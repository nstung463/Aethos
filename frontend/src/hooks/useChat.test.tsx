import { act, renderHook, waitFor } from "@testing-library/react";
import { type ReactNode, useRef } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ThreadsProvider, useThreads } from "../context/ThreadsContext";
import type {
  AskUserRequest,
  ModeConfig,
  PermissionRequest,
  ProviderProfile,
  ThreadPermissionsBundle,
  ToolEvent,
} from "../types";
import { useChat } from "./useChat";
import * as authModule from "../utils/auth";
import * as backendThreadsModule from "../utils/backendThreads";
import * as permissionsModule from "../utils/permissions";
import * as streamModule from "../utils/stream";

vi.mock("../utils/auth", () => ({
  ensureAuthToken: vi.fn(),
}));

vi.mock("../utils/backendThreads", () => ({
  deleteBackendThread: vi.fn(),
  fetchBackendThread: vi.fn(),
  fetchBackendThreads: vi.fn(),
  stopThreadRun: vi.fn(),
  updateBackendThread: vi.fn(),
}));

vi.mock("../utils/permissions", () => ({
  fetchThreadPermissions: vi.fn(),
  updateThreadPermissions: vi.fn(),
}));

vi.mock("../utils/stream", () => ({
  createRemoteThread: vi.fn(),
  generateFollowUps: vi.fn(),
  generateTitle: vi.fn(),
  streamChat: vi.fn(),
}));

const streamChatMock = vi.mocked(streamModule.streamChat);
const createRemoteThreadMock = vi.mocked(streamModule.createRemoteThread);
const generateTitleMock = vi.mocked(streamModule.generateTitle);
const generateFollowUpsMock = vi.mocked(streamModule.generateFollowUps);
const ensureAuthTokenMock = vi.mocked(authModule.ensureAuthToken);
const fetchBackendThreadsMock = vi.mocked(backendThreadsModule.fetchBackendThreads);
const updateBackendThreadMock = vi.mocked(backendThreadsModule.updateBackendThread);
const fetchThreadPermissionsMock = vi.mocked(permissionsModule.fetchThreadPermissions);

const profile: ProviderProfile = {
  id: "profile-1",
  name: "Test Profile",
  provider: "openai",
  apiKey: "test-key",
  model: "gpt-test",
  reasoningEnabled: true,
};

const modeConfig: ModeConfig = {
  id: "build",
  label: "Build",
  eyebrow: "Ship changes",
  instruction: "Be helpful.",
  placeholder: "Ask a question",
  suggestions: [],
};

const emptyPermissions: ThreadPermissionsBundle = {
  defaults: { mode: null, working_directories: [], rules: [] },
  overlay: { mode: null, working_directories: [], rules: [] },
  effective: { mode: null, working_directories: [], rules: [] },
};

function wrapper({ children }: { children: ReactNode }) {
  return (
    <MemoryRouter>
      <ThreadsProvider>{children}</ThreadsProvider>
    </MemoryRouter>
  );
}

function renderUseChat() {
  const setThreadPermissions = vi.fn();
  const setStatus = vi.fn();
  const setError = vi.fn();

  const hook = renderHook(
    () => {
      const { threads } = useThreads();
      const pendingRetriesRef = useRef({});
      const chat = useChat({
        activeThread: null,
        activeProfile: profile,
        activeProfileId: profile.id,
        activeModel: profile.model,
        activeMode: "build",
        activeBackendMode: "local",
        activeLocalRootDir: "W:/workspace",
        modeConfig,
        isUploading: false,
        pendingRetriesRef,
        threadPermissions: null,
        setThreadPermissions,
        setStatus,
        setError,
      });
      return { chat, threads };
    },
    { wrapper },
  );

  return { ...hook, setThreadPermissions, setStatus, setError };
}

function getSubmittedThread(threads: ReturnType<typeof renderUseChat>["result"]["current"]["threads"]) {
  expect(threads).toHaveLength(1);
  return threads[0];
}

function getUserMessage(threads: ReturnType<typeof renderUseChat>["result"]["current"]["threads"]) {
  const thread = getSubmittedThread(threads);
  expect(thread.messages[0]?.role).toBe("user");
  return thread.messages[0];
}

function getAssistantMessage(threads: ReturnType<typeof renderUseChat>["result"]["current"]["threads"]) {
  const thread = getSubmittedThread(threads);
  expect(thread.messages[1]?.role).toBe("assistant");
  return thread.messages[1];
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  ensureAuthTokenMock.mockResolvedValue("token");
  fetchBackendThreadsMock.mockImplementation(
    () => new Promise(() => undefined),
  );
  createRemoteThreadMock.mockResolvedValue("thread_123");
  fetchThreadPermissionsMock.mockResolvedValue(emptyPermissions);
  updateBackendThreadMock.mockResolvedValue({
    id: "thread_123",
    title: "Thread",
    model: profile.model,
    mode: "build",
    messages: [],
    attachments: [],
    updatedAt: new Date().toISOString(),
  });
  generateTitleMock.mockResolvedValue({});
  generateFollowUpsMock.mockResolvedValue({ follow_ups: [] });
});

