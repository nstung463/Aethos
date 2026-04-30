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

export type PermissionSubject = "read" | "edit" | "bash" | "powershell" | "skill" | "mcp";
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
  skill?: string;
  source?: string;
  server?: string;
  allowed_tools?: string[];
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

export type MessageStreamReasoningItem = {
  id: string;
  type: "reasoning";
  content: string;
  startedAt?: number;
  thinkingDuration?: number; // seconds
};

export type MessageStreamItem = MessageStreamTextItem | MessageStreamWorkspaceItem | MessageStreamReasoningItem;

export type Message = {
  id: string;
  role: Role;
  content: string;
  reasoning?: string;
  toolEvents?: string[];
  followUps?: string[];
  createdAt: string;
  status?: "streaming" | "done" | "error" | "interrupted";
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
  status?: "idle" | "running" | "requires_action" | "interrupted" | string;
  activeRunId?: string | null;
  runStartedAt?: number | null;
  lastStopRunId?: string | null;
  lastStopReason?: string | null;
  lastInterruptedAt?: number | null;
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
      run_id?: string;
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
  | "security"
  | "extensions";

export type ExtensionSkill = {
  name: string;
  description: string;
  source: string;
  loaded_from: "local" | "mcp" | string;
  path?: string | null;
  root_dir?: string | null;
  server?: string | null;
  remote_name?: string | null;
  when_to_use?: string | null;
  allowed_tools: string[];
  argument_hint?: string | null;
  arguments: string[];
  model?: string | null;
  effort?: string | null;
  context?: string | null;
  agent?: string | null;
  paths: string[];
  raw_frontmatter?: Record<string, unknown>;
  body?: string | null;
  can_delete?: boolean;
};

export type ActivatedRule = {
  path: string;
  name: string;
  source: string;
  tokens: number;
};

export type ContextCategory = {
  key: string;
  label: string;
  tokens: number;
  percent: number;
  source?: string | null;
};

export type ContextGridSquare = {
  category_key: string;
  category_label: string;
  tokens: number;
};

export type ContextSuggestion = {
  severity: "info" | "warning" | string;
  title_key: string;
  detail_key: string;
  tokens: number;
};

export type ContextStatus = {
  context_window: number;
  used_tokens: number;
  percent_used: number;
  categories: ContextCategory[];
  grid_rows: ContextGridSquare[][];
  suggestions: ContextSuggestion[];
  activated_rules: ActivatedRule[];
  is_estimated: boolean;
};

export type MCPServerInfo = {
  name: string;
  transport?: string | null;
  url?: string | null;
  auth_url?: string | null;
  has_instructions: boolean;
  status: "ok" | "error" | "unknown" | string;
  error?: string | null;
  command?: string | null;
  args?: string[];
  source?: "env" | "settings" | string;
  can_remove?: boolean;
  tools: Record<string, unknown>[];
  resources: Record<string, unknown>[];
  prompts: Record<string, unknown>[];
  skill_prompts: Record<string, unknown>[];
};

export type MCPServerInput = {
  name: string;
  transport: string;
  url?: string | null;
  headers?: Record<string, string> | null;
  command?: string | null;
  args?: string[];
  env?: Record<string, string> | null;
  cwd?: string | null;
  auth_url?: string | null;
  instructions?: string | null;
};
