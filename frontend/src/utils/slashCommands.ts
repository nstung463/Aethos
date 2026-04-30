import type { ComposerMode, ReasoningEffort } from "../types";
import type { ExtensionSkill } from "../types";

export type SlashCommandCategory = "mode" | "thread" | "model" | "utility" | "skill";
export type SlashCommandType = "immediate" | "with-args";
export type SlashCommandArgInput = "freeform" | "select";

export type SlashCommandDef = {
  name: string;
  descriptionKey: string;
  defaultDescription: string;
  type: SlashCommandType;
  argInput?: SlashCommandArgInput;
  argsPlaceholderKey?: string;
  defaultArgsPlaceholder?: string;
  category: SlashCommandCategory;
  skill?: ExtensionSkill;
};

export type SlashCommandOptionDef = {
  value: string;
  labelKey: string;
  defaultLabel: string;
  descriptionKey?: string;
  defaultDescription?: string;
};

export const SLASH_COMMANDS: SlashCommandDef[] = [
  {
    name: "build",
    descriptionKey: "slashCommands.descriptions.build",
    defaultDescription: "Switch to build mode",
    type: "immediate",
    category: "mode",
  },
  {
    name: "review",
    descriptionKey: "slashCommands.descriptions.review",
    defaultDescription: "Switch to review mode",
    type: "immediate",
    category: "mode",
  },
  {
    name: "explain",
    descriptionKey: "slashCommands.descriptions.explain",
    defaultDescription: "Switch to explain mode",
    type: "immediate",
    category: "mode",
  },
  {
    name: "rename",
    descriptionKey: "slashCommands.descriptions.rename",
    defaultDescription: "Rename this thread",
    type: "with-args",
    argsPlaceholderKey: "slashCommands.args.title",
    defaultArgsPlaceholder: "<title>",
    category: "thread",
  },
  {
    name: "favorite",
    descriptionKey: "slashCommands.descriptions.favorite",
    defaultDescription: "Toggle favorite for this thread",
    type: "immediate",
    category: "thread",
  },
  {
    name: "project",
    descriptionKey: "slashCommands.descriptions.project",
    defaultDescription: "Move this thread to a project",
    type: "with-args",
    argsPlaceholderKey: "slashCommands.args.projectName",
    defaultArgsPlaceholder: "<project name>",
    category: "thread",
  },
  {
    name: "think",
    descriptionKey: "slashCommands.descriptions.think",
    defaultDescription: "Set reasoning effort level",
    type: "with-args",
    argInput: "select",
    argsPlaceholderKey: "slashCommands.args.reasoningLevel",
    defaultArgsPlaceholder: "none | low | medium | high | max",
    category: "model",
  },
  {
    name: "context",
    descriptionKey: "slashCommands.descriptions.context",
    defaultDescription: "Visualize current context usage",
    type: "immediate",
    category: "utility",
  },
];

export const REASONING_EFFORT_VALUES: ReasoningEffort[] = [
  "none", "minimal", "low", "medium", "high", "xhigh", "max",
];

export const COMPOSER_MODES: ComposerMode[] = ["build", "review", "explain"];
const BUILT_IN_COMMAND_NAMES = new Set(SLASH_COMMANDS.map((command) => command.name));

export function getReasoningEffortOptions(
  values: ReasoningEffort[] = REASONING_EFFORT_VALUES,
): SlashCommandOptionDef[] {
  return values.map((value) => ({
    value,
    labelKey: `settings.reasoningEffortOption.${value}`,
    defaultLabel: value,
    descriptionKey: `slashCommands.reasoningDescriptions.${value}`,
  }));
}

export function getSlashMenuQuery(draft: string): string | null {
  if (!draft.startsWith("/")) return null;
  const withoutSlash = draft.slice(1);
  if (withoutSlash.includes(" ")) return null;
  return withoutSlash.toLowerCase();
}

export function buildSkillSlashCommands(skills: ExtensionSkill[]): SlashCommandDef[] {
  return skills
    .filter((skill) => skill.name.trim() && !BUILT_IN_COMMAND_NAMES.has(skill.name))
    .map((skill) => ({
      name: skill.name,
      descriptionKey: `slashCommands.skillDescriptions.${skill.name}`,
      defaultDescription: skill.when_to_use
        ? `${skill.description} - ${skill.when_to_use}`
        : skill.description,
      type: "with-args" as const,
      argsPlaceholderKey: `slashCommands.skillArgs.${skill.name}`,
      defaultArgsPlaceholder: skill.argument_hint ?? "<args>",
      category: "skill" as const,
      skill,
    }));
}

export function buildSlashCommands(skills: ExtensionSkill[] = []): SlashCommandDef[] {
  return [...SLASH_COMMANDS, ...buildSkillSlashCommands(skills)];
}

export function filterSlashCommands(query: string, commands: SlashCommandDef[] = SLASH_COMMANDS): SlashCommandDef[] {
  if (!query) return commands;
  return commands.filter((cmd) => cmd.name.toLowerCase().startsWith(query));
}

export function parseSlashCommand(
  draft: string,
  commands: SlashCommandDef[] = SLASH_COMMANDS,
): { command: SlashCommandDef; args: string } | null {
  if (!draft.startsWith("/")) return null;
  const withoutSlash = draft.slice(1);
  const spaceIdx = withoutSlash.indexOf(" ");
  const cmdName = spaceIdx === -1 ? withoutSlash : withoutSlash.slice(0, spaceIdx);
  const args = spaceIdx === -1 ? "" : withoutSlash.slice(spaceIdx + 1).trim();
  const normalizedName = cmdName.toLowerCase();
  const command = commands.find((c) => c.name.toLowerCase() === normalizedName);
  if (!command) return null;
  return { command, args };
}
