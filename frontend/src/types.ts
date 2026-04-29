export type ModelInfo = {
  id: string;
  object: string;
  owned_by?: string;
};

/** @deprecated use ProviderProfile */
export type UserApiKeys = {
  openrouter: string;
  anthropic: string;
  openai: string;
};

export type ProviderType =
  | "openrouter"
  | "anthropic"
  | "openai"
  | "deepseek"
  | "together"
  | "groq"
  | "xai"
  | "fireworks"
  | "perplexity"
  | "google_genai"
  | "bedrock"
  | "azure_openai"
  | "openai_compatible";

export type ReasoningEffort = "none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max";

export type ProviderProfile = {
  id: string;
  name: string;
  provider: ProviderType;
  apiKey: string;
  model: string;
  baseUrl?: string;
  deployment?: string;
  apiVersion?: string;
  reasoningEnabled?: boolean;
  reasoningEffort?: ReasoningEffort;
  thinkingBudgetTokens?: number;
  modelKwargs?: Record<string, unknown>;
};

export type Attachment = {
  id: string;
  filename: string;
  contentType?: string;
  size?: number;
};

export type PermissionMode =
  | "default"
  | "accept_edits"
  | "bypass_permissions"
  | "dont_ask";

export type PermissionSubject = "read" | "edit" | "bash" | "powershell";
export type PermissionBehavior = "allow" | "ask" | "deny";

export type PermissionRuleInput = {
  subject: PermissionSubject;
  behavior: PermissionBehavior;
  matcher?: string | null;
};

export type PermissionRequest = {
  behavior: "ask" | "deny";
  reason: string;
  tool_name?: string;
  suggested_mode?: PermissionMode;
  subject?: PermissionSubject;
  path?: string;
  command?: string;
};

export type AskUserOption = {
  label: string;
  description: string;
  preview?: string;
};

export type AskUserQuestion = {
  question: string;
  header: string;
  options: AskUserOption[];
  multi_select?: boolean;
};

export type AskUserRequest = {
  behavior: "ask_user";
  questions: AskUserQuestion[];
  metadata?: Record<string, string>;
};

export type PermissionProfile = {
  mode: PermissionMode | null;
  working_directories: string[];
  rules: PermissionRuleInput[];
};

export type ThreadPermissionsBundle = {
  defaults: PermissionProfile;
  overlay: PermissionProfile;
  effective: PermissionProfile;
};

export type Role = "user" | "assistant" | "system";
export type ComposerMode = "build" | "review" | "explain";

export type MessageStreamTextItem = {
  id: string;
  type: "text";
  content: string;
};

export type MessageStreamWorkspaceItem = {
  id: string;
  type: "workspace_frame";
  frameId: string;
};

export type MessageStreamItem = MessageStreamTextItem | MessageStreamWorkspaceItem;

export type Message = {
  id: string;
  role: Role;
  content: string;
  reasoning?: string;
  toolEvents?: string[];
  followUps?: string[];
  createdAt: string;
  status?: "streaming" | "done" | "error";
  error?: string;
  thinkingDuration?: number; // seconds
  permissionRequest?: PermissionRequest;
  askUserRequest?: AskUserRequest;
  workspaceFrames?: WorkspaceFrame[];
  streamItems?: MessageStreamItem[];
  /** True while the message is optimistically rendered before the server confirms it */
  optimistic?: boolean;
};

export type ChatThread = {
  id: string;
  remoteId?: string;
  title: string;
  isFavorite?: boolean;
  project?: string;
  model: string;
  profileId?: string;
  backendMode?: "sandbox" | "local";
  localRootDir?: string;
  mode: ComposerMode;
  messages: Message[];
  attachments: Attachment[];
  updatedAt: string;
};

export type ToolEventPhase = "start" | "end";

export type ToolEvent = {
  name: string;
  phase: ToolEventPhase;
  input?: Record<string, unknown>;
  output?: string;
};

export type WorkspaceFrameStatus = "pending" | "in_progress" | "completed" | "failed";

export type WorkspaceFrame = {
  id: string;
  timestamp: string;
  toolName: string;
  input: Record<string, unknown>;
  output?: string;
  status?: WorkspaceFrameStatus;
};

export type StreamChunk = {
  choices?: Array<{
    delta?: {
      content?: string;
      reasoning_content?: string;
      permission_request?: PermissionRequest | AskUserRequest;
      tool_event?: ToolEvent;
    };
    finish_reason?: string | null;
  }>;
};

export type ModeConfig = {
  id: ComposerMode;
  label: string;
  eyebrow: string;
  instruction: string;
  placeholder: string;
  suggestions: string[];
};

export type AppView = "chat" | "settings";

export type SettingsSection =
  | "general"
  | "appearance"
  | "profiles"
  | "model-settings"
  | "security";
