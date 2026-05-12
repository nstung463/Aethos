import { API_BASE_URL } from "../constants";
import type {
  ConnectionAuthorizationPayload,
  ConnectionInfo,
  ConnectionTestPayload,
  ExtensionSkill,
  MCPJSONConfig,
  MCPServerInfo,
  MCPServerInput,
} from "../types";
import { authFetch } from "./auth";

function qs(rootDir?: string) {
  const trimmed = rootDir?.trim() ?? "";
  return trimmed ? `root_dir=${encodeURIComponent(trimmed)}` : "";
}

function withQuery(url: string, query?: string) {
  return query ? `${url}?${query}` : url;
}

function normalizeSkill(raw: unknown): ExtensionSkill | null {
  if (!raw || typeof raw !== "object") return null;
  const item = raw as Record<string, unknown>;
  if (typeof item.name !== "string" || typeof item.description !== "string") return null;
  return {
    name: item.name,
    description: item.description,
    source: typeof item.source === "string" ? item.source : "unknown",
    overridden_by_project: item.overridden_by_project === true,
    loaded_from: typeof item.loaded_from === "string" ? item.loaded_from : "local",
    aliases: Array.isArray(item.aliases)
      ? item.aliases.filter((value): value is string => typeof value === "string")
      : [],
    path: typeof item.path === "string" ? item.path : null,
    root_dir: typeof item.root_dir === "string" ? item.root_dir : null,
    server: typeof item.server === "string" ? item.server : null,
    remote_name: typeof item.remote_name === "string" ? item.remote_name : null,
    when_to_use: typeof item.when_to_use === "string" ? item.when_to_use : null,
    allowed_tools: Array.isArray(item.allowed_tools)
      ? item.allowed_tools.filter((value): value is string => typeof value === "string")
      : [],
    argument_hint: typeof item.argument_hint === "string" ? item.argument_hint : null,
    arguments: Array.isArray(item.arguments)
      ? item.arguments.filter((value): value is string => typeof value === "string")
      : [],
    model: typeof item.model === "string" ? item.model : null,
    effort: typeof item.effort === "string" ? item.effort : null,
    context: typeof item.context === "string" ? item.context : null,
    agent: typeof item.agent === "string" ? item.agent : null,
    paths: Array.isArray(item.paths)
      ? item.paths.filter((value): value is string => typeof value === "string")
      : [],
    raw_frontmatter:
      item.raw_frontmatter && typeof item.raw_frontmatter === "object"
        ? item.raw_frontmatter as Record<string, unknown>
        : {},
    body: typeof item.body === "string" ? item.body : null,
    can_delete: item.can_delete === true,
  };
}

export async function fetchSkills(rootDir?: string, signal?: AbortSignal): Promise<ExtensionSkill[]> {
  const response = await authFetch(withQuery(`${API_BASE_URL}/v1/extensions/skills`, qs(rootDir)), { signal });
  if (!response.ok) throw new Error(`Failed to load skills (${response.status})`);
  const payload = await response.json() as { skills?: unknown[] };
  return (payload.skills ?? []).map(normalizeSkill).filter((item): item is ExtensionSkill => item !== null);
}

export async function fetchSkill(name: string, rootDir?: string, signal?: AbortSignal): Promise<ExtensionSkill> {
  const response = await authFetch(
    withQuery(`${API_BASE_URL}/v1/extensions/skills/${encodeURIComponent(name)}`, qs(rootDir)),
    { signal },
  );
  if (!response.ok) throw new Error(`Failed to load skill (${response.status})`);
  const skill = normalizeSkill(await response.json());
  if (!skill) throw new Error("Invalid skill response");
  return skill;
}

