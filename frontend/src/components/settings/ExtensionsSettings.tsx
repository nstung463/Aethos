import { ChangeEvent, DragEvent, useEffect, useId, useMemo, useRef, useState } from "react";
import JSZip from "jszip";
import { Braces, Cable, Ellipsis, ExternalLink, FileArchive, Plus, PlugZap, Puzzle, RefreshCcw, Search, ShieldAlert, Trash2, Upload, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ExtensionSkill, MCPJSONConfig, MCPServerInfo, MCPServerInput } from "../../types";
import {
  addMCPServer,
  deleteSkill,
  fetchMCPConfig,
  fetchMCPInstructions,
  fetchMCPServers,
  fetchSkill,
  fetchSkills,
  importSkillPackage,
  refreshMCPServers,
  removeMCPServer,
  saveMCPConfig,
} from "../../utils/extensions";
import StyledSelect from "./StyledSelect";

type SkillSourceFilter = "all" | "aethos_project" | "aethos_user";
type SkillUploadScope = "user" | "project";
type MCPScopeFilter = "all" | "project" | "user";
type MCPEditScope = "project" | "user";

const TRANSPORTS = ["http", "streamable_http", "stdio", "sse", "websocket"] as const;
type Transport = typeof TRANSPORTS[number];


function badgeClassName(kind: "neutral" | "risk" | "success" = "neutral") {
  if (kind === "risk") {
    return "border-[var(--danger-border)] bg-[var(--danger-bg)] text-[var(--danger)]";
  }
  if (kind === "success") {
    return "border-[var(--success)]/30 bg-[var(--success-bg)] text-[var(--success)]";
  }
  return "border-[var(--border-subtle)] bg-[var(--surface-soft)] text-[var(--text-soft)]";
}

function riskBadges(skill: ExtensionSkill) {
  const badges: Array<{ key: string; label: string; kind?: "neutral" | "risk" | "success" }> = [
    {
      key: skill.loaded_from === "mcp" ? "mcp" : "local",
      label: skill.loaded_from === "mcp" ? "MCP" : "Local",
      kind: skill.loaded_from === "mcp" ? "risk" : "success",
    },
  ];
  if (skill.allowed_tools.length > 0) badges.push({ key: "allowed-tools", label: "allowed-tools", kind: "risk" });
  if (skill.context === "fork") badges.push({ key: "fork", label: "context: fork", kind: "risk" });
  return badges;
}

function inputClass(extraClass = "") {
  return `w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--border-strong)] placeholder:text-[var(--text-faint)] ${extraClass}`;
}

function labelClass() {
  return "block text-xs font-medium text-[var(--text-secondary)] mb-1";
}

function nestedModalShellClass() {
  return "absolute inset-0 z-[100] flex items-center justify-center bg-black/50 p-3 backdrop-blur-sm sm:p-4";
}

function nestedModalCardClass() {
  return "flex w-full max-w-lg min-h-0 max-h-full flex-col overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] shadow-2xl";
}

interface AddServerModalProps {
  rootDir: string;
  onClose: () => void;
  onAdded: (servers: MCPServerInfo[]) => void;
}

