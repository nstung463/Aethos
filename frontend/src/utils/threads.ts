import type { ChatThread, ComposerMode, Message, MessageStreamItem } from "../types";
import { findRunStepById } from "./runSteps";

export function createId(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}

export function createEmptyThread(model = "", mode: ComposerMode = "build"): ChatThread {
  return {
    id: createId("chat"),
    remoteId: undefined,
    title: "New conversation",
    isFavorite: false,
    project: "",
    model,
    backendMode: "local",
    localRootDir: "",
    mode,
    messages: [],
    attachments: [],
    updatedAt: new Date().toISOString(),
  };
}

export function summarizeTitle(text: string) {
  const normalized = text.replace(/\s+/g, " ").trim();
  return normalized ? normalized.slice(0, 56) : "New conversation";
}

export function getRelativeGroupLabel(dateString: string) {
  const input = new Date(dateString);
  const today = new Date();
  const startOfInput = new Date(input.getFullYear(), input.getMonth(), input.getDate()).getTime();
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const diffDays = Math.round((startOfToday - startOfInput) / 86400000);

  if (diffDays <= 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return "This week";
  return input.toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

export function groupThreads(threads: ChatThread[]) {
  const groups: Array<{ label: string; items: ChatThread[] }> = [];
  threads
    .slice()
    .sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt))
    .forEach((thread) => {
      const label = getRelativeGroupLabel(thread.updatedAt);
      const current = groups.at(-1);
      if (!current || current.label !== label) {
        groups.push({ label, items: [thread] });
      } else {
        current.items.push(thread);
      }
    });
  return groups;
}

export function getLatestPreview(thread: ChatThread) {
  const latest = thread.messages.at(-1);
  if (!latest) return "Fresh conversation";
  if (latest.role === "assistant" && latest.status === "streaming") {
    return latest.content || "Thinking...";
  }
  return latest.content || "Fresh conversation";
}

function getReasoningDuration(startedAt?: number, now = Date.now()) {
  return startedAt ? Math.max(0, Math.round((now - startedAt) / 1000)) : undefined;
}

export function finalizeActiveReasoning(message: Message, now = Date.now()): Message {
  const streamItems = [...(message.streamItems ?? [])];
  const lastItem = streamItems.at(-1);

  if (lastItem?.type !== "reasoning" || lastItem.thinkingDuration !== undefined) {
    return message;
  }

  streamItems[streamItems.length - 1] = {
    ...lastItem,
    thinkingDuration: getReasoningDuration(lastItem.startedAt, now),
  };

  return { ...message, streamItems };
}

export function mergeReasoning(message: Message, chunk: string): Message {
  const thinkingText = chunk;
  const streamItems = [...(message.streamItems ?? [])];
  const lastItem = streamItems.at(-1);

  if (thinkingText) {
    if (lastItem?.type === "reasoning" && lastItem.thinkingDuration === undefined) {
      streamItems[streamItems.length - 1] = {
        ...lastItem,
        content: `${lastItem.content}${thinkingText}`,
      };
    } else {
      streamItems.push({
        id: createId("stream"),
        type: "reasoning",
        content: thinkingText,
        startedAt: Date.now(),
      });
    }
  }

  const nextReasoning = `${message.reasoning ?? ""}${thinkingText}`;

  return { ...message, reasoning: nextReasoning, streamItems };
}

export function appendMessageContent(message: Message, chunk: string): Message {
  const finalizedMessage = finalizeActiveReasoning(message);
  const streamItems = [...(finalizedMessage.streamItems ?? [])];
  const lastItem = streamItems.at(-1);

  if (lastItem?.type === "text") {
    streamItems[streamItems.length - 1] = {
      ...lastItem,
      content: `${lastItem.content}${chunk}`,
    };
  } else {
    streamItems.push({
      id: createId("stream"),
      type: "text",
      content: chunk,
    });
  }

  return {
    ...finalizedMessage,
    content: `${finalizedMessage.content}${chunk}`,
    streamItems,
  };
}

export function appendWorkspaceFrameItem(message: Message, frameId: string): Message {
  const finalizedMessage = finalizeActiveReasoning(message);

  return {
    ...finalizedMessage,
    streamItems: [
      ...(finalizedMessage.streamItems ?? []),
      {
        id: createId("stream"),
        type: "workspace_frame",
        frameId,
      },
    ],
  };
}