afterEach(() => {
  localStorage.clear();
});

describe("useChat optimistic acknowledgement", () => {
  it("clears optimistic when run_id arrives before content", async () => {
    streamChatMock.mockImplementation(async ({ onRunId }) => {
      onRunId?.("run-123");
    });

    const { result } = renderUseChat();

    act(() => {
      result.current.chat.setDraft("Check run id");
    });

    await act(async () => {
      await result.current.chat.handleSubmit();
    });

    await waitFor(() => {
      expect(getUserMessage(result.current.threads).optimistic).toBe(false);
    });
  });

  it("clears optimistic on the first tool event without content", async () => {
    streamChatMock.mockImplementation(async ({ onToolEvent }) => {
      const startEvent: ToolEvent = {
        step_id: "step_tool_tool-1",
        tool_call_id: "tool-1",
        name: "powershell",
        phase: "start",
        input: { command: "Get-Location" },
        summary: "List current working directory",
      };
      const endEvent: ToolEvent = {
        step_id: "step_tool_tool-1",
        tool_call_id: "tool-1",
        name: "powershell",
        phase: "end",
        output: "Exit code: 0",
        summary: "Exit code: 0",
      };
      onToolEvent?.(startEvent);
      onToolEvent?.(endEvent);
    });

    const { result } = renderUseChat();

    act(() => {
      result.current.chat.setDraft("Run a tool");
    });

    await act(async () => {
      await result.current.chat.handleSubmit();
    });

    await waitFor(() => {
      expect(getUserMessage(result.current.threads).optimistic).toBe(false);
    });

    expect(getAssistantMessage(result.current.threads).runSteps).toHaveLength(1);
    expect(getAssistantMessage(result.current.threads).runSteps?.[0]?.id).toBe("step_tool_tool-1");
    expect(getAssistantMessage(result.current.threads).runSteps?.[0]?.summary).toBe("List current working directory");
    expect(getAssistantMessage(result.current.threads).workspaceFrames?.[0]?.summary).toBe("List current working directory");
  });

  it("keeps tool run steps when tool events do not include tool_call_id", async () => {
    streamChatMock.mockImplementation(async ({ onToolEvent }) => {
      const startEvent: ToolEvent = {
        name: "powershell",
        phase: "start",
        input: { command: "Get-Location" },
      };
      const endEvent: ToolEvent = {
        name: "powershell",
        phase: "end",
        output: "Exit code: 0",
      };
      onToolEvent?.(startEvent);
      onToolEvent?.(endEvent);
    });

    const { result } = renderUseChat();

    act(() => {
      result.current.chat.setDraft("Run a tool without an id");
    });

    await act(async () => {
      await result.current.chat.handleSubmit();
    });

    await waitFor(() => {
      expect(getUserMessage(result.current.threads).optimistic).toBe(false);
    });

    const runSteps = getAssistantMessage(result.current.threads).runSteps ?? [];
    expect(runSteps).toHaveLength(1);
    expect(runSteps[0]?.toolName).toBe("powershell");
    expect(runSteps[0]?.status).toBe("completed");
  });

  it("keeps output artifact metadata on run steps and workspace frames", async () => {
    streamChatMock.mockImplementation(async ({ onToolEvent }) => {
      onToolEvent?.({
        step_id: "step_tool_tool-artifact",
        tool_call_id: "tool-artifact",
        name: "present_output_file",
        phase: "start",
        input: { path: "report.xlsx" },
      });
      onToolEvent?.({
        step_id: "step_tool_tool-artifact",
        tool_call_id: "tool-artifact",
        name: "present_output_file",
        phase: "end",
        output: "Presented output file: report.xlsx",
        artifact: {
          file_id: "file_1",
          filename: "report.xlsx",
          content_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          size: 123,
          artifact_type: "spreadsheet",
          title: "Q1 report",
          description: "Final workbook",
          content_url: "/api/files/file_1/content",
        },
      });
    });

    const { result } = renderUseChat();

    act(() => {
      result.current.chat.setDraft("Create a report");
    });

    await act(async () => {
      await result.current.chat.handleSubmit();
    });

    await waitFor(() => {
      expect(getUserMessage(result.current.threads).optimistic).toBe(false);
    });

    const assistant = getAssistantMessage(result.current.threads);
    expect(assistant.runSteps?.[0]?.artifact?.file_id).toBe("file_1");
    expect(assistant.workspaceFrames?.[0]?.artifact?.title).toBe("Q1 report");
  });

  it("reuses the same streamed tool block when a tool completes before the run finishes", async () => {
    let releaseStream!: () => void;
    const streamPending = new Promise<void>((resolve) => {
      releaseStream = resolve;
    });

    streamChatMock.mockImplementation(async ({ onToolEvent }) => {
      onToolEvent?.({
        step_id: "step_tool_tool-1",
        tool_call_id: "tool-1",
        name: "editor",
        phase: "start",
        input: { file_path: "hello.py" },
        summary: "Create hello.py",
      });
      onToolEvent?.({
        step_id: "step_tool_tool-1",
        tool_call_id: "tool-1",
        name: "editor",
        phase: "end",
        output: "Created hello.py",
        summary: "Create hello.py",
      });
      await streamPending;
    });

    const { result } = renderUseChat();

    act(() => {
      result.current.chat.setDraft("Create hello.py");
    });

    let submitPromise!: Promise<void>;
    await act(async () => {
      submitPromise = result.current.chat.handleSubmit();
      await Promise.resolve();
    });

    await waitFor(() => {
      const assistant = getAssistantMessage(result.current.threads);
      expect(assistant.status).toBe("streaming");
      expect(assistant.runSteps).toHaveLength(1);
      expect(assistant.runSteps?.[0]?.status).toBe("completed");
      expect(assistant.streamItems?.filter((item) => item.type === "run_step")).toHaveLength(1);
      expect(assistant.workspaceFrames).toHaveLength(1);
      expect(assistant.workspaceFrames?.[0]?.status).toBe("completed");
    });

    releaseStream();

    await act(async () => {
      await submitPromise;
    });
  });

  it("clears optimistic on reasoning before content", async () => {
    streamChatMock.mockImplementation(async ({ onReasoning }) => {
      onReasoning("Thinking through the problem");
    });

    const { result } = renderUseChat();

    act(() => {
      result.current.chat.setDraft("Think first");
    });

    await act(async () => {
      await result.current.chat.handleSubmit();
    });

    await waitFor(() => {
      expect(getUserMessage(result.current.threads).optimistic).toBe(false);
    });

    expect(getAssistantMessage(result.current.threads).reasoning).toContain("Thinking through the problem");
  });

  it("clears optimistic and keeps requires_action for permission-first runs", async () => {
    const permissionRequest: PermissionRequest = {
      behavior: "ask",
      reason: "Need approval to edit a file",
      tool_name: "filesystem",
    };

    streamChatMock.mockImplementation(async ({ onPermissionRequest }) => {
      onPermissionRequest(permissionRequest);
    });

    const { result } = renderUseChat();

    act(() => {
      result.current.chat.setDraft("Edit a file");
    });

    await act(async () => {
      await result.current.chat.handleSubmit();
    });

    await waitFor(() => {
      expect(getUserMessage(result.current.threads).optimistic).toBe(false);
    });

    const thread = getSubmittedThread(result.current.threads);
    expect(thread.status).toBe("requires_action");
    expect(getAssistantMessage(result.current.threads).permissionRequest).toEqual(permissionRequest);
  });

  it("clears optimistic and keeps requires_action for ask-user-first runs", async () => {
    const askUserRequest: AskUserRequest = {
      behavior: "ask_user",
      questions: [
        {
          header: "Choice",
          question: "Which option?",
          options: [
            { label: "A", description: "Option A" },
          ],
        },
      ],
    };

    streamChatMock.mockImplementation(async ({ onAskUserRequest }) => {
      onAskUserRequest?.(askUserRequest);
    });

    const { result } = renderUseChat();

    act(() => {
      result.current.chat.setDraft("Ask me first");
    });

    await act(async () => {
      await result.current.chat.handleSubmit();
    });

    await waitFor(() => {
      expect(getUserMessage(result.current.threads).optimistic).toBe(false);
    });

    const thread = getSubmittedThread(result.current.threads);
    expect(thread.status).toBe("requires_action");
    expect(getAssistantMessage(result.current.threads).askUserRequest).toEqual(askUserRequest);
  });

  it("clears optimistic when the request is aborted before the first stream delta", async () => {
    streamChatMock.mockImplementation(
      async ({ signal }) =>
        new Promise<void>((_, reject) => {
          if (signal.aborted) {
            reject(new DOMException("Aborted", "AbortError"));
            return;
          }
          signal.addEventListener(
            "abort",
            () => reject(new DOMException("Aborted", "AbortError")),
            { once: true },
          );
        }),
    );

    const { result } = renderUseChat();

    act(() => {
      result.current.chat.setDraft("Abort before the first event");
    });

    const submitPromise = act(async () => {
      const pendingSubmit = result.current.chat.handleSubmit();
      result.current.chat.handleStop();
      await pendingSubmit;
    });

    await submitPromise;

    await waitFor(() => {
      expect(getUserMessage(result.current.threads).optimistic).toBe(false);
    });

    expect(getAssistantMessage(result.current.threads).status).toBe("interrupted");
  });
});
