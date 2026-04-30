import { STORAGE_KEY, LEGACY_STORAGE_KEY } from "../constants";
import type {
  Attachment,
  ChatThread,
  ComposerMode,
  Message,
  MessageStreamItem,
  WorkspaceFrame,
} from "../types";

function createId(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}

function normalizeWorkspaceFrames(value: unknown): WorkspaceFrame[] {
  if (!Array.isArray(value)) return [];

  const frames = value
    .map((frame) => {
      if (!frame || typeof frame !== "object") return null;
      const raw = frame as Record<string, unknown>;

      const input =
        raw.input && typeof raw.input === "object" && !Array.isArray(raw.input)
          ? (raw.input as Record<string, unknown>)
          : {};

      return {
        id: typeof raw.id === "string" ? raw.id : createId("frame"),
        timestamp:
          typeof raw.timestamp === "string" ? raw.timestamp : new Date().toISOString(),
        toolName: typeof raw.toolName === "string" ? raw.toolName : "unknown",
        input,
        ...(typeof raw.output === "string" ? { output: raw.output } : {}),
        ...(raw.status === "pending" ||
        raw.status === "in_progress" ||
        raw.status === "completed" ||
        raw.status === "failed"
          ? { status: raw.status }
          : {}),
      } as WorkspaceFrame;
    })
    .filter((frame): frame is WorkspaceFrame => frame !== null);

  return frames;
}

function normalizeStreamItems(value: unknown): MessageStreamItem[] {
  if (!Array.isArray(value)) return [];

  return value
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const raw = item as Record<string, unknown>;
      const id = typeof raw.id === "string" ? raw.id : createId("stream");

      if (raw.type === "text" && typeof raw.content === "string") {
        return {
          id,
          type: "text" as const,
          content: raw.content,
        };
      }

      if (raw.type === "workspace_frame" && typeof raw.frameId === "string") {
        return {
          id,
          type: "workspace_frame" as const,
          frameId: raw.frameId,
        };
      }

      return null;
    })
    .filter((item): item is MessageStreamItem => item !== null);
}

function normalizeThread(thread: ChatThread | Record<string, unknown>): ChatThread {
  const rawMessages = Array.isArray(thread.messages)
    ? (thread.messages as Array<Record<string, unknown>>)
    : [];

  const messages: Message[] = rawMessages.map((msg) => ({
    ...(msg.permissionRequest && typeof msg.permissionRequest === "object"
      ? (() => {
          const permissionRequest = msg.permissionRequest as Record<string, unknown>;
          const behavior = permissionRequest.behavior;
          const reason = permissionRequest.reason;
          const toolName =
            typeof permissionRequest.tool_name === "string" ? permissionRequest.tool_name : undefined;
          const rawSuggestedMode =
            permissionRequest.suggested_mode ?? permissionRequest.suggested_thread_mode;
          const suggestedMode =
            rawSuggestedMode === "default" ||
            rawSuggestedMode === "accept_edits" ||
            rawSuggestedMode === "bypass_permissions" ||
            rawSuggestedMode === "dont_ask"
              ? rawSuggestedMode
              : undefined;
          return behavior === "ask" || behavior === "deny"
            ? typeof reason === "string"
              ? {
                  permissionRequest: {
                    behavior,
                    reason,
                    tool_name: toolName,
                    suggested_mode: suggestedMode,
                    subject:
                      permissionRequest.subject === "read" ||
                      permissionRequest.subject === "edit" ||
                      permissionRequest.subject === "bash" ||
                      permissionRequest.subject === "powershell" ||
                      permissionRequest.subject === "skill"
                        ? permissionRequest.subject
                        : undefined,
                    path: typeof permissionRequest.path === "string" ? permissionRequest.path : undefined,
                    command: typeof permissionRequest.command === "string" ? permissionRequest.command : undefined,
                    skill: typeof permissionRequest.skill === "string" ? permissionRequest.skill : undefined,
                    source: typeof permissionRequest.source === "string" ? permissionRequest.source : undefined,
                    server: typeof permissionRequest.server === "string" ? permissionRequest.server : undefined,
                    allowed_tools: Array.isArray(permissionRequest.allowed_tools)
                      ? permissionRequest.allowed_tools.filter((item): item is string => typeof item === "string")
                      : undefined,
                  },
                }
              : {}
            : {};
        })()
      : {}),
    id: typeof msg.id === "string" ? msg.id : createId("msg"),
    role:
      msg.role === "assistant" || msg.role === "system" || msg.role === "user"
        ? msg.role
        : "assistant",
    content: typeof msg.content === "string" ? msg.content : "",
    reasoning: typeof msg.reasoning === "string" ? msg.reasoning : "",
    toolEvents: Array.isArray(msg.toolEvents)
      ? msg.toolEvents.filter((x): x is string => typeof x === "string")
      : [],
    followUps: Array.isArray(msg.followUps)
      ? msg.followUps.filter((x): x is string => typeof x === "string")
      : [],
    createdAt: typeof msg.createdAt === "string" ? msg.createdAt : new Date().toISOString(),
    status:
      msg.status === "streaming" || msg.status === "error" || msg.status === "done"
        ? msg.status
        : "done",
    error: typeof msg.error === "string" ? msg.error : "",
    thinkingDuration: typeof msg.thinkingDuration === "number" ? msg.thinkingDuration : undefined,
    workspaceFrames: normalizeWorkspaceFrames(msg.workspaceFrames),
    streamItems: normalizeStreamItems(msg.streamItems),
  }));

  const rawAttachments = Array.isArray(thread.attachments)
    ? (thread.attachments as Array<Record<string, unknown>>)
    : [];

  const attachments: Attachment[] = rawAttachments
    .map((attachment) => ({
      id: typeof attachment.id === "string" ? attachment.id : "",
      filename: typeof attachment.filename === "string" ? attachment.filename : "",
      contentType:
        typeof attachment.contentType === "string" ? attachment.contentType : undefined,
      size: typeof attachment.size === "number" ? attachment.size : undefined,
    }))
    .filter((attachment) => attachment.id && attachment.filename);

  return {
    id: typeof thread.id === "string" ? thread.id : createId("chat"),
    remoteId: typeof thread.remoteId === "string" ? thread.remoteId : undefined,
    title: typeof thread.title === "string" ? thread.title : "New conversation",
    isFavorite: typeof thread.isFavorite === "boolean" ? thread.isFavorite : false,
    project: typeof thread.project === "string" ? thread.project : "",
    model: typeof thread.model === "string" ? thread.model : "",
    profileId: typeof thread.profileId === "string" ? thread.profileId : undefined,
    backendMode:
      thread.backendMode === "local" || thread.backendMode === "sandbox"
        ? thread.backendMode
        : "sandbox",
    localRootDir: typeof thread.localRootDir === "string" ? thread.localRootDir : "",
    mode:
      thread.mode === "build" || thread.mode === "review" || thread.mode === "explain"
        ? (thread.mode as ComposerMode)
        : "build",
    messages,
    attachments,
    updatedAt:
      typeof thread.updatedAt === "string" ? thread.updatedAt : new Date().toISOString(),
  };
}

export function loadThreads(): ChatThread[] {
  const raw = localStorage.getItem(STORAGE_KEY) ?? localStorage.getItem(LEGACY_STORAGE_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as Array<ChatThread | Record<string, unknown>>;
    return Array.isArray(parsed) ? parsed.map(normalizeThread) : [];
  } catch {
    return [];
  }
}

export function saveThreads(threads: ChatThread[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(threads));
}