export function appendRunStepItem(message: Message, runStepId: string): Message {
  const finalizedMessage = finalizeActiveReasoning(message);
  const existingItems = finalizedMessage.streamItems ?? [];

  if (existingItems.some((item) => item.type === "run_step" && item.runStepId === runStepId)) {
    return finalizedMessage;
  }

  return {
    ...finalizedMessage,
    streamItems: [
      ...existingItems,
      {
        id: createId("stream"),
        type: "run_step",
        runStepId,
      },
    ],
  };
}

export function getOrderedMessageStreamItems(message: Message): MessageStreamItem[] {
  if ((message.streamItems?.length ?? 0) > 0) {
    const compacted: Array<MessageStreamItem | null> = [];
    const seenByKey = new Map<string, number>();

    for (const item of message.streamItems ?? []) {
      if (item.type !== "run_step") {
        compacted.push(item);
        continue;
      }

      const step = findRunStepById(message, item.runStepId);
      if (!step || step.kind !== "tool") {
        compacted.push(item);
        continue;
      }

      const dedupeKey = step.toolCallId ? `tool:${step.toolCallId}` : `step:${step.id}`;
      const previousIndex = seenByKey.get(dedupeKey);
      if (previousIndex !== undefined) {
        compacted[previousIndex] = {
          ...item,
          runStepId: step.id,
        };
        continue;
      }

      seenByKey.set(dedupeKey, compacted.length);
      compacted.push({
        ...item,
        runStepId: step.id,
      });
    }

    return compacted.filter((item): item is MessageStreamItem => item !== null);
  }

  const items: MessageStreamItem[] = [];
  if (message.content) {
    items.push({
      id: createId("stream"),
      type: "text",
      content: message.content,
    });
  }

  for (const frame of message.workspaceFrames ?? []) {
    items.push({
      id: createId("stream"),
      type: "workspace_frame",
      frameId: frame.id,
    });
  }

  if (items.length === 0) {
    for (const step of message.runSteps ?? []) {
      if (step.kind !== "tool") continue;
      items.push({
        id: createId("stream"),
        type: "run_step",
        runStepId: step.id,
      });
    }
  }

  return items;
}

export function parsePermissionPromptFromContent(content: string) {
  const trimmed = content.trim();
  const exact = trimmed.match(/^Permission (ask|deny):\s*(.+)$/is);
  if (exact) {
    return {
      behavior: exact[1] === "ask" ? ("ask" as const) : ("deny" as const),
      reason: exact[2].trim(),
    };
  }

  if (/need your approval|would you like to proceed|approve/i.test(trimmed)) {
    return {
      behavior: "ask" as const,
      reason: trimmed,
    };
  }

  return null;
}

export function getToolLabel(input: string) {
  const match = input.match(/Using tool `([^`]+)`/);
  return match?.[1] ?? input;
}

export function getToolParams(input: string) {
  const normalized = input.trim();

  // Try new format: Using tool `name` with params: params_content
  const newMatch = normalized.match(/^Using tool `[^`]+` with params: (.+)$/);
  if (newMatch) {
    return newMatch[1].trim();
  }

  // Fallback to old format: Using tool `name`(params)
  const oldMatch = normalized.match(/^Using tool `([^`]+)`\(([\s\S]*)\)$/);
  return oldMatch?.[2]?.trim() ?? "";
}

export function formatToolParams(input: string, maxLength = 360) {
  const params = getToolParams(input);
  if (!params) return "No parameters";

  const compact = params.replace(/\s+/g, " ").trim();
  if (compact.length <= maxLength) return compact;
  return `${compact.slice(0, maxLength).trimEnd()}...`;
}

export function toApiMessages(messages: Message[], modeInstruction: string) {
  return [
    { role: "system" as const, content: modeInstruction },
    ...messages
      .filter((m) => {
        if (m.role === "system") return false;
        if (m.role === "user" && !m.content.trim()) return false;
        if (m.role === "assistant" && !m.content.trim()) return false;
        return true;
      })
      .map(({ role, content, reasoning }) => ({
        role,
        content,
        ...(reasoning?.trim() ? { reasoning_content: reasoning } : {}),
      })),
  ];
}