export async function importSkillPackage(
  file: File,
  overwrite: boolean,
  scope: "user" | "project" = "user",
  rootDir?: string,
  signal?: AbortSignal,
): Promise<{ skill: ExtensionSkill; warnings: string[] }> {
  const body = new FormData();
  body.append("file", file);
  const params = new URLSearchParams();
  if (rootDir?.trim()) params.set("root_dir", rootDir.trim());
  params.set("overwrite", overwrite ? "true" : "false");
  params.set("scope", scope);
  const response = await authFetch(
    withQuery(`${API_BASE_URL}/v1/extensions/skills/import`, params.toString()),
    { method: "POST", body, signal },
  );
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Skill import failed (${response.status})`);
  }
  const payload = await response.json() as { skill?: unknown };
  const skill = normalizeSkill(payload.skill);
  if (!skill) throw new Error("Invalid skill import response");
  return {
    skill,
    warnings: Array.isArray((payload as { warnings?: unknown[] }).warnings)
      ? ((payload as { warnings?: unknown[] }).warnings?.filter((item): item is string => typeof item === "string") ?? [])
      : [],
  };
}

export async function deleteSkill(name: string, rootDir?: string, signal?: AbortSignal) {
  const response = await authFetch(
    withQuery(`${API_BASE_URL}/v1/extensions/skills/${encodeURIComponent(name)}`, qs(rootDir)),
    { method: "DELETE", signal },
  );
  if (!response.ok) throw new Error(`Failed to delete skill (${response.status})`);
}

export async function fetchMCPServers(rootDir?: string, signal?: AbortSignal): Promise<MCPServerInfo[]> {
  const response = await authFetch(withQuery(`${API_BASE_URL}/v1/extensions/mcp/servers`, qs(rootDir)), { signal });
  if (!response.ok) throw new Error(`Failed to load MCP servers (${response.status})`);
  const payload = await response.json() as { servers?: MCPServerInfo[] };
  return Array.isArray(payload.servers) ? payload.servers : [];
}

export async function fetchMCPInstructions(rootDir?: string, signal?: AbortSignal): Promise<string> {
  const response = await authFetch(withQuery(`${API_BASE_URL}/v1/extensions/mcp/instructions`, qs(rootDir)), { signal });
  if (!response.ok) throw new Error(`Failed to load MCP instructions (${response.status})`);
  const payload = await response.json() as { instructions?: string | null };
  return payload.instructions ?? "";
}

export async function fetchMCPConfig(
  scope: "user" | "project" = "user",
  rootDir?: string,
  signal?: AbortSignal,
): Promise<MCPJSONConfig> {
  const params = new URLSearchParams();
  params.set("scope", scope);
  if (scope === "project" && rootDir?.trim()) params.set("root_dir", rootDir.trim());
  const response = await authFetch(withQuery(`${API_BASE_URL}/v1/extensions/mcp/config`, params.toString()), { signal });
  if (!response.ok) throw new Error(`Failed to load MCP config (${response.status})`);
  const payload = await response.json() as Partial<MCPJSONConfig>;
  return {
    path: typeof payload.path === "string" ? payload.path : "~/.aethos/settings.json",
    content: typeof payload.content === "string" ? payload.content : "{\n  \"mcpServers\": {}\n}",
    scope: typeof payload.scope === "string" ? payload.scope : scope,
  };
}

export async function saveMCPConfig(
  content: string,
  scope: "user" | "project" = "user",
  rootDir?: string,
  signal?: AbortSignal,
): Promise<MCPJSONConfig> {
  const params = new URLSearchParams();
  params.set("scope", scope);
  if (scope === "project" && rootDir?.trim()) params.set("root_dir", rootDir.trim());
  const response = await authFetch(withQuery(`${API_BASE_URL}/v1/extensions/mcp/config`, params.toString()), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
    signal,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Failed to save MCP config (${response.status})`);
  }
  const payload = await response.json() as Partial<MCPJSONConfig>;
  return {
    path: typeof payload.path === "string" ? payload.path : "~/.aethos/settings.json",
    content: typeof payload.content === "string" ? payload.content : content,
    scope: typeof payload.scope === "string" ? payload.scope : scope,
  };
}

export async function refreshMCPServers(signal?: AbortSignal): Promise<MCPServerInfo[]> {
  const response = await authFetch(`${API_BASE_URL}/v1/extensions/mcp/refresh`, {
    method: "POST",
    signal,
  });
  if (!response.ok) throw new Error(`Failed to refresh MCP servers (${response.status})`);
  const payload = await response.json() as { servers?: MCPServerInfo[] };
  return Array.isArray(payload.servers) ? payload.servers : [];
}