function AddServerModal({ rootDir, onClose, onAdded }: AddServerModalProps) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [transport, setTransport] = useState<Transport>("http");
  const [url, setUrl] = useState("");
  const [command, setCommand] = useState("");
  const [args, setArgs] = useState("");
  const [authUrl, setAuthUrl] = useState("");
  const [instructions, setInstructions] = useState("");
  const [scope, setScope] = useState<"user" | "project">(rootDir.trim() ? "project" : "user");
  const [status, setStatus] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const needsUrl = transport === "http" || transport === "streamable_http" || transport === "sse" || transport === "websocket";
  const needsCommand = transport === "stdio";
  const needsAuthUrl = transport === "http" || transport === "streamable_http";

  async function handleSubmit() {
    if (!name.trim()) { setStatus(t("extensions.mcpServerNameRequired", "Server name is required.")); return; }
    if (needsUrl && !url.trim()) { setStatus(t("extensions.mcpUrlRequired", "URL is required for this transport.")); return; }
    if (needsCommand && !command.trim()) { setStatus(t("extensions.mcpCommandRequired", "Command is required for stdio transport.")); return; }

    const input: MCPServerInput = {
      name: name.trim(),
      transport,
      url: needsUrl ? url.trim() || null : null,
      command: needsCommand ? command.trim() || null : null,
      args: needsCommand && args.trim() ? args.split(",").map((a) => a.trim()).filter(Boolean) : undefined,
      auth_url: needsAuthUrl && authUrl.trim() ? authUrl.trim() : null,
      instructions: instructions.trim() || null,
      scope,
    };

    setSubmitting(true);
    setStatus(t("extensions.adding", "Adding..."));
    try {
      const servers = await addMCPServer(input, rootDir.trim() || undefined);
      onAdded(servers);
      onClose();
    } catch (err) {
      setStatus(err instanceof Error ? err.message : t("extensions.mcpAddFailed", "Failed to add server."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={nestedModalShellClass()}>
      <div className={nestedModalCardClass()}>
        <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-5 py-4">
          <h2 className="text-base font-semibold text-[var(--text-primary)]">{t("extensions.addMcpServerTitle", "Add MCP server")}</h2>
          <button type="button" onClick={onClose} className="rounded-lg p-2 text-[var(--text-soft)] hover:bg-[var(--surface-hover)]">
            <X size={16} strokeWidth={1.8} />
          </button>
        </div>

        <div className="min-h-0 overflow-y-auto px-5 py-4">
          <div className="space-y-3">
          <div>
            <label className={labelClass()}>{t("extensions.mcpServerName", "Server name")}</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="my-server" className={inputClass()} />
          </div>

          <div>
            <label className={labelClass()}>{t("extensions.mcpTransport", "Transport")}</label>
            <StyledSelect
              value={transport}
              options={TRANSPORTS.map((tr) => ({ value: tr, label: tr }))}
              onValueChange={setTransport}
              label={t("extensions.mcpTransport", "Transport")}
            />
          </div>

          <div>
            <label className={labelClass()}>{t("extensions.scopeLabel", "Scope")}</label>
            <StyledSelect
              value={scope}
              options={[
                ...(rootDir.trim() ? [{ value: "project", label: t("extensions.scope.project", "Project") }] : []),
                { value: "user", label: t("extensions.scope.user", "User") },
              ]}
              onValueChange={(value) => setScope(value as "user" | "project")}
              label={t("extensions.scopeLabel", "Scope")}
            />
          </div>

          {needsUrl && (
            <div>
              <label className={labelClass()}>{t("extensions.mcpUrl", "URL")}</label>
              <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/mcp" className={inputClass()} />
            </div>
          )}

          {needsCommand && (
            <>
              <div>
                <label className={labelClass()}>{t("extensions.mcpCommand", "Command")}</label>
                <input value={command} onChange={(e) => setCommand(e.target.value)} placeholder="python" className={inputClass()} />
              </div>
              <div>
                <label className={labelClass()}>{t("extensions.mcpArgs", "Arguments")}</label>
                <input value={args} onChange={(e) => setArgs(e.target.value)} placeholder="/path/to/server.py, --port, 8080" className={inputClass()} />
                <p className="mt-1 text-[10px] text-[var(--text-faint)]">{t("extensions.mcpArgsHint", "Comma-separated")}</p>
              </div>
            </>
          )}

          {needsAuthUrl && (
            <div>
              <label className={labelClass()}>{t("extensions.mcpAuthUrl", "Auth URL (optional)")}</label>
              <input value={authUrl} onChange={(e) => setAuthUrl(e.target.value)} placeholder="https://example.com/login" className={inputClass()} />
            </div>
          )}

          <div>
            <label className={labelClass()}>{t("extensions.mcpInstructions", "Instructions (optional)")}</label>
            <textarea value={instructions} onChange={(e) => setInstructions(e.target.value)}
              placeholder={t("extensions.mcpInstructionsPlaceholder", "Usage hints injected into the system prompt...")}
              rows={3} className={inputClass("resize-none")} />
          </div>
        </div>
        </div>

        {status ? <p className="px-5 pb-1 text-sm text-[var(--text-secondary)]">{status}</p> : null}

        <div className="flex flex-wrap justify-end gap-2 border-t border-[var(--border-subtle)] px-5 py-4">
          <button type="button" onClick={onClose}
            className="rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-sm text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]">
            {t("settings.cancel", "Cancel")}
          </button>
          <button type="button" onClick={handleSubmit} disabled={submitting}
            className="rounded-xl bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50">
            {t("extensions.addMcpServer", "Add server")}
          </button>
        </div>
      </div>
    </div>
  );
}

interface EditMCPConfigModalProps {
  config: MCPJSONConfig;
  rootDir: string;
  scope: MCPEditScope;
  onClose: () => void;
  onSaved: (config: MCPJSONConfig) => void;
}

function EditMCPConfigModal({ config, rootDir, scope, onClose, onSaved }: EditMCPConfigModalProps) {
  const { t } = useTranslation();
  const [content, setContent] = useState(config.content);
  const [status, setStatus] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSave() {
    setSubmitting(true);
    setStatus(t("extensions.saving", "Saving..."));
    try {
      const saved = await saveMCPConfig(content, scope, rootDir.trim() || undefined);
      onSaved(saved);
      onClose();
    } catch (err) {
      setStatus(err instanceof Error ? err.message : t("extensions.mcpConfigSaveFailed", "Failed to save MCP config."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={nestedModalShellClass()}>
      <div className="flex w-full max-w-3xl min-h-0 max-h-full flex-col overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] shadow-2xl">
        <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-[var(--text-primary)]">
              {scope === "project"
                ? t("extensions.editProjectMcpJsonTitle", "Edit project MCP config")
                : t("extensions.editMcpJsonTitle", "Edit user MCP config")}
            </h2>
            <p className="truncate text-xs text-[var(--text-soft)]">{config.path}</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-2 text-[var(--text-soft)] hover:bg-[var(--surface-hover)]">
            <X size={16} strokeWidth={1.8} />
          </button>
        </div>

        <div className="min-h-0 overflow-y-auto px-5 py-4">
          <p className="mb-3 text-sm leading-6 text-[var(--text-secondary)]">
            {scope === "project"
              ? t("extensions.editProjectMcpJsonDesc", "Paste the MCP JSON managed for this project here. Aethos will validate it and save the mcpServers section into .aethos/settings.json in the selected workspace.")
              : t("extensions.editMcpJsonDesc", "Paste the MCP JSON managed for your user account here. Aethos will validate it and save the mcpServers section into ~/.aethos/settings.json.")}
          </p>
          <textarea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            rows={18}
            spellCheck={false}
            className={inputClass("min-h-[420px] resize-y font-mono text-xs leading-6")}
          />
        </div>

        {status ? <p className="px-5 pb-1 text-sm text-[var(--text-secondary)]">{status}</p> : null}

        <div className="flex flex-wrap justify-end gap-2 border-t border-[var(--border-subtle)] px-5 py-4">
          <button type="button" onClick={onClose} className="rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-sm text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]">
            {t("settings.cancel", "Cancel")}
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={submitting}
            className="rounded-xl bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {t("extensions.saveMcpJson", "Save MCP config")}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ExtensionsSettings({ rootDir }: { rootDir: string }) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<"skills" | "mcp">("skills");
  const [skills, setSkills] = useState<ExtensionSkill[]>([]);
  const [selectedSkillName, setSelectedSkillName] = useState("");
  const [selectedSkill, setSelectedSkill] = useState<ExtensionSkill | null>(null);
  const [skillQuery, setSkillQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState<SkillSourceFilter>("all");
  const [mcpServers, setMcpServers] = useState<MCPServerInfo[]>([]);
  const [mcpScopeFilter, setMcpScopeFilter] = useState<MCPScopeFilter>("all");
  const [mcpInstructions, setMcpInstructions] = useState("");
  const [mcpConfig, setMcpConfig] = useState<MCPJSONConfig>({ path: "~/.aethos/settings.json", content: "{\n  \"mcpServers\": {}\n}", scope: "user" });
  const [mcpUserConfig, setMcpUserConfig] = useState<MCPJSONConfig>({ path: "~/.aethos/settings.json", content: "{\n  \"mcpServers\": {}\n}", scope: "user" });
  const [mcpProjectConfig, setMcpProjectConfig] = useState<MCPJSONConfig>({ path: "", content: "{\n  \"mcpServers\": {}\n}", scope: "project" });
  const [editMcpConfigScope, setEditMcpConfigScope] = useState<MCPEditScope>("user");
  const [selectedServerName, setSelectedServerName] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [addServerOpen, setAddServerOpen] = useState(false);
  const [editMcpConfigOpen, setEditMcpConfigOpen] = useState(false);
  const [mcpActionsOpen, setMcpActionsOpen] = useState(false);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [overwrite, setOverwrite] = useState(false);
  const [uploadScope, setUploadScope] = useState<SkillUploadScope>("user");
  const [uploadStatus, setUploadStatus] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const mcpActionsRef = useRef<HTMLDivElement | null>(null);
  const mcpActionsMenuId = useId();

  useEffect(() => {
    if (!mcpActionsOpen) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (!mcpActionsRef.current?.contains(event.target as Node)) setMcpActionsOpen(false);
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMcpActionsOpen(false);
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [mcpActionsOpen]);

  async function loadSkills(signal?: AbortSignal) {
    const items = await fetchSkills(rootDir.trim() || undefined, signal);
    setSkills(items);
    setSelectedSkillName((current) => current || items[0]?.name || "");
  }

  useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true);
    setError("");
    Promise.all([
      loadSkills(controller.signal),
      fetchMCPServers(rootDir.trim() || undefined, controller.signal).then((items) => {
        setMcpServers(items);
        setSelectedServerName((current) => current || items[0]?.name || "");
      }),
      fetchMCPInstructions(rootDir.trim() || undefined, controller.signal).then(setMcpInstructions),
      fetchMCPConfig("user", undefined, controller.signal).then((cfg) => {
        setMcpUserConfig(cfg);
        if (editMcpConfigScope === "user") setMcpConfig(cfg);
      }),
      fetchMCPConfig("project", rootDir.trim() || undefined, controller.signal)
        .then((cfg) => {
          setMcpProjectConfig(cfg);
          if (editMcpConfigScope === "project") setMcpConfig(cfg);
        })
        .catch(() => {
          // Project scope may be unavailable when no workspace root is selected.
        }),
    ])
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof Error ? err.message : t("extensions.loadFailed", "Failed to load extensions."));
      })
      .finally(() => setIsLoading(false));
    return () => controller.abort();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editMcpConfigScope, rootDir, t]);

  useEffect(() => {
    setMcpConfig(editMcpConfigScope === "project" ? mcpProjectConfig : mcpUserConfig);
  }, [editMcpConfigScope, mcpProjectConfig, mcpUserConfig]);

  useEffect(() => {
    if (!selectedSkillName) {
      setSelectedSkill(null);
      return;
    }
    const controller = new AbortController();
    fetchSkill(selectedSkillName, rootDir.trim() || undefined, controller.signal)
      .then(setSelectedSkill)
      .catch(() => setSelectedSkill(skills.find((skill) => skill.name === selectedSkillName) ?? null));
    return () => controller.abort();
  }, [rootDir, selectedSkillName, skills]);

  const filteredSkills = useMemo(() => {
    const query = skillQuery.trim().toLowerCase();
    return skills.filter((skill) => {
      if (skill.loaded_from === "mcp" || skill.source === "mcp") return false;
      const matchesSource = sourceFilter === "all" || skill.source === sourceFilter;
      const matchesQuery =
        !query ||
        skill.name.toLowerCase().includes(query) ||
        skill.description.toLowerCase().includes(query) ||
        (skill.when_to_use ?? "").toLowerCase().includes(query);
      return matchesSource && matchesQuery;
    });
  }, [skillQuery, skills, sourceFilter]);

  const filteredMcpServers = useMemo(() => {
    if (mcpScopeFilter === "all") return mcpServers;
    return mcpServers.filter((server) => (server.scope || "") === mcpScopeFilter);
  }, [mcpScopeFilter, mcpServers]);

  const selectedServer = filteredMcpServers.find((server) => server.name === selectedServerName) ?? filteredMcpServers[0] ?? null;

  function handlePickFile(event: ChangeEvent<HTMLInputElement>) {
    setUploadFiles(Array.from(event.target.files ?? []));
    setUploadStatus("");
    event.target.value = "";
  }

  function handlePickFolders(event: ChangeEvent<HTMLInputElement>) {
    setUploadFiles(Array.from(event.target.files ?? []));
    setUploadStatus("");
    event.target.value = "";
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setUploadFiles(Array.from(event.dataTransfer.files ?? []));
    setUploadStatus("");
  }

  async function buildFolderUpload(folderName: string, files: File[]): Promise<File> {
    const archive = new JSZip();
    files.forEach((file) => {
      const relativePath = file.webkitRelativePath || file.name;
      const parts = relativePath.split("/").filter(Boolean);
      const innerPath = parts.length > 1 ? parts.slice(1).join("/") : file.name;
      archive.file(`${folderName}/${innerPath}`, file);
    });
    const blob = await archive.generateAsync({ type: "blob" });
    return new File([blob], `${folderName}.skill`, { type: "application/zip" });
  }

  async function buildUploadQueue(files: File[]): Promise<File[]> {
    const packageFiles: File[] = [];
    const folderGroups = new Map<string, File[]>();

    files.forEach((file) => {
      const relativePath = file.webkitRelativePath;
      if (!relativePath) {
        packageFiles.push(file);
        return;
      }
      const [folderName] = relativePath.split("/").filter(Boolean);
      if (!folderName) {
        packageFiles.push(file);
        return;
      }
      const group = folderGroups.get(folderName) ?? [];
      group.push(file);
      folderGroups.set(folderName, group);
    });

    const folderArchives = await Promise.all(
      Array.from(folderGroups.entries()).map(([folderName, groupFiles]) => buildFolderUpload(folderName, groupFiles)),
    );
    return [...packageFiles, ...folderArchives];
  }

  async function handleUpload() {
    if (uploadFiles.length === 0) return;
    const resolvedUploadScope = uploadScope === "project" && rootDir.trim() ? "project" : "user";
    try {
      const uploads = await buildUploadQueue(uploadFiles);
      if (resolvedUploadScope === "project") {
        const uploadNames = new Set<string>();
        for (const upload of uploads) {
          try {
            const archive = await JSZip.loadAsync(upload);
            const skillEntry = Object.values(archive.files).find((entry) => !entry.dir && entry.name.split("/").pop() === "SKILL.md");
            if (!skillEntry) continue;
            const content = await skillEntry.async("string");
            const name = content.match(/^---\s*\n[\s\S]*?^name:\s*['"]?([^'"\n]+)['"]?\s*$/m)?.[1]?.trim();
            if (name) uploadNames.add(name);
          } catch {
            continue;
          }
        }
        const overridesUserSkill = skills.some((skill) => skill.source === "aethos_user" && uploadNames.has(skill.name));
        if (overridesUserSkill && !window.confirm(t("extensions.confirmProjectSkillOverride", "This project skill will override your user skill in this project."))) {
          setUploadStatus("");
          return;
        }
      }
      const installed: string[] = [];
      const failures: string[] = [];
      const warnings: string[] = [];
      let lastInstalledSkillName = "";

      for (const [index, upload] of uploads.entries()) {
        setUploadStatus(
          t("extensions.uploadingSkillProgress", "Installing skill {{current}} of {{total}}...", {
            current: index + 1,
            total: uploads.length,
          }),
        );
        try {
          const result = await importSkillPackage(upload, overwrite, resolvedUploadScope, rootDir.trim() || undefined);
          installed.push(result.skill.name);
          lastInstalledSkillName = result.skill.name;
          warnings.push(...result.warnings);
        } catch (err) {
          const message = err instanceof Error ? err.message : t("extensions.uploadFailed", "Skill upload failed.");
          failures.push(`${upload.name}: ${message}`);
        }
      }

      await loadSkills();
      if (lastInstalledSkillName) {
        setSelectedSkillName(lastInstalledSkillName);
      }
      if (failures.length === 0) {
        const warningSuffix = warnings.length > 0
          ? ` ${t("extensions.uploadWarnings", "Warnings")}: ${warnings.join(" ")}`
          : "";
        setUploadStatus(
          t("extensions.skillInstalledCount", "{{count}} skill installed.", { count: installed.length }) + warningSuffix,
        );
        setUploadOpen(false);
      } else if (installed.length > 0) {
        setUploadStatus(
          t("extensions.skillInstalledPartial", "{{installed}} installed, {{failed}} failed.", {
            installed: installed.length,
            failed: failures.length,
          }) + ` ${failures.join(" ")}`
        );
      } else {
        setUploadStatus(failures.join(" "));
      }
      setUploadFiles([]);
      setOverwrite(false);
      setUploadScope("user");
    } catch (err) {
      setUploadStatus(err instanceof Error ? err.message : t("extensions.uploadFailed", "Skill upload failed."));
    }
  }

  async function handleDeleteSkill(skill: ExtensionSkill) {
    if (!window.confirm(t("extensions.confirmDeleteSkill", "Delete this Aethos-managed skill?"))) return;
    await deleteSkill(skill.name, skill.source === "aethos_project" ? rootDir.trim() || undefined : undefined);
    await loadSkills();
    setSelectedSkillName("");
  }

  async function handleRefreshMcp() {
    const resolvedRootDir = rootDir.trim() || undefined;
    setIsLoading(true);
    setError("");
    try {
      await refreshMCPServers();
      setMcpServers(await fetchMCPServers(resolvedRootDir));
      setMcpInstructions(await fetchMCPInstructions(resolvedRootDir));
      const userConfig = await fetchMCPConfig("user");
      setMcpUserConfig(userConfig);
      if (editMcpConfigScope === "user") setMcpConfig(userConfig);
      if (resolvedRootDir) {
        const projectConfig = await fetchMCPConfig("project", resolvedRootDir);
        setMcpProjectConfig(projectConfig);
        if (editMcpConfigScope === "project") setMcpConfig(projectConfig);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("extensions.refreshFailed", "Refresh failed."));
    } finally {
      setIsLoading(false);
    }
  }

  async function handleRemoveMcpServer(server: MCPServerInfo) {
    if (!window.confirm(t("extensions.confirmRemoveMcpServer", "Remove this MCP server from settings?"))) return;
    setError("");
    try {
      const resolvedRootDir = rootDir.trim() || undefined;
      const scope = server.scope === "project" ? "project" : "user";
      await removeMCPServer(server.name, scope, resolvedRootDir);
      const updated = await fetchMCPServers(resolvedRootDir);
      setMcpServers(updated);
      setMcpInstructions(await fetchMCPInstructions(resolvedRootDir));
      const userConfig = await fetchMCPConfig("user");
      setMcpUserConfig(userConfig);
      if (editMcpConfigScope === "user") setMcpConfig(userConfig);
      if (resolvedRootDir) {
        const projectConfig = await fetchMCPConfig("project", resolvedRootDir);
        setMcpProjectConfig(projectConfig);
        if (editMcpConfigScope === "project") setMcpConfig(projectConfig);
      }
      if (selectedServerName === server.name) {
        setSelectedServerName(updated[0]?.name ?? "");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("extensions.mcpRemoveFailed", "Failed to remove server."));
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-[26px] font-semibold text-[var(--text-primary)]">{t("settings.extensions", "Extensions")}</h1>
        <p className="text-[13px] leading-6 text-[var(--text-secondary)]">
          {t("extensions.description", "Manage project skills and inspect MCP servers without changing the prompt contract. Aethos still loads full skill instructions only through the skill tool.")}
        </p>
      </div>

      <div className="flex rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] p-1">
        {[
          { id: "skills" as const, label: t("extensions.skills", "Skills"), icon: Puzzle },
          { id: "mcp" as const, label: t("extensions.mcp", "MCP"), icon: Cable },
        ].map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`flex flex-1 items-center justify-center gap-2 rounded-xl px-3 py-2 text-sm transition ${
              tab === id ? "bg-[var(--panel-elevated)] text-[var(--text-primary)] shadow-sm" : "text-[var(--text-soft)] hover:text-[var(--text-primary)]"
            }`}
          >
            <Icon size={15} strokeWidth={1.8} />
            {label}
          </button>
        ))}
      </div>

      {error ? (
        <div className="rounded-2xl border border-[var(--danger-border)] bg-[var(--danger-bg)] px-4 py-3 text-sm text-[var(--danger)]">
          {error}
        </div>
      ) : null}

      {tab === "skills" ? (
        <section className="space-y-4">
            <>
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative min-w-0 flex-1">
                  <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-faint)]" size={15} strokeWidth={1.8} />
                  <input
                    value={skillQuery}
                    onChange={(event) => setSkillQuery(event.target.value)}
                    placeholder={t("extensions.searchSkills", "Search skills")}
                    className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] py-2 pl-9 pr-3 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--border-strong)]"
                  />
                </div>
                <StyledSelect
                  value={sourceFilter}
                  options={(["all", "aethos_project", "aethos_user"] as SkillSourceFilter[]).map((source) => ({
                    value: source,
                    label: source === "all" ? t("extensions.allSources", "All sources") : t(`extensions.source.${source}`, source),
                  }))}
                  onValueChange={setSourceFilter}
                  className="min-w-[150px]"
                  label={t("extensions.allSources", "All sources")}
                />
                <button
                  type="button"
                  onClick={() => setUploadOpen(true)}
                  className="inline-flex items-center gap-2 rounded-xl bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white transition hover:opacity-90"
                >
                  <Upload size={15} strokeWidth={1.8} />
                  {t("extensions.uploadSkill", "Upload skill")}
                </button>
              </div>

              <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(220px,0.85fr)]">
                <div className="space-y-2">
                  {filteredSkills.length === 0 ? (
                    <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-4 text-sm text-[var(--text-secondary)]">
                      {isLoading ? t("extensions.loading", "Loading...") : t("extensions.noSkills", "No skills found.")}
                    </div>
                  ) : filteredSkills.map((skill) => (
                    <button
                      key={skill.name}
                      type="button"
                      onClick={() => setSelectedSkillName(skill.name)}
                      className={`w-full rounded-2xl border p-4 text-left transition ${
                        selectedSkillName === skill.name
                          ? "border-[var(--accent)] bg-[color:color-mix(in_oklab,var(--accent)_10%,var(--panel-elevated))]"
                          : "border-[var(--border-subtle)] bg-[var(--panel-elevated)] hover:border-[var(--border-strong)]"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <h3 className="truncate text-sm font-semibold text-[var(--text-primary)]">{skill.name}</h3>
                          <p className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--text-secondary)]">{skill.description}</p>
                        </div>
                        <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.14em] ${badgeClassName()}`}>
                          {t(`extensions.source.${skill.source}`, skill.source)}
                        </span>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {riskBadges(skill).map((badge) => (
                          <span key={badge.key} className={`rounded-full border px-2 py-0.5 text-[10px] ${badgeClassName(badge.kind)}`}>
                            {badge.label}
                          </span>
                        ))}
                      </div>
                    </button>
                  ))}
                </div>

                <aside className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-4">
                  {selectedSkill ? (
                    <div className="space-y-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <h3 className="truncate text-sm font-semibold text-[var(--text-primary)]">{selectedSkill.name}</h3>
                          <p className="mt-1 text-xs text-[var(--text-soft)]">{selectedSkill.path || `${selectedSkill.server}:${selectedSkill.remote_name}`}</p>
                        </div>
                        {selectedSkill.can_delete ? (
                          <button
                            type="button"
                            onClick={() => handleDeleteSkill(selectedSkill)}
                            className="rounded-lg p-2 text-[var(--danger)] transition hover:bg-[var(--danger-bg)]"
                            title={t("extensions.deleteSkill", "Delete skill")}
                          >
                            <Trash2 size={15} strokeWidth={1.8} />
                          </button>
                        ) : null}
                      </div>
                      {selectedSkill.when_to_use ? (
                        <p className="rounded-xl bg-[var(--surface-soft)] px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]">{selectedSkill.when_to_use}</p>
                      ) : null}
                      <div className="grid gap-2 text-xs text-[var(--text-secondary)]">
                        <div>{t("extensions.allowedTools", "Allowed tools")}: {selectedSkill.allowed_tools.join(", ") || t("extensions.none", "None")}</div>
                        <div>{t("extensions.argumentHint", "Argument hint")}: {selectedSkill.argument_hint || t("extensions.none", "None")}</div>
                        <div>{t("extensions.paths", "Paths")}: {selectedSkill.paths.join(", ") || t("extensions.none", "None")}</div>
                      </div>
                      <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] p-3 text-xs leading-5 text-[var(--text-secondary)]">
                        {selectedSkill.body || t("extensions.noPreview", "No local preview available for this skill.")}
                      </pre>
                    </div>
                  ) : (
                    <p className="text-sm text-[var(--text-soft)]">{t("extensions.selectSkill", "Select a skill to inspect it.")}</p>
                  )}
                </aside>
              </div>
            </>
        </section>
      ) : (
        <section className="space-y-4">
          <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] p-3 sm:p-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
              <div className="min-w-0 space-y-1">
                <h2 className="text-sm font-semibold text-[var(--text-primary)]">{t("extensions.mcpOverviewTitle", "MCP servers")}</h2>
                <p className="text-sm text-[var(--text-secondary)]">{t("extensions.mcpDesc", "Inspect configured MCP servers, resources, prompts, and model instructions.")}</p>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
                <div className="sm:min-w-[160px]">
                  <StyledSelect
                    value={mcpScopeFilter}
                    options={[
                      { value: "all", label: t("extensions.allSources", "All sources") },
                      { value: "project", label: t("extensions.scope.project", "Project") },
                      { value: "user", label: t("extensions.scope.user", "User") },
                    ]}
                    onValueChange={(value) => {
                      setMcpScopeFilter(value as MCPScopeFilter);
                      setSelectedServerName("");
                    }}
                    className="min-w-[150px]"
                    label={t("extensions.allSources", "All sources")}
                  />
                </div>
                <button
                  type="button"
                  onClick={() => setAddServerOpen(true)}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white transition hover:opacity-90"
                >
                  <Plus size={15} strokeWidth={1.8} />
                  {t("extensions.addMcpServer", "Add server")}
                </button>
                <div ref={mcpActionsRef} className="relative">
                  <button
                    type="button"
                    aria-haspopup="menu"
                    aria-expanded={mcpActionsOpen}
                    aria-controls={mcpActionsMenuId}
                    onClick={() => setMcpActionsOpen((current) => !current)}
                    className="inline-flex items-center justify-center gap-2 rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-sm text-[var(--text-secondary)] transition hover:bg-[var(--surface-hover)]"
                  >
                    <Ellipsis size={15} strokeWidth={1.8} />
                    {t("extensions.mcpActions", "Actions")}
                  </button>

                  {mcpActionsOpen ? (
                    <div
                      id={mcpActionsMenuId}
                      role="menu"
                      className="absolute right-0 top-[calc(100%+8px)] z-30 min-w-[240px] rounded-2xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-1 shadow-[0_18px_45px_var(--shadow-panel)]"
                    >
                      <button
                        type="button"
                        role="menuitem"
                        onClick={() => {
                          setMcpActionsOpen(false);
                          void handleRefreshMcp();
                        }}
                        className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-[var(--text-primary)] transition hover:bg-[var(--surface-hover)]"
                      >
                        <RefreshCcw size={15} strokeWidth={1.8} />
                        {t("extensions.refresh", "Refresh")}
                      </button>
                      {rootDir.trim() ? (
                        <button
                          type="button"
                          role="menuitem"
                          onClick={() => {
                            setMcpActionsOpen(false);
                            setEditMcpConfigScope("project");
                            setEditMcpConfigOpen(true);
                          }}
                          className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-[var(--text-primary)] transition hover:bg-[var(--surface-hover)]"
                        >
                          <Braces size={15} strokeWidth={1.8} />
                          {t("extensions.editProjectMcpJson", "Edit project MCP config")}
                        </button>
                      ) : null}
                      <button
                        type="button"
                        role="menuitem"
                        onClick={() => {
                          setMcpActionsOpen(false);
                          setEditMcpConfigScope("user");
                          setEditMcpConfigOpen(true);
                        }}
                        className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-[var(--text-primary)] transition hover:bg-[var(--surface-hover)]"
                      >
                        <Braces size={15} strokeWidth={1.8} />
                        {t("extensions.editMcpJson", "Edit user MCP config")}
                      </button>
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </div>
          <div className="grid gap-3 lg:grid-cols-[minmax(0,0.8fr)_minmax(220px,1fr)]">
            <div className="space-y-2">
              {filteredMcpServers.length === 0 ? (
                <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-4 text-sm text-[var(--text-secondary)]">
                  {t("extensions.noMcpServers", "No MCP servers configured.")}
                </div>
              ) : filteredMcpServers.map((server) => (
                <button
                  key={server.name}
                  type="button"
                  onClick={() => setSelectedServerName(server.name)}
                  className={`w-full rounded-2xl border p-4 text-left transition ${
                    selectedServerName === server.name
                      ? "border-[var(--accent)] bg-[color:color-mix(in_oklab,var(--accent)_10%,var(--panel-elevated))]"
                      : "border-[var(--border-subtle)] bg-[var(--panel-elevated)] hover:border-[var(--border-strong)]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-2">
                      <span className="font-semibold text-[var(--text-primary)]">{server.name}</span>
                      {server.source ? (
                        <span className={`rounded-full border px-2 py-0.5 text-[10px] ${badgeClassName()}`}>
                          {t(`extensions.mcpSource.${server.source}`, server.source)}
                        </span>
                      ) : null}
                      {server.scope ? (
                        <span className={`rounded-full border px-2 py-0.5 text-[10px] ${badgeClassName()}`}>
                          {t(`extensions.scope.${server.scope}`, server.scope)}
                        </span>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className={`rounded-full border px-2 py-0.5 text-[10px] ${badgeClassName(server.status === "ok" ? "success" : "risk")}`}>
                        {server.status}
                      </span>
                      {server.can_remove ? (
                        <span
                          role="button"
                          onClick={(e) => { e.stopPropagation(); void handleRemoveMcpServer(server); }}
                          className="rounded-lg p-1.5 text-[var(--danger)] transition hover:bg-[var(--danger-bg)]"
                          title={t("extensions.removeMcpServer", "Remove server")}
                        >
                          <Trash2 size={13} strokeWidth={1.8} />
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] text-[var(--text-soft)]">
                    <span className={`rounded-full border px-2 py-0.5 ${badgeClassName()}`}>{server.tools.length} {t("extensions.tools", "tools")}</span>
                    <span className={`rounded-full border px-2 py-0.5 ${badgeClassName()}`}>{server.resources.length} {t("extensions.resources", "resources")}</span>
                    <span className={`rounded-full border px-2 py-0.5 ${badgeClassName()}`}>{server.skill_prompts.length} {t("extensions.skillPrompts", "skill prompts")}</span>
                  </div>
                </button>
              ))}
            </div>
            <aside className="space-y-3 rounded-2xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-4">
              {selectedServer ? (
                <>
                  <div className="flex items-start gap-3">
                    <div className="rounded-xl bg-[var(--surface-soft)] p-2 text-[var(--accent)]">
                      <PlugZap size={17} strokeWidth={1.8} />
                    </div>
                    <div className="min-w-0">
                      <h3 className="text-sm font-semibold text-[var(--text-primary)]">{selectedServer.name}</h3>
                      <p className="truncate text-xs text-[var(--text-soft)]">
                        {selectedServer.transport || "MCP"}
                        {selectedServer.url ? ` — ${selectedServer.url}` : ""}
                        {selectedServer.command ? ` — ${selectedServer.command}` : ""}
                      </p>
                    </div>
                  </div>
                  {selectedServer.error ? (
                    <div className="flex gap-2 rounded-xl border border-[var(--danger-border)] bg-[var(--danger-bg)] p-3 text-xs text-[var(--danger)]">
                      <ShieldAlert size={15} strokeWidth={1.8} />
                      {selectedServer.error}
                    </div>
                  ) : null}
                  <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] p-3 text-xs leading-5 text-[var(--text-secondary)]">
                    {mcpInstructions || t("extensions.noMcpInstructions", "No MCP instructions are configured.")}
                  </pre>
                  <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-3 py-2 text-xs text-[var(--text-secondary)]">
                    {selectedServer.scope === "user" || selectedServer.can_remove ? (
                      <div>{t("extensions.mcpConfigPath", "User config path")}: {mcpConfig.path}</div>
                    ) : (
                      <div>
                        {t("extensions.mcpServerScope", "Server scope")}:{" "}
                        {selectedServer.scope
                          ? t(`extensions.scope.${selectedServer.scope}`, selectedServer.scope)
                          : t("extensions.mcpSourceUnknown", "Unknown")}
                      </div>
                    )}
                  </div>
                  <div className="grid gap-2 text-xs text-[var(--text-secondary)]">
                    <div>{t("extensions.tools", "Tools")}: {selectedServer.tools.map((item) => String(item.name ?? item.value ?? "")).filter(Boolean).join(", ") || t("extensions.none", "None")}</div>
                    <div>{t("extensions.prompts", "Prompts")}: {selectedServer.prompts.map((item) => String(item.name ?? "")).filter(Boolean).join(", ") || t("extensions.none", "None")}</div>
                    <div>{t("extensions.skillPrompts", "Skill prompts")}: {selectedServer.skill_prompts.map((item) => String(item.name ?? "")).filter(Boolean).join(", ") || t("extensions.none", "None")}</div>
                  </div>
                </>
              ) : (
                <p className="text-sm text-[var(--text-soft)]">{t("extensions.selectMcpServer", "Select an MCP server to inspect it.")}</p>
              )}
            </aside>
          </div>
        </section>
      )}

      {uploadOpen ? (
        <div className={nestedModalShellClass()}>
          <div className={nestedModalCardClass()}>
            <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-5 py-4">
              <h2 className="text-base font-semibold text-[var(--text-primary)]">{t("extensions.uploadSkillPackage", "Upload skill package")}</h2>
              <button type="button" onClick={() => setUploadOpen(false)} className="rounded-lg p-2 text-[var(--text-soft)] hover:bg-[var(--surface-hover)]">
                <X size={16} strokeWidth={1.8} />
              </button>
            </div>
            <div className="min-h-0 overflow-y-auto px-5 py-4">
              <div
                onDragOver={(event) => event.preventDefault()}
                onDrop={handleDrop}
                className="rounded-2xl border border-dashed border-[var(--border-strong)] bg-[var(--surface-soft)] p-6 text-center"
              >
                <FileArchive className="mx-auto text-[var(--text-soft)]" size={28} strokeWidth={1.7} />
                <p className="mt-3 text-sm font-medium text-[var(--text-primary)]">
                  {uploadFiles.length > 0
                    ? t("extensions.selectedSkillUploads", "{{count}} item selected", { count: uploadFiles.length })
                    : t("extensions.dropSkillPackage", "Drop .zip, .skill, or skill folders here")}
                </p>
                <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="inline-flex items-center justify-center rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-sm leading-5 text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]"
                  >
                    {t("extensions.browseFiles", "Browse files")}
                  </button>
                  <button
                    type="button"
                    onClick={() => folderInputRef.current?.click()}
                    className="inline-flex items-center justify-center rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-sm leading-5 text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]"
                  >
                    {t("extensions.browseSkillFolders", "Browse skill folders")}
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".zip,.skill"
                    multiple
                    className="hidden"
                    onChange={handlePickFile}
                  />
                  <input
                    ref={folderInputRef}
                    type="file"
                    multiple
                    className="hidden"
                    onChange={handlePickFolders}
                    {...({ webkitdirectory: "" } as Record<string, string>)}
                  />
                </div>
                {uploadFiles.length > 0 ? (
                  <div className="mt-3 max-h-32 overflow-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-3 text-left text-xs text-[var(--text-secondary)]">
                    {uploadFiles.map((file) => (
                      <div key={`${file.webkitRelativePath || file.name}:${file.size}`} className="break-all">
                        {file.webkitRelativePath || file.name}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
              <div className="mt-4 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] p-3">
                <label className={labelClass()}>{t("extensions.uploadScope", "Install scope")}</label>
                <StyledSelect
                  value={uploadScope}
                  options={[
                    { value: "user", label: t("extensions.uploadScopeUser", "User — available in all chats and projects") },
                    ...(rootDir.trim()
                      ? [{ value: "project" as const, label: t("extensions.uploadScopeProject", "Project — only this workspace, overrides user skill names") }]
                      : []),
                  ]}
                  onValueChange={setUploadScope}
                  label={t("extensions.uploadScope", "Install scope")}
                />
                <p className="mt-2 text-xs leading-5 text-[var(--text-soft)]">
                  {uploadScope === "project" && rootDir.trim()
                    ? t("extensions.uploadScopeProjectHint", "Project skills are saved under this workspace's .aethos/skills folder and override user skills with the same name in this project.")
                    : t("extensions.uploadScopeUserHint", "User skills are saved under ~/.aethos/skills and work in general chat plus every project.")}
                </p>
              </div>
              <label className="mt-4 flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                <input type="checkbox" checked={overwrite} onChange={(event) => setOverwrite(event.target.checked)} />
                {t("extensions.overwriteExisting", "Overwrite existing skill with the same name")}
              </label>
            </div>
            {uploadStatus ? <p className="px-5 pb-1 text-sm text-[var(--text-secondary)]">{uploadStatus}</p> : null}
            <div className="flex flex-wrap justify-end gap-2 border-t border-[var(--border-subtle)] px-5 py-4">
              <button type="button" onClick={() => setUploadOpen(false)} className="rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-sm text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]">
                {t("settings.cancel", "Cancel")}
              </button>
              <button type="button" onClick={handleUpload} disabled={uploadFiles.length === 0} className="rounded-xl bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50">
                {t("extensions.installSkill", "Install skill")}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {addServerOpen ? (
        <AddServerModal
          rootDir={rootDir}
          onClose={() => setAddServerOpen(false)}
          onAdded={() => {
            const resolvedRootDir = rootDir.trim() || undefined;
            void fetchMCPServers(resolvedRootDir)
              .then((servers) => {
                setMcpServers(servers);
                setSelectedServerName(servers[servers.length - 1]?.name ?? selectedServerName);
              })
              .catch(() => {});
            void fetchMCPInstructions(resolvedRootDir).then(setMcpInstructions).catch(() => {});
            void fetchMCPConfig("user").then((cfg) => {
              setMcpUserConfig(cfg);
              if (editMcpConfigScope === "user") setMcpConfig(cfg);
            }).catch(() => {});
            if (resolvedRootDir) {
              void fetchMCPConfig("project", resolvedRootDir).then((cfg) => {
                setMcpProjectConfig(cfg);
                if (editMcpConfigScope === "project") setMcpConfig(cfg);
              }).catch(() => {});
            }
          }}
        />
      ) : null}

      {editMcpConfigOpen ? (
        <EditMCPConfigModal
          config={mcpConfig}
          rootDir={rootDir}
          scope={editMcpConfigScope}
          onClose={() => setEditMcpConfigOpen(false)}
          onSaved={(config) => {
            if ((config.scope || editMcpConfigScope) === "project") {
              setMcpProjectConfig(config);
            } else {
              setMcpUserConfig(config);
            }
            setMcpConfig(config);
            void refreshMCPServers()
              .then(async () => {
                const resolvedRootDir = rootDir.trim() || undefined;
                setMcpServers(await fetchMCPServers(resolvedRootDir));
                setMcpInstructions(await fetchMCPInstructions(resolvedRootDir));
              })
              .catch(() => {});
          }}
        />
      ) : null}
    </div>
  );
}
