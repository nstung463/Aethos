import { type FormEvent, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import type {
  AskUserRequest,
  ChatThread,
  ComposerMode,
  Message,
  ModeConfig,
  PermissionMode,
  PermissionProfile,
  ProviderProfile,
  RunStep,
  ThreadPermissionsBundle,
  ToolEvent,
  WorkspaceFrame,
} from "../types";
import {
  appendMessageContent,
  appendRunStepItem,
  createEmptyThread,
  createId,
  finalizeActiveReasoning,
  mergeReasoning,
  summarizeTitle,
} from "../utils/threads";
import { deriveToolStepId, runStepsToWorkspaceFrames } from "../utils/runSteps";
import {
  createRemoteThread,
  generateFollowUps,
  generateTitle,
  streamChat,
} from "../utils/stream";
import { fetchThreadPermissions, updateThreadPermissions } from "../utils/permissions";
import { useThreads } from "../context/ThreadsContext";
import type { PendingPermissionRetry } from "./usePermissions";
import { stopThreadRun, updateBackendThread } from "../utils/backendThreads";

const EMPTY_PERMISSION_PROFILE: PermissionProfile = {
  mode: null,
  working_directories: [],
  rules: [],
};

function resolveToolStepStatus(toolName: string, output?: string): RunStep["status"] {
  if ((toolName === "bash" || toolName === "powershell") && output) {
    const firstLine = output.split("\n", 1)[0]?.trim() ?? "";
    if (firstLine.startsWith("Exit code:")) {
      const code = Number.parseInt(firstLine.slice("Exit code:".length).trim(), 10);
      if (Number.isFinite(code)) {
        return code === 0 ? "completed" : "failed";
      }
    }
  }
  return "completed";
}

interface ChatOptions {
  activeThread: ChatThread | null;
  activeProfile: ProviderProfile | null;
  activeProfileId: string;
  activeModel: string;
  activeMode: ComposerMode;
  activeBackendMode: "sandbox" | "local";
  activeLocalRootDir: string;
  modeConfig: ModeConfig;
  isUploading: boolean;
  pendingRetriesRef: React.MutableRefObject<Record<string, PendingPermissionRetry>>;
  threadPermissions: ThreadPermissionsBundle | null;
  setThreadPermissions: (bundle: ThreadPermissionsBundle | null) => void;
  setStatus: (s: string) => void;
  setError: (e: string) => void;
}

export function useChat({
  activeThread,
  activeProfile,
  activeProfileId,
  activeModel,
  activeMode,
  activeBackendMode,
  activeLocalRootDir,
  modeConfig,
  isUploading,
  pendingRetriesRef,
  threadPermissions,
  setThreadPermissions,
  setStatus,
  setError,
}: ChatOptions) {
  const navigate = useNavigate();
  const { setThreads, updateThread } = useThreads();
  const [draft, setDraft] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const reasoningStartRef = useRef<number | null>(null);
  const runStepsRef = useRef<RunStep[]>([]);
  const toolStepIndexRef = useRef<Record<string, string>>({});
  const currentRunRef = useRef<{ threadId: string; runId: string; localThreadId: string; assistantMessageId: string } | null>(null);

  function resolveCurrentRunStepMessageId(fallbackMessageId: string) {
    return currentRunRef.current?.assistantMessageId ?? fallbackMessageId;
  }

  function settlePendingPermissionRunSteps(status: Extract<RunStep["status"], "completed" | "interrupted"> = "completed") {
    const nowIso = new Date().toISOString();
    runStepsRef.current = runStepsRef.current.map((step) =>
      step.kind === "permission" && step.status === "pending"
        ? {
            ...step,
            status,
            endedAt: step.endedAt ?? nowIso,
          }
        : step,
    );
  }

  function appendPermissionRunStep(assistantMsgId: string, request: { reason: string; behavior: "ask" | "deny" }) {
    if (runStepsRef.current.some((step) => step.kind === "permission" && step.status === "pending")) {
      return;
    }
    runStepsRef.current = [
      ...runStepsRef.current,
      {
        id: createId("step"),
        runId: currentRunRef.current?.runId ?? null,
        messageId: assistantMsgId,
        parentStepId: null,
        kind: "permission",
        status: "pending",
        startedAt: new Date().toISOString(),
        endedAt: null,
        permissionRequest: request,
      },
    ];
  }

  function acknowledgeServerRun(
    threadLocalId: string,
    optimisticUserMessageId: string,
    updater?: (thread: ChatThread) => ChatThread,
  ) {
    updateThread(threadLocalId, (thread) => {
      const nextThread = updater ? updater(thread) : thread;
      return {
        ...nextThread,
        messages: nextThread.messages.map((msg) =>
          msg.id === optimisticUserMessageId && msg.optimistic
            ? { ...msg, optimistic: false }
            : msg,
        ),
      };
    });
  }

  function handleToolEvent(
    event: ToolEvent,
    threadLocalId: string,
    assistantMsgId: string,
    optimisticUserMessageId?: string,
  ) {
    const nowIso = new Date().toISOString();
    let startedRunStepId: string | null = null;
    const canonicalRunStepId = event.step_id ?? deriveToolStepId(event.tool_call_id);

    const fallbackRunStepId = runStepsRef.current
      .slice()
      .reverse()
      .find(
        (step) =>
          step.kind === "tool" &&
          step.toolName === event.name &&
          !step.endedAt,
      )?.id;

    if (event.phase === "start") {
      const existingStepId =
        (canonicalRunStepId && runStepsRef.current.some((step) => step.id === canonicalRunStepId)
          ? canonicalRunStepId
          : null) ??
        (event.tool_call_id ? toolStepIndexRef.current[event.tool_call_id] : null) ??
        fallbackRunStepId;
      if (existingStepId) {
        console.warn("Received duplicate tool start event", event);
      } else {
        const runStepId = canonicalRunStepId ?? createId("step");
        runStepsRef.current = [
          ...runStepsRef.current,
          {
            id: runStepId,
            runId: currentRunRef.current?.runId ?? null,
            messageId: assistantMsgId,
            parentStepId: null,
            kind: "tool",
            status: "in_progress",
            startedAt: nowIso,
            endedAt: null,
            toolCallId: event.tool_call_id ?? null,
            toolName: event.name,
            input: event.input ?? {},
            summary: event.summary,
          },
        ];
        if (event.tool_call_id) {
          toolStepIndexRef.current[event.tool_call_id] = runStepId;
        }
        startedRunStepId = runStepId;
      }
    } else if (event.phase === "end") {
      const runStepId =
        (canonicalRunStepId && runStepsRef.current.some((step) => step.id === canonicalRunStepId)
          ? canonicalRunStepId
          : null) ??
        (event.tool_call_id ? toolStepIndexRef.current[event.tool_call_id] : null) ??
        fallbackRunStepId;
      if (!runStepId) {
        console.warn("Received tool end event without matching start", event);
        const completedRunStepId = canonicalRunStepId ?? createId("step");
        runStepsRef.current = [
          ...runStepsRef.current,
          {
            id: completedRunStepId,
            runId: currentRunRef.current?.runId ?? null,
            messageId: resolveCurrentRunStepMessageId(assistantMsgId),
            parentStepId: null,
            kind: "tool",
            status: resolveToolStepStatus(event.name, event.output),
            startedAt: nowIso,
            endedAt: nowIso,
            toolCallId: event.tool_call_id ?? null,
            toolName: event.name,
            input: event.input ?? {},
            summary: event.summary,
            output: event.output,
            rawOutput: event.raw_output ?? event.output,
            collapsed: event.collapsed,
            lineCount: event.line_count,
            classification: event.classification,
          },
        ];
        if (event.tool_call_id) {
          toolStepIndexRef.current[event.tool_call_id] = completedRunStepId;
        }
        startedRunStepId = completedRunStepId;
      } else {
        let updated = false;
        runStepsRef.current = runStepsRef.current.map((step) => {
          if (step.id !== runStepId) return step;
          updated = true;
          if (step.endedAt) {
            console.warn("Received duplicate tool end event", event);
            return step;
          }
          return {
            ...step,
            endedAt: nowIso,
            summary: step.summary ?? event.summary,
            output: event.output,
            rawOutput: event.raw_output ?? event.output,
            collapsed: event.collapsed,
            lineCount: event.line_count,
            classification: event.classification,
            status: step.status === "pending" ? "pending" : resolveToolStepStatus(step.toolName ?? event.name, event.output),
          };
        });
        if (!updated) {
          console.warn("Tool step index resolved to a missing run step", event);
        }
      }
    }

    const workspaceFrames: WorkspaceFrame[] = runStepsToWorkspaceFrames(runStepsRef.current);

    const updateThreadState = (thread: ChatThread) => ({
      ...thread,
      messages: thread.messages.map((msg) =>
        msg.id === assistantMsgId
          ? (() => {
              const withStepItem = startedRunStepId
                ? appendRunStepItem(msg, startedRunStepId)
                : msg;
              return {
                ...withStepItem,
                runSteps: [...runStepsRef.current],
                workspaceFrames,
              };
            })()
          : msg,
      ),
      updatedAt: new Date().toISOString(),
    });

    if (optimisticUserMessageId) {
      acknowledgeServerRun(threadLocalId, optimisticUserMessageId, updateThreadState);
      return;
    }

    updateThread(threadLocalId, updateThreadState);
  }

  async function hydrateThreadMetadata(
    thread: ChatThread,
    modeInstruction: string,
    options: { generateTitle: boolean },
    profile: ProviderProfile,
  ) {
    const taskInput = { model: profile.model, messages: thread.messages, modeInstruction, profile };
    const tasks = [
      options.generateTitle ? generateTitle(taskInput) : Promise.resolve<{ title?: string }>({}),
      generateFollowUps(taskInput),
    ] as const;

    const [titleResult, followUpsResult] = await Promise.allSettled(tasks);

    if (titleResult.status === "fulfilled") {
      const nextTitle = titleResult.value.title?.trim();
      if (nextTitle) {
        const remoteId = thread.remoteId ?? (thread.id.startsWith("thread_") ? thread.id : undefined);
        updateThread(thread.id, (current) => ({
          ...current,
          title: nextTitle,
          updatedAt: new Date().toISOString(),
        }));
        if (remoteId) {
          updateBackendThread(remoteId, {
            title: nextTitle,
            model: thread.model,
            mode: thread.mode,
            profile_id: thread.profileId,
            project: thread.project,
            is_favorite: thread.isFavorite,
          }).catch(() => {
            // Local title remains useful even if metadata persistence fails.
          });
        }
      }
    }

    if (followUpsResult.status === "fulfilled") {
      updateThread(thread.id, (current) => ({
        ...current,
        messages: current.messages.map((msg, i, arr) =>
          i === arr.length - 1 && msg.role === "assistant"
            ? {
                ...msg,
                followUps: Array.isArray(followUpsResult.value.follow_ups)
                  ? followUpsResult.value.follow_ups
                  : [],
              }
            : msg,
        ),
        updatedAt: new Date().toISOString(),
      }));
    }
  }

  function resetAssistantMessage(threadLocalId: string, assistantMessageId: string) {
    updateThread(threadLocalId, (thread) => ({
      ...thread,
      messages: thread.messages.map((msg) =>
          msg.id === assistantMessageId
            ? {
                ...msg,
                error: undefined,
                permissionRequest: undefined,
                askUserRequest: undefined,
                status: "streaming" as const,
            }
          : msg,
      ),
      updatedAt: new Date().toISOString(),
    }));
  }

  function buildFallbackPendingRetry(assistantMessageId: string): PendingPermissionRetry | null {
    const thread = activeThread;
    if (!thread || !activeProfile) return null;

    const remoteThreadId = thread.remoteId ?? (thread.id.startsWith("thread_") ? thread.id : undefined);
    if (!remoteThreadId) return null;

    const blockedIndex = thread.messages.findIndex(
      (message) => message.id === assistantMessageId && message.role === "assistant",
    );
    if (blockedIndex <= 0) return null;

    return {
      localThreadId: thread.id,
      remoteThreadId,
      assistantMessageId,
      requestMessages: thread.messages.slice(0, blockedIndex),
      profile: activeProfile,
      model: activeModel,
      modeInstruction: modeConfig.instruction,
      backendMode: activeBackendMode,
      localRootDir: activeBackendMode === "local" ? activeLocalRootDir : undefined,
    };
  }

  async function retryPendingPermissionRequest(
    assistantMessageId: string,
    options: { persistMode?: PermissionMode; resumeOverride?: Record<string, unknown> },
  ) {
    const pending = pendingRetriesRef.current[assistantMessageId] ?? buildFallbackPendingRetry(assistantMessageId);
    if (!pending) throw new Error("The blocked action is no longer available to retry.");

    let activeThreadPermissions = threadPermissions;
    if (options.persistMode) {
      activeThreadPermissions = await updateThreadPermissions(pending.remoteThreadId, {
        ...(activeThreadPermissions?.overlay ?? EMPTY_PERMISSION_PROFILE),
        mode: options.persistMode,
        working_directories: [...(activeThreadPermissions?.overlay.working_directories ?? [])],
        rules: [...(activeThreadPermissions?.overlay.rules ?? [])],
      });
      setThreadPermissions(activeThreadPermissions);
    }

    const existingAssistantMessage =
      activeThread?.messages.find((msg) => msg.id === assistantMessageId) ?? null;

    resetAssistantMessage(pending.localThreadId, assistantMessageId);
    setError("");
    setStatus("Retrying blocked action...");
    setIsStreaming(true);

    let sawPermissionRequest = false;
    let sawContent = false;
    const controller = new AbortController();
    abortRef.current = controller;
    reasoningStartRef.current = null;
    runStepsRef.current = [...(existingAssistantMessage?.runSteps ?? [])];
    settlePendingPermissionRunSteps("completed");
    toolStepIndexRef.current = Object.fromEntries(
      runStepsRef.current
        .filter((step) => step.kind === "tool" && step.toolCallId)
        .map((step) => [step.toolCallId as string, step.id]),
    );
    updateThread(pending.localThreadId, (thread) => ({
      ...thread,
      messages: thread.messages.map((msg) =>
        msg.id === assistantMessageId
          ? {
              ...msg,
              runSteps: [...runStepsRef.current],
              workspaceFrames: runStepsToWorkspaceFrames(runStepsRef.current),
            }
          : msg,
      ),
      updatedAt: new Date().toISOString(),
    }));

    try {
      await streamChat({
        model: pending.model,
        messages: pending.requestMessages,
        modeInstruction: pending.modeInstruction,
        threadId: pending.remoteThreadId,
        profile: pending.profile,
        signal: controller.signal,
        extraMetadata: {
          backend: {
            mode: pending.backendMode,
            root_dir: pending.backendMode === "local" ? pending.localRootDir : undefined,
          },
          resume: options.resumeOverride ?? { approved: true },
        },
        onContent: (chunk) => {
          sawContent = true;
          updateThread(pending.localThreadId, (thread) => ({
            ...thread,
            messages: thread.messages.map((msg) =>
              msg.id === assistantMessageId
                ? { ...appendMessageContent(msg, chunk), permissionRequest: undefined }
                : msg,
            ),
            updatedAt: new Date().toISOString(),
          }));
        },
        onReasoning: (chunk) => {
          if (!reasoningStartRef.current) reasoningStartRef.current = Date.now();
          updateThread(pending.localThreadId, (thread) => ({
            ...thread,
            messages: thread.messages.map((msg) =>
              msg.id === assistantMessageId
                ? { ...mergeReasoning(msg, chunk), permissionRequest: undefined }
                : msg,
            ),
            updatedAt: new Date().toISOString(),
          }));
        },
        onPermissionRequest: (request) => {
          sawPermissionRequest = true;
          appendPermissionRunStep(assistantMessageId, request);
          updateThread(pending.localThreadId, (thread) => ({
            ...thread,
            messages: thread.messages.map((msg) =>
              msg.id === assistantMessageId
                ? {
                    ...msg,
                    permissionRequest: request,
                    runSteps: [...runStepsRef.current],
                    workspaceFrames: runStepsToWorkspaceFrames(runStepsRef.current),
                    status: "done" as const,
                  }
                : msg,
            ),
            updatedAt: new Date().toISOString(),
          }));
        },
        onAskUserRequest: (request: AskUserRequest) => {
          sawPermissionRequest = true;
          updateThread(pending.localThreadId, (thread) => ({
            ...thread,
            messages: thread.messages.map((msg) =>
              msg.id === assistantMessageId
                ? { ...msg, askUserRequest: request, status: "done" as const }
                : msg,
            ),
            updatedAt: new Date().toISOString(),
          }));
        },
        onToolEvent: (event) => handleToolEvent(event, pending.localThreadId, assistantMessageId),
        onRunId: (runId) => {
          currentRunRef.current = {
            threadId: pending.remoteThreadId,
            runId,
            localThreadId: pending.localThreadId,
            assistantMessageId,
          };
          updateThread(pending.localThreadId, (thread) => ({
            ...thread,
            activeRunId: runId,
            status: "running",
          }));
        },
      });

      const thinkingDuration = reasoningStartRef.current
        ? Math.round((Date.now() - reasoningStartRef.current) / 1000)
        : undefined;
      reasoningStartRef.current = null;

      updateThread(pending.localThreadId, (thread) => ({
        ...thread,
        status: sawPermissionRequest ? "requires_action" : "idle",
        activeRunId: null,
        messages: thread.messages.map((msg) =>
          msg.id === assistantMessageId
            ? { ...finalizeActiveReasoning(msg), status: "done" as const, thinkingDuration }
            : msg,
        ),
        updatedAt: new Date().toISOString(),
      }));

      if (!sawPermissionRequest && sawContent) {
        delete pendingRetriesRef.current[assistantMessageId];
      }
      currentRunRef.current = null;
      setStatus(sawPermissionRequest ? "Permission still required" : "Ready");
    } catch (retryError) {
      delete pendingRetriesRef.current[assistantMessageId];
      if (retryError instanceof DOMException && retryError.name === "AbortError") {
        settlePendingPermissionRunSteps("interrupted");
        updateThread(pending.localThreadId, (thread) => ({
          ...thread,
          status: "interrupted",
          activeRunId: null,
          lastStopRunId: thread.activeRunId ?? null,
          lastStopReason: "user_cancel",
          lastInterruptedAt: Math.floor(Date.now() / 1000),
          messages: thread.messages.map((item) =>
            item.id === assistantMessageId && item.status === "streaming"
              ? {
                  ...item,
                  status: "interrupted" as const,
                  runSteps: [...runStepsRef.current],
                  workspaceFrames: runStepsToWorkspaceFrames(runStepsRef.current),
                }
              : item,
          ),
          updatedAt: new Date().toISOString(),
        }));
        setStatus("Stopped");
        return;
      }
      const message =
        retryError instanceof Error
            ? retryError.message
            : "Retry failed";
      updateThread(pending.localThreadId, (thread) => ({
        ...thread,
        messages: thread.messages.map((item) =>
          item.id === assistantMessageId
            ? {
                ...item,
                status: "error" as const,
                error: message,
                content: item.content || "The assistant did not return any text.",
              }
            : item,
        ),
      }));
      setError(message);
      setStatus("Error");
      throw retryError;
    } finally {
      abortRef.current = null;
      setIsStreaming(false);
    }
  }

  async function handleSubmit(event?: FormEvent) {
    event?.preventDefault();

    const prompt = draft.trim();
    const pendingAttachments = activeThread?.attachments ?? [];
    if ((!prompt && pendingAttachments.length === 0) || !activeProfile || isStreaming || isUploading)
      return;
    setError("");
    setStatus(`Running in ${modeConfig.label.toLowerCase()} mode`);
    setIsStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;
    reasoningStartRef.current = null;
    runStepsRef.current = [];
    toolStepIndexRef.current = {};

    let remoteThreadId =
      activeThread?.remoteId ?? (activeThread?.id.startsWith("thread_") ? activeThread.id : undefined);
    if (!remoteThreadId) {
      try {
        remoteThreadId = await createRemoteThread(controller.signal);
      } catch (err) {
        const msg =
          err instanceof DOMException && err.name === "AbortError"
            ? "Generation stopped"
            : err instanceof Error
              ? err.message
              : "Failed to create thread";
        abortRef.current = null;
        setIsStreaming(false);
        setError(msg);
        setStatus("Error");
        return;
      }
    }

    const now = new Date().toISOString();
    const rawBase = activeThread ?? {
      ...createEmptyThread(activeModel, activeMode),
      id: remoteThreadId,
      remoteId: remoteThreadId,
    };
    const isFirstMessage = rawBase.messages.length === 0;

    const userMsg: Message = {
      id: createId("msg"),
      role: "user",
      content:
        prompt ||
        pendingAttachments.map((a) => `Attached file: ${a.filename}`).join("\n"),
      createdAt: now,
      status: "done",
      optimistic: true,
    };
    const assistantMsg: Message = {
      id: createId("msg"),
      role: "assistant",
      content: "",
      reasoning: "",
      toolEvents: [],
      runSteps: [],
      workspaceFrames: [],
      streamItems: [],
      createdAt: now,
      status: "streaming",
    };
    const nextMessages = [...rawBase.messages, userMsg, assistantMsg];
    const nextThread: ChatThread = {
      ...rawBase,
      remoteId: remoteThreadId,
      profileId: rawBase.profileId ?? activeProfileId,
      model: activeModel,
      mode: activeMode,
      backendMode: activeBackendMode,
      localRootDir: activeBackendMode === "local" ? activeLocalRootDir : "",
      title: isFirstMessage ? summarizeTitle(prompt) : rawBase.title,
      messages: nextMessages,
      updatedAt: now,
    };

    setThreads((current) => {
      const existingIndex = current.findIndex((t) => t.id === nextThread.id);
      if (existingIndex === -1) return [nextThread, ...current];
      return current.map((t) => (t.id === nextThread.id ? nextThread : t));
    });

    if (!activeThread) navigate(`/app/${remoteThreadId}`);
    setDraft("");

    try {
      if (activeThread && !activeThread.remoteId) {
        updateThread(nextThread.id, (thread) => ({
          ...thread,
          remoteId: remoteThreadId,
          updatedAt: new Date().toISOString(),
        }));
      }
      updateBackendThread(remoteThreadId, {
        title: nextThread.title,
        model: activeModel,
        mode: activeMode,
        profile_id: activeProfileId,
        project: nextThread.project,
        is_favorite: nextThread.isFavorite,
      }).catch(() => {
        // Runtime metadata is still checkpointed; UI metadata can retry on next explicit change.
      });

      const currentThreadPermissions = await fetchThreadPermissions(
        remoteThreadId,
        controller.signal,
      );
      setThreadPermissions(currentThreadPermissions);

      pendingRetriesRef.current[assistantMsg.id] = {
        localThreadId: nextThread.id,
        remoteThreadId,
        assistantMessageId: assistantMsg.id,
        requestMessages: nextMessages.slice(0, -1),
        profile: activeProfile,
        model: activeModel,
        modeInstruction: modeConfig.instruction,
        backendMode: activeBackendMode,
        localRootDir: activeBackendMode === "local" ? activeLocalRootDir : undefined,
      };

      let sawPermissionRequest = false;
      let sawContent = false;

      await streamChat({
        model: activeModel,
        messages: nextMessages,
        modeInstruction: modeConfig.instruction,
        threadId: remoteThreadId,
        profile: activeProfile,
        signal: controller.signal,
        extraMetadata: {
          backend: {
            mode: activeBackendMode,
            root_dir: activeBackendMode === "local" ? activeLocalRootDir : undefined,
          },
        },
        onContent: (chunk) => {
          sawContent = true;
          acknowledgeServerRun(nextThread.id, userMsg.id, (thread) => ({
            ...thread,
            messages: thread.messages.map((msg) =>
              msg.id === assistantMsg.id
                ? { ...appendMessageContent(msg, chunk), permissionRequest: undefined }
                : msg,
            ),
            updatedAt: new Date().toISOString(),
          }));
        },
        onReasoning: (chunk) => {
          if (!reasoningStartRef.current) reasoningStartRef.current = Date.now();
          acknowledgeServerRun(nextThread.id, userMsg.id, (thread) => ({
            ...thread,
            messages: thread.messages.map((msg) =>
              msg.id === assistantMsg.id
                ? { ...mergeReasoning(msg, chunk), permissionRequest: undefined }
                : msg,
            ),
            updatedAt: new Date().toISOString(),
          }));
        },
        onPermissionRequest: (request) => {
          sawPermissionRequest = true;
          appendPermissionRunStep(assistantMsg.id, request);
          acknowledgeServerRun(nextThread.id, userMsg.id, (thread) => ({
            ...thread,
            messages: thread.messages.map((msg) =>
              msg.id === assistantMsg.id
                ? {
                    ...msg,
                    permissionRequest: request,
                    askUserRequest: undefined,
                    runSteps: [...runStepsRef.current],
                    workspaceFrames: runStepsToWorkspaceFrames(runStepsRef.current),
                    status: "done" as const,
                  }
                : msg,
            ),
            updatedAt: new Date().toISOString(),
          }));
        },
        onAskUserRequest: (request: AskUserRequest) => {
          sawPermissionRequest = true;
          acknowledgeServerRun(nextThread.id, userMsg.id, (thread) => ({
            ...thread,
            messages: thread.messages.map((msg) =>
              msg.id === assistantMsg.id
                ? { ...msg, askUserRequest: request, status: "done" as const }
                : msg,
            ),
            updatedAt: new Date().toISOString(),
          }));
        },
        onToolEvent: (event) => handleToolEvent(event, nextThread.id, assistantMsg.id, userMsg.id),
        onRunId: (runId) => {
          currentRunRef.current = {
            threadId: remoteThreadId,
            runId,
            localThreadId: nextThread.id,
            assistantMessageId: assistantMsg.id,
          };
          acknowledgeServerRun(nextThread.id, userMsg.id, (thread) => ({
            ...thread,
            activeRunId: runId,
            status: "running",
          }));
        },
      });

      const thinkingDuration = reasoningStartRef.current
        ? Math.round((Date.now() - reasoningStartRef.current) / 1000)
        : undefined;
      reasoningStartRef.current = null;

      updateThread(nextThread.id, (thread) => ({
        ...thread,
        status: sawPermissionRequest ? "requires_action" : "idle",
        activeRunId: null,
        messages: thread.messages.map((msg) =>
          msg.id === assistantMsg.id
            ? {
                ...finalizeActiveReasoning(msg),
                status: "done" as const,
                thinkingDuration,
                runSteps: runStepsRef.current,
                workspaceFrames: runStepsToWorkspaceFrames(runStepsRef.current),
              }
            : msg,
        ),
        updatedAt: new Date().toISOString(),
      }));

      if (!sawPermissionRequest && sawContent) {
        delete pendingRetriesRef.current[assistantMsg.id];
      }
      currentRunRef.current = null;

      void hydrateThreadMetadata(
        {
          ...nextThread,
          messages: nextMessages.map((msg) =>
            msg.id === assistantMsg.id
              ? { ...msg, status: "done" as const, thinkingDuration }
              : msg,
          ),
        },
        modeConfig.instruction,
        { generateTitle: isFirstMessage },
        activeProfile,
      );

      setStatus("Ready");
    } catch (err: unknown) {
      delete pendingRetriesRef.current[assistantMsg.id];
      if (err instanceof DOMException && err.name === "AbortError") {
        updateThread(nextThread.id, (thread) => ({
          ...thread,
          status: "interrupted",
          activeRunId: null,
          messages: thread.messages.map((m) =>
            m.id === assistantMsg.id && m.status === "streaming"
              ? { ...m, status: "interrupted" as const }
              : m.id === userMsg.id && m.optimistic
                ? { ...m, optimistic: false }
              : m,
          ),
          updatedAt: new Date().toISOString(),
        }));
        setStatus("Stopped");
        return;
      }
      const msg =
        err instanceof Error
            ? err.message
            : "Unknown error";
      updateThread(nextThread.id, (thread) => ({
        ...thread,
        messages: thread.messages.map((m) =>
          m.id === assistantMsg.id
            ? {
                ...m,
                status: "error" as const,
                error: msg,
                content: m.content || "The assistant did not return any text.",
              }
            : m,
        ),
      }));
      setError(msg);
      setStatus("Error");
    } finally {
      abortRef.current = null;
      setIsStreaming(false);
    }
  }

  function handleStop() {
    const currentRun = currentRunRef.current;
    if (currentRun) {
      settlePendingPermissionRunSteps("interrupted");
      stopThreadRun(currentRun.threadId, currentRun.runId, "user_cancel").catch(() => {
        // The local abort still gives control back immediately; backend reconciliation handles stale runs.
      });
      updateThread(currentRun.localThreadId, (thread) => ({
        ...thread,
        status: "interrupted",
        activeRunId: null,
        lastStopRunId: currentRun.runId,
        lastStopReason: "user_cancel",
        lastInterruptedAt: Math.floor(Date.now() / 1000),
        messages: thread.messages.map((message) =>
          message.id === currentRun.assistantMessageId && message.status === "streaming"
            ? {
                ...message,
                status: "interrupted" as const,
                runSteps: [...runStepsRef.current],
                workspaceFrames: runStepsToWorkspaceFrames(runStepsRef.current),
              }
            : message,
        ),
        updatedAt: new Date().toISOString(),
      }));
    }
    abortRef.current?.abort();
    abortRef.current = null;
    currentRunRef.current = null;
    setStatus("Stopped");
  }

  async function handleApproveOnce(messageId: string) {
    await retryPendingPermissionRequest(messageId, {});
  }

  async function handleApproveForChat(messageId: string, mode: PermissionMode) {
    await retryPendingPermissionRequest(messageId, { persistMode: mode });
  }

  async function handleBypassForChat(messageId: string) {
    await retryPendingPermissionRequest(messageId, { persistMode: "bypass_permissions" });
  }

  async function handleAnswerAskUser(
    messageId: string,
    answers: Record<string, string>,
    notes: Record<string, string>,
  ) {
    await retryPendingPermissionRequest(messageId, {
      resumeOverride: { answers, notes },
    });
  }

  return {
    draft,
    setDraft,
    isStreaming,
    handleSubmit,
    handleStop,
    handleApproveOnce,
    handleApproveForChat,
    handleBypassForChat,
    handleAnswerAskUser,
  };
}
