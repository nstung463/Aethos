import { API_BASE_URL } from "../constants";
import type { ExtensionSkill, MCPServerInfo } from "../types";
import { authFetch } from "./auth";

function qs(rootDir: string) {
  return `root_dir=${encodeURIComponent(rootDir)}`;
}

function normalizeSkill(raw: unknown): ExtensionSkill | null {
  if (!raw || typeof raw !== "object") return null;
  const item = raw as Record<string, unknown>;
  if (typeof item.name !== "string" || typeof item.description !== "string") return null;
  return {
    name: item.name,
    description: item.description,
    source: typeof item.source === "string" ? item.source : "unknown",
    loaded_from: typeof item.loaded_from === "string" ? item.loaded_from : "local",
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

export async function fetchSkills(rootDir: string, signal?: AbortSignal): Promise<ExtensionSkill[]> {
  const response = await authFetch(`${API_BASE_URL}/v1/extensions/skills?${qs(rootDir)}`, { signal });
  if (!response.ok) throw new Error(`Failed to load skills (${response.status})`);
  const payload = await response.json() as { skills?: unknown[] };
  return (payload.skills ?? []).map(normalizeSkill).filter((item): item is ExtensionSkill => item !== null);
}

export async function fetchSkill(rootDir: string, name: string, signal?: AbortSignal): Promise<ExtensionSkill> {
  const response = await authFetch(
    `${API_BASE_URL}/v1/extensions/skills/${encodeURIComponent(name)}?${qs(rootDir)}`,
    { signal },
  );
  if (!response.ok) throw new Error(`Failed to load skill (${response.status})`);
  const skill = normalizeSkill(await response.json());
  if (!skill) throw new Error("Invalid skill response");
  return skill;
}

export async function importSkillPackage(
  rootDir: string,
  file: File,
  overwrite: boolean,
  signal?: AbortSignal,
): Promise<ExtensionSkill> {
  const body = new FormData();
  body.append("file", file);
  const response = await authFetch(
    `${API_BASE_URL}/v1/extensions/skills/import?${qs(rootDir)}&overwrite=${overwrite ? "true" : "false"}`,
    { method: "POST", body, signal },
  );
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Skill import failed (${response.status})`);
  }
  const payload = await response.json() as { skill?: unknown };
  const skill = normalizeSkill(payload.skill);
  if (!skill) throw new Error("Invalid skill import response");
  return skill;
}

export async function deleteSkill(rootDir: string, name: string, signal?: AbortSignal) {
  const response = await authFetch(
    `${API_BASE_URL}/v1/extensions/skills/${encodeURIComponent(name)}?${qs(rootDir)}`,
    { method: "DELETE", signal },
  );
  if (!response.ok) throw new Error(`Failed to delete skill (${response.status})`);
}

export async function fetchMCPServers(signal?: AbortSignal): Promise<MCPServerInfo[]> {
  const response = await authFetch(`${API_BASE_URL}/v1/extensions/mcp/servers`, { signal });
  if (!response.ok) throw new Error(`Failed to load MCP servers (${response.status})`);
  const payload = await response.json() as { servers?: MCPServerInfo[] };
  return Array.isArray(payload.servers) ? payload.servers : [];
}

export async function fetchMCPInstructions(signal?: AbortSignal): Promise<string> {
  const response = await authFetch(`${API_BASE_URL}/v1/extensions/mcp/instructions`, { signal });
  if (!response.ok) throw new Error(`Failed to load MCP instructions (${response.status})`);
  const payload = await response.json() as { instructions?: string | null };
  return payload.instructions ?? "";
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
