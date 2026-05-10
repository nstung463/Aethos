import type { ChatThread } from "../types";

export function hasHydrationBlockingLocalState(thread: ChatThread) {
  return thread.messages.some(
    (message) => message.status === "streaming" || message.optimistic,
  );
}

export function hasLiveLocalState(thread: ChatThread) {
  return thread.messages.some(
    (message) =>
      message.status === "streaming" ||
      message.optimistic ||
      Boolean(message.permissionRequest) ||
      Boolean(message.askUserRequest),
  );
}

export function hasIncompleteWorkspaceFrames(thread: ChatThread) {
  return thread.messages.some((message) =>
    (message.workspaceFrames ?? []).some(
      (frame) => frame.status === "in_progress" || frame.status === "pending",
    ),
  );
}

function maxToolFramesPerMessage(thread: ChatThread) {
  return thread.messages.reduce((maxFrames, message) => {
    const frameCount = message.messageType === "tool_activity"
      ? message.workspaceFrames?.length ?? 0
      : (message.workspaceFrames ?? []).filter((frame) => frame.toolName).length;
    return Math.max(maxFrames, frameCount);
  }, 0);
}

export function mergeHydratedThreads(localThreads: ChatThread[], serverThreads: ChatThread[]) {
  const localById = new Map(localThreads.map((thread) => [thread.id, thread]));
  const merged = serverThreads.map((serverThread) => {
    const local = localById.get(serverThread.id);
    if (!local) return serverThread;
    if (hasLiveLocalState(local)) return local;
    const shouldPreferServerMessages =
      hasIncompleteWorkspaceFrames(local) &&
      serverThread.messages.length > 0 &&
      serverThread.status !== "running";
    const serverHasMoreGroupedToolFrames =
      maxToolFramesPerMessage(serverThread) > maxToolFramesPerMessage(local);
    if (Date.parse(local.updatedAt) > Date.parse(serverThread.updatedAt)) {
      return {
        ...serverThread,
        ...local,
        status: serverThread.status,
        activeRunId: serverThread.activeRunId,
        runStartedAt: serverThread.runStartedAt,
        lastStopRunId: serverThread.lastStopRunId,
        lastStopReason: serverThread.lastStopReason,
        lastInterruptedAt: serverThread.lastInterruptedAt,
        messages: shouldPreferServerMessages || serverHasMoreGroupedToolFrames
          ? serverThread.messages
          : local.messages.length > 0
            ? local.messages
            : serverThread.messages,
      };
    }
    return {
      ...local,
      ...serverThread,
      messages: shouldPreferServerMessages
        ? serverThread.messages
        : serverThread.messages.length > 0
          ? serverThread.messages
          : local.messages,
    };
  });

  const serverIds = new Set(serverThreads.map((thread) => thread.id));
  const localOnly = localThreads.filter((thread) => {
    if (serverIds.has(thread.id)) return false;
    if (thread.id.startsWith("thread_") && !hasLiveLocalState(thread)) return false;
    return true;
  });
  return [...merged, ...localOnly];
}
