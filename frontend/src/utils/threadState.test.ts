import { describe, expect, it } from "vitest";
import type { ChatThread } from "../types";
import { mergeHydratedThreads } from "./threadState";

function buildThread(overrides: Partial<ChatThread>): ChatThread {
  return {
    id: "thread_123",
    remoteId: "thread_123",
    title: "Thread",
    model: "gpt-test",
    mode: "build",
    messages: [],
    attachments: [],
    updatedAt: "2026-05-07T00:00:00.000Z",
    ...overrides,
  };
}

describe("mergeHydratedThreads", () => {
  it("reconciles once stale optimistic state is cleared", () => {
    const localWithOptimistic = buildThread({
      updatedAt: "2026-05-07T00:00:01.000Z",
      messages: [
        {
          id: "msg-user",
          role: "user",
          content: "Do the thing",
          createdAt: "2026-05-07T00:00:00.000Z",
          optimistic: true,
        },
      ],
    });
    const serverThread = buildThread({
      updatedAt: "2026-05-07T00:00:02.000Z",
      messages: [
        {
          id: "msg-user",
          role: "user",
          content: "Do the thing",
          createdAt: "2026-05-07T00:00:00.000Z",
        },
        {
          id: "msg-assistant",
          role: "assistant",
          content: "",
          createdAt: "2026-05-07T00:00:01.000Z",
          status: "done",
        },
      ],
      status: "idle",
    });

    expect(mergeHydratedThreads([localWithOptimistic], [serverThread])[0].messages).toEqual(
      localWithOptimistic.messages,
    );

    const clearedLocal = buildThread({
      ...localWithOptimistic,
      messages: [
        {
          ...localWithOptimistic.messages[0],
          optimistic: false,
        },
      ],
    });

    expect(mergeHydratedThreads([clearedLocal], [serverThread])[0].messages).toEqual(
      serverThread.messages,
    );
  });

  it("still treats permission-first local state as live after optimistic is cleared", () => {
    const localPermissionThread = buildThread({
      updatedAt: "2026-05-07T00:00:01.000Z",
      status: "requires_action",
      messages: [
        {
          id: "msg-user",
          role: "user",
          content: "Edit a file",
          createdAt: "2026-05-07T00:00:00.000Z",
          optimistic: false,
        },
        {
          id: "msg-assistant",
          role: "assistant",
          content: "",
          createdAt: "2026-05-07T00:00:01.000Z",
          status: "done",
          permissionRequest: {
            behavior: "ask",
            reason: "Need approval",
          },
        },
      ],
    });
    const serverThread = buildThread({
      updatedAt: "2026-05-07T00:00:02.000Z",
      status: "idle",
      messages: [
        {
          id: "msg-user",
          role: "user",
          content: "Edit a file",
          createdAt: "2026-05-07T00:00:00.000Z",
        },
      ],
    });

    expect(mergeHydratedThreads([localPermissionThread], [serverThread])[0]).toEqual(
      localPermissionThread,
    );
  });

  it("still treats ask-user local state as live after optimistic is cleared", () => {
    const localAskUserThread = buildThread({
      updatedAt: "2026-05-07T00:00:01.000Z",
      status: "requires_action",
      messages: [
        {
          id: "msg-user",
          role: "user",
          content: "Ask me something",
          createdAt: "2026-05-07T00:00:00.000Z",
          optimistic: false,
        },
        {
          id: "msg-assistant",
          role: "assistant",
          content: "",
          createdAt: "2026-05-07T00:00:01.000Z",
          status: "done",
          askUserRequest: {
            behavior: "ask_user",
            questions: [
              {
                header: "Choice",
                question: "Pick one",
                options: [{ label: "A", description: "Option A" }],
              },
            ],
          },
        },
      ],
    });
    const serverThread = buildThread({
      updatedAt: "2026-05-07T00:00:02.000Z",
      status: "idle",
      messages: [
        {
          id: "msg-user",
          role: "user",
          content: "Ask me something",
          createdAt: "2026-05-07T00:00:00.000Z",
        },
      ],
    });

    expect(mergeHydratedThreads([localAskUserThread], [serverThread])[0]).toEqual(
      localAskUserThread,
    );
  });

  it("prefers server messages when hydration has grouped tool frames", () => {
    const localSplitToolThread = buildThread({
      updatedAt: "2026-05-07T00:00:03.000Z",
      messages: [
        {
          id: "msg-tool-1",
          role: "assistant",
          messageType: "tool_activity",
          content: "",
          createdAt: "2026-05-07T00:00:00.000Z",
          status: "done",
          workspaceFrames: [{ id: "frame-1", timestamp: "2026-05-07T00:00:00.000Z", toolName: "web_search", input: {} }],
        },
        {
          id: "msg-tool-2",
          role: "assistant",
          messageType: "tool_activity",
          content: "",
          createdAt: "2026-05-07T00:00:01.000Z",
          status: "done",
          workspaceFrames: [{ id: "frame-2", timestamp: "2026-05-07T00:00:01.000Z", toolName: "web_fetch", input: {} }],
        },
      ],
    });
    const serverGroupedThread = buildThread({
      updatedAt: "2026-05-07T00:00:02.000Z",
      messages: [
        {
          id: "msg-tools",
          role: "assistant",
          messageType: "tool_activity",
          content: "",
          createdAt: "2026-05-07T00:00:00.000Z",
          status: "done",
          workspaceFrames: [
            { id: "frame-1", timestamp: "2026-05-07T00:00:00.000Z", toolName: "web_search", input: {} },
            { id: "frame-2", timestamp: "2026-05-07T00:00:01.000Z", toolName: "web_fetch", input: {} },
          ],
        },
      ],
    });

    expect(mergeHydratedThreads([localSplitToolThread], [serverGroupedThread])[0].messages).toEqual(
      serverGroupedThread.messages,
    );
  });
});
