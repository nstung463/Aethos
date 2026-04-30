import { ChangeEvent, DragEvent, useEffect, useMemo, useState } from "react";
import { Cable, FileArchive, PlugZap, Puzzle, RefreshCcw, Search, ShieldAlert, Trash2, Upload, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ExtensionSkill, MCPServerInfo } from "../../types";
import {
  deleteSkill,
  fetchMCPInstructions,
  fetchMCPServers,
  fetchSkill,
  fetchSkills,
  importSkillPackage,
  refreshMCPServers,
} from "../../utils/extensions";

type SkillSourceFilter = "all" | "ethos" | "project" | "claude" | "mcp";

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

export default function ExtensionsSettings({ rootDir }: { rootDir: string }) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<"skills" | "mcp">("skills");
  const [skills, setSkills] = useState<ExtensionSkill[]>([]);
  const [selectedSkillName, setSelectedSkillName] = useState("");
  const [selectedSkill, setSelectedSkill] = useState<ExtensionSkill | null>(null);
  const [skillQuery, setSkillQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState<SkillSourceFilter>("all");
  const [mcpServers, setMcpServers] = useState<MCPServerInfo[]>([]);
  const [mcpInstructions, setMcpInstructions] = useState("");
  const [selectedServerName, setSelectedServerName] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [overwrite, setOverwrite] = useState(false);
  const [uploadStatus, setUploadStatus] = useState("");

  const hasRootDir = rootDir.trim().length > 0;

  async function loadSkills(signal?: AbortSignal) {
    if (!hasRootDir) {
      setSkills([]);
      setSelectedSkillName("");
      setSelectedSkill(null);
      return;
    }
    const items = await fetchSkills(rootDir, signal);
    setSkills(items);
    setSelectedSkillName((current) => current || items[0]?.name || "");
  }

  useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true);
    setError("");
    Promise.all([
      loadSkills(controller.signal),
      fetchMCPServers(controller.signal).then((items) => {
        setMcpServers(items);
        setSelectedServerName((current) => current || items[0]?.name || "");
      }),
      fetchMCPInstructions(controller.signal).then(setMcpInstructions),
    ])
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof Error ? err.message : t("extensions.loadFailed", "Failed to load extensions."));
      })
      .finally(() => setIsLoading(false));
    return () => controller.abort();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rootDir]);

  useEffect(() => {
    if (!selectedSkillName || !hasRootDir) {
      setSelectedSkill(null);
      return;
    }
    const controller = new AbortController();
    fetchSkill(rootDir, selectedSkillName, controller.signal)
      .then(setSelectedSkill)
      .catch(() => setSelectedSkill(skills.find((skill) => skill.name === selectedSkillName) ?? null));
    return () => controller.abort();
  }, [hasRootDir, rootDir, selectedSkillName, skills]);

  const filteredSkills = useMemo(() => {
    const query = skillQuery.trim().toLowerCase();
    return skills.filter((skill) => {
      const matchesSource = sourceFilter === "all" || skill.source === sourceFilter;
      const matchesQuery =
        !query ||
        skill.name.toLowerCase().includes(query) ||
        skill.description.toLowerCase().includes(query) ||
        (skill.when_to_use ?? "").toLowerCase().includes(query);
      return matchesSource && matchesQuery;
    });
  }, [skillQuery, skills, sourceFilter]);

  const selectedServer = mcpServers.find((server) => server.name === selectedServerName) ?? mcpServers[0] ?? null;

  function handlePickFile(event: ChangeEvent<HTMLInputElement>) {
    setUploadFile(event.target.files?.[0] ?? null);
    setUploadStatus("");
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setUploadFile(event.dataTransfer.files?.[0] ?? null);
    setUploadStatus("");
  }

  async function handleUpload() {
    if (!uploadFile || !hasRootDir) return;
    try {
      setUploadStatus(t("extensions.uploadingSkill", "Uploading skill package..."));
      const skill = await importSkillPackage(rootDir, uploadFile, overwrite);
      await loadSkills();
      setSelectedSkillName(skill.name);
      setUploadStatus(t("extensions.skillInstalled", "Skill installed."));
      setUploadOpen(false);
      setUploadFile(null);
      setOverwrite(false);
    } catch (err) {
      setUploadStatus(err instanceof Error ? err.message : t("extensions.uploadFailed", "Skill upload failed."));
    }
  }

  async function handleDeleteSkill(skill: ExtensionSkill) {
    if (!window.confirm(t("extensions.confirmDeleteSkill", "Delete this Ethos-managed skill?"))) return;
    await deleteSkill(rootDir, skill.name);
    await loadSkills();
    setSelectedSkillName("");
  }

  async function handleRefreshMcp() {
    setIsLoading(true);
    setError("");
    try {
      setMcpServers(await refreshMCPServers());
      setMcpInstructions(await fetchMCPInstructions());
    } catch (err) {
      setError(err instanceof Error ? err.message : t("extensions.refreshFailed", "Refresh failed."));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold text-[var(--text-primary)]">{t("settings.extensions", "Extensions")}</h1>
        <p className="text-sm leading-6 text-[var(--text-secondary)]">
          {t("extensions.description", "Manage project skills and inspect MCP servers without changing the prompt contract. Ethos still loads full skill instructions only through the skill tool.")}
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
          {!hasRootDir ? (
            <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-5">
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">{t("extensions.selectProjectFirst", "Select a local project first")}</h2>
              <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                {t("extensions.selectProjectFirstDesc", "Project skills are installed into .ethos/skills, so Ethos needs an active local project folder before importing packages.")}
              </p>
            </div>
          ) : (
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
                <select
                  value={sourceFilter}
                  onChange={(event) => setSourceFilter(event.target.value as SkillSourceFilter)}
                  style={{ colorScheme: "inherit" }}
                  className="rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none"
                >
                  {(["all", "ethos", "project", "claude", "mcp"] as SkillSourceFilter[]).map((source) => (
                    <option key={source} value={source} className="bg-[var(--panel-elevated)] text-[var(--text-primary)]">
                      {source === "all" ? t("extensions.allSources", "All sources") : source}
                    </option>
                  ))}
                </select>
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
                          {skill.source}
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
          )}
        </section>
      ) : (
        <section className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-[var(--text-secondary)]">{t("extensions.mcpDesc", "Inspect configured MCP servers, resources, prompts, and model instructions.")}</p>
            <button
              type="button"
              onClick={handleRefreshMcp}
              className="inline-flex items-center gap-2 rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-sm text-[var(--text-secondary)] transition hover:bg-[var(--surface-hover)]"
            >
              <RefreshCcw size={15} strokeWidth={1.8} />
              {t("extensions.refresh", "Refresh")}
            </button>
          </div>
          <div className="grid gap-3 lg:grid-cols-[minmax(0,0.8fr)_minmax(220px,1fr)]">
            <div className="space-y-2">
              {mcpServers.length === 0 ? (
                <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-4 text-sm text-[var(--text-secondary)]">
                  {t("extensions.noMcpServers", "No MCP servers configured.")}
                </div>
              ) : mcpServers.map((server) => (
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
                    <span className="font-semibold text-[var(--text-primary)]">{server.name}</span>
                    <span className={`rounded-full border px-2 py-0.5 text-[10px] ${badgeClassName(server.status === "ok" ? "success" : "risk")}`}>
                      {server.status}
                    </span>
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
                      <p className="truncate text-xs text-[var(--text-soft)]">{selectedServer.transport || "MCP"} {selectedServer.url ? `- ${selectedServer.url}` : ""}</p>
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
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-2xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-5 shadow-2xl">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-base font-semibold text-[var(--text-primary)]">{t("extensions.uploadSkillPackage", "Upload skill package")}</h2>
              <button type="button" onClick={() => setUploadOpen(false)} className="rounded-lg p-2 text-[var(--text-soft)] hover:bg-[var(--surface-hover)]">
                <X size={16} strokeWidth={1.8} />
              </button>
            </div>
            <div
              onDragOver={(event) => event.preventDefault()}
              onDrop={handleDrop}
              className="mt-4 rounded-2xl border border-dashed border-[var(--border-strong)] bg-[var(--surface-soft)] p-6 text-center"
            >
              <FileArchive className="mx-auto text-[var(--text-soft)]" size={28} strokeWidth={1.7} />
              <p className="mt-3 text-sm font-medium text-[var(--text-primary)]">
                {uploadFile?.name || t("extensions.dropSkillPackage", "Drop a .zip or .skill package here")}
              </p>
              <label className="mt-3 inline-flex cursor-pointer rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-sm text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]">
                {t("extensions.browseFiles", "Browse files")}
                <input type="file" accept=".zip,.skill" className="hidden" onChange={handlePickFile} />
              </label>
            </div>
            <label className="mt-4 flex items-center gap-2 text-sm text-[var(--text-secondary)]">
              <input type="checkbox" checked={overwrite} onChange={(event) => setOverwrite(event.target.checked)} />
              {t("extensions.overwriteExisting", "Overwrite existing skill with the same name")}
            </label>
            {uploadStatus ? <p className="mt-3 text-sm text-[var(--text-secondary)]">{uploadStatus}</p> : null}
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setUploadOpen(false)} className="rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-sm text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]">
                {t("settings.cancel", "Cancel")}
              </button>
              <button type="button" onClick={handleUpload} disabled={!uploadFile} className="rounded-xl bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50">
                {t("extensions.installSkill", "Install skill")}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
