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
  ThreadPermissionsBundle,
  ToolEvent,
  WorkspaceFrame,
} from "../types";
import {
  appendMessageContent,
  appendWorkspaceFrameItem,
  createEmptyThread,
  createId,
  mergeReasoning,
  summarizeTitle,
} from "../utils/threads";
import {
  createRemoteThread,
  generateFollowUps,
  generateTitle,
  streamChat,
} from "../utils/stream";
import { fetchThreadPermissions, updateThreadPermissions } from "../utils/permissions";
import { useThreads } from "../context/ThreadsContext";
import type { PendingPermissionRetry } from "./usePermissions";

const EMPTY_PERMISSION_PROFILE: PermissionProfile = {
  mode: null,
  working_directories: [],
  rules: [],
};

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
  const workspaceFramesRef = useRef<WorkspaceFrame[]>([]);

  function handleToolEvent(event: ToolEvent, threadLocalId: string, assistantMsgId: string) {
    let startedFrameId: string | null = null;

    if (event.phase === "start" && event.input !== undefined) {
      const frame: WorkspaceFrame = {
        id: `frame-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        timestamp: new Date().toISOString(),
        toolName: event.name,
        input: event.input,
        status: "in_progress",
      };
      workspaceFramesRef.current = [...workspaceFramesRef.current, frame];
      startedFrameId = frame.id;
    } else if (event.phase === "end" && event.output !== undefined) {
      const frames = workspaceFramesRef.current;
      const now = Date.now();
      const reversedIdx = [...frames].reverse().findIndex(
        (frame) =>
          frame.toolName === event.name &&
          frame.output === undefined &&
          now - new Date(frame.timestamp).getTime() < 60_000,
      );

      if (reversedIdx !== -1) {
        const realIdx = frames.length - 1 - reversedIdx;
        workspaceFramesRef.current = frames.map((frame, index) =>
          index === realIdx
            ? { ...frame, output: event.output, status: "completed" }
            : frame,
        );
      }
    }

    updateThread(threadLocalId, (thread) => ({
      ...thread,
      messages: thread.messages.map((msg) =>
        msg.id === assistantMsgId
          ? (() => {
              const withFrameItem = startedFrameId
                ? appendWorkspaceFrameItem(msg, startedFrameId)
                : msg;
              return {
                ...withFrameItem,
                workspaceFrames: [...workspaceFramesRef.current],
              };
            })()
          : msg,
      ),
      updatedAt: new Date().toISOString(),
    }));
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
        updateThread(thread.id, (current) => ({
          ...current,
          title: nextTitle,
          updatedAt: new Date().toISOString(),
        }));
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
                content: "",
                reasoning: "",
                toolEvents: [],
                workspaceFrames: [],
                streamItems: [],
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

  async function retryPendingPermissionRequest(
    assistantMessageId: string,
    options: { persistMode?: PermissionMode; resumeOverride?: Record<string, unknown> },
  ) {
    const pending = pendingRetriesRef.current[assistantMessageId];
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

    resetAssistantMessage(pending.localThreadId, assistantMessageId);
    setError("");
    setStatus("Retrying blocked action...");
    setIsStreaming(true);

    let sawPermissionRequest = false;
    let sawContent = false;
    const controller = new AbortController();
    abortRef.current = controller;
    reasoningStartRef.current = null;
    workspaceFramesRef.current = [];

    try {
      await streamChat({
        model: pending.model,
        messages: pending.requestMessages,
        modeInstruction: pending.modeInstruction,
        threadId: pending.remoteThreadId,
        fileIds: pending.fileIds,
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
          updateThread(pending.localThreadId, (thread) => ({
            ...thread,
            messages: thread.messages.map((msg) =>
              msg.id === assistantMessageId
                ? { ...msg, permissionRequest: request, status: "done" as const }
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
      });

      const thinkingDuration = reasoningStartRef.current
        ? Math.round((Date.now() - reasoningStartRef.current) / 1000)
        : undefined;
      reasoningStartRef.current = null;

      updateThread(pending.localThreadId, (thread) => ({
        ...thread,
        messages: thread.messages.map((msg) =>
          msg.id === assistantMessageId ? { ...msg, status: "done" as const, thinkingDuration } : msg,
        ),
        updatedAt: new Date().toISOString(),
      }));

      if (!sawPermissionRequest && sawContent) {
        delete pendingRetriesRef.current[assistantMessageId];
      }
      setStatus(sawPermissionRequest ? "Permission still required" : "Ready");
    } catch (retryError) {
      delete pendingRetriesRef.current[assistantMessageId];
      const message =
        retryError instanceof DOMException && retryError.name === "AbortError"
          ? "Retry stopped"
          : retryError instanceof Error
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

    const now = new Date().toISOString();
    const rawBase = activeThread ?? createEmptyThread(activeModel, activeMode);
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
      workspaceFrames: [],
      streamItems: [],
      createdAt: now,
      status: "streaming",
    };
    const nextMessages = [...rawBase.messages, userMsg, assistantMsg];
    const nextThread: ChatThread = {
      ...rawBase,
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

    if (!activeThread) navigate(`/app/${nextThread.id}`);
    setDraft("");
    setIsStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;
    reasoningStartRef.current = null;
    workspaceFramesRef.current = [];

    try {
      const remoteThreadId =
        nextThread.remoteId ?? (await createRemoteThread(controller.signal));
      if (!nextThread.remoteId) {
        updateThread(nextThread.id, (thread) => ({
          ...thread,
          remoteId: remoteThreadId,
          updatedAt: new Date().toISOString(),
        }));
      }

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
        fileIds: pendingAttachments.map((a) => a.id),
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
        fileIds: pendingAttachments.map((a) => a.id),
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
          updateThread(nextThread.id, (thread) => ({
            ...thread,
            messages: thread.messages.map((msg) =>
              msg.id === assistantMsg.id
                ? { ...appendMessageContent(msg, chunk), permissionRequest: undefined }
                : msg.id === userMsg.id
                  ? { ...msg, optimistic: false }
                  : msg,
            ),
            updatedAt: new Date().toISOString(),
          }));
        },
        onReasoning: (chunk) => {
          if (!reasoningStartRef.current) reasoningStartRef.current = Date.now();
          updateThread(nextThread.id, (thread) => ({
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
          updateThread(nextThread.id, (thread) => ({
            ...thread,
            messages: thread.messages.map((msg) =>
              msg.id === assistantMsg.id ? { ...msg, permissionRequest: request } : msg,
            ),
            updatedAt: new Date().toISOString(),
          }));
        },
        onAskUserRequest: (request: AskUserRequest) => {
          sawPermissionRequest = true;
          updateThread(nextThread.id, (thread) => ({
            ...thread,
            messages: thread.messages.map((msg) =>
              msg.id === assistantMsg.id
                ? { ...msg, askUserRequest: request, status: "done" as const }
                : msg,
            ),
            updatedAt: new Date().toISOString(),
          }));
        },
        onToolEvent: (event) => handleToolEvent(event, nextThread.id, assistantMsg.id),
      });

      const thinkingDuration = reasoningStartRef.current
        ? Math.round((Date.now() - reasoningStartRef.current) / 1000)
        : undefined;
      reasoningStartRef.current = null;

      updateThread(nextThread.id, (thread) => ({
        ...thread,
        messages: thread.messages.map((msg) =>
          msg.id === assistantMsg.id
            ? { ...msg, status: "done" as const, thinkingDuration, workspaceFrames: workspaceFramesRef.current }
            : msg,
        ),
        updatedAt: new Date().toISOString(),
      }));

      if (!sawPermissionRequest && sawContent) {
        delete pendingRetriesRef.current[assistantMsg.id];
      }

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
      const msg =
        err instanceof DOMException && err.name === "AbortError"
          ? "Generation stopped"
          : err instanceof Error
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
    abortRef.current?.abort();
    abortRef.current = null;
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