export async function addMCPServer(input: MCPServerInput, rootDir?: string, signal?: AbortSignal): Promise<MCPServerInfo[]> {
  const params = new URLSearchParams();
  if ((input.scope ?? "user") === "project" && rootDir?.trim()) params.set("root_dir", rootDir.trim());
  const response = await authFetch(withQuery(`${API_BASE_URL}/v1/extensions/mcp/servers`, params.toString()), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    signal,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Failed to add MCP server (${response.status})`);
  }
  const payload = await response.json() as { servers?: MCPServerInfo[] };
  return Array.isArray(payload.servers) ? payload.servers : [];
}

export async function removeMCPServer(
  name: string,
  scope: "user" | "project" = "user",
  rootDir?: string,
  signal?: AbortSignal,
): Promise<MCPServerInfo[]> {
  const params = new URLSearchParams();
  params.set("scope", scope);
  if (scope === "project" && rootDir?.trim()) params.set("root_dir", rootDir.trim());
  const response = await authFetch(
    withQuery(`${API_BASE_URL}/v1/extensions/mcp/servers/${encodeURIComponent(name)}`, params.toString()),
    { method: "DELETE", signal },
  );
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Failed to remove MCP server (${response.status})`);
  }
  const payload = await response.json() as { servers?: MCPServerInfo[] };
  return Array.isArray(payload.servers) ? payload.servers : [];
}

export async function fetchConnections(rootDir?: string, signal?: AbortSignal): Promise<ConnectionInfo[]> {
  const response = await authFetch(withQuery(`${API_BASE_URL}/v1/extensions/connections`, qs(rootDir)), { signal });
  if (!response.ok) throw new Error(`Failed to load connections (${response.status})`);
  const payload = await response.json() as { connections?: ConnectionInfo[] };
  return Array.isArray(payload.connections) ? payload.connections : [];
}

export async function authorizeConnection(
  provider: string,
  rootDir?: string,
  redirect_to?: string,
  signal?: AbortSignal,
): Promise<ConnectionAuthorizationPayload> {
  const response = await authFetch(withQuery(`${API_BASE_URL}/v1/extensions/connections/${encodeURIComponent(provider)}/authorize`, qs(rootDir)), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ redirect_to: redirect_to ?? null }),
    signal,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Failed to start ${provider} authorization (${response.status})`);
  }
  return await response.json() as ConnectionAuthorizationPayload;
}

export async function testConnection(connectionId: string, rootDir?: string, signal?: AbortSignal): Promise<ConnectionTestPayload> {
  const response = await authFetch(withQuery(`${API_BASE_URL}/v1/extensions/connections/${encodeURIComponent(connectionId)}/test`, qs(rootDir)), {
    method: "POST",
    signal,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Failed to test connection (${response.status})`);
  }
  return await response.json() as ConnectionTestPayload;
}

export async function deleteConnection(connectionId: string, rootDir?: string, signal?: AbortSignal): Promise<void> {
  const response = await authFetch(withQuery(`${API_BASE_URL}/v1/extensions/connections/${encodeURIComponent(connectionId)}`, qs(rootDir)), {
    method: "DELETE",
    signal,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Failed to delete connection (${response.status})`);
  }
}

export async function updateConnectionTools(
  connectionId: string,
  enabled: boolean,
  rootDir?: string,
  signal?: AbortSignal,
): Promise<ConnectionInfo> {
  const response = await authFetch(withQuery(`${API_BASE_URL}/v1/extensions/connections/${encodeURIComponent(connectionId)}/tools`, qs(rootDir)), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
    signal,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Failed to update connection tools (${response.status})`);
  }
  return await response.json() as ConnectionInfo;
}

export async function fetchConnectionScopes(connectionId: string, rootDir?: string, signal?: AbortSignal): Promise<string[]> {
  const response = await authFetch(withQuery(`${API_BASE_URL}/v1/extensions/connections/${encodeURIComponent(connectionId)}/scopes`, qs(rootDir)), { signal });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Failed to load connection scopes (${response.status})`);
  }
  const payload = await response.json() as { scopes?: string[] };
  return Array.isArray(payload.scopes) ? payload.scopes.filter((item): item is string => typeof item === "string") : [];
}
