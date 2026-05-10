import {
  FileCode,
  FileCode2,
  FileOutput,
  FilePenLine,
  FileSearch,
  FolderTree,
  Globe,
  MessageSquare,
  MousePointer2,
  Search,
  Terminal,
  Wrench,
} from "lucide-react";
import type { WorkspaceFrame } from "../../types";

type WorkspaceIconVariant = "activity" | "timeline";

export function getWorkspaceToolIcon(toolName: string, variant: WorkspaceIconVariant = "activity") {
  switch (toolName) {
    case "present_output_file":
      return FileOutput;
    case "bash":
    case "powershell":
      return Terminal;
    case "read_file":
      return variant === "timeline" ? FileSearch : FileCode;
    case "write_file":
      return variant === "timeline" ? FileCode2 : FileCode;
    case "edit_file":
      return variant === "timeline" ? FilePenLine : FileCode;
    case "ls":
    case "glob":
      return FolderTree;
    case "grep":
    case "tavily_search":
      return Search;
    case "web_fetch":
      return Globe;
    case "browser_action":
    case "click":
    case "type":
      return MousePointer2;
    case "ask_user":
    case "send_user_message":
      return MessageSquare;
    default:
      return Wrench;
  }
}

export function getWorkspaceActionLabel(frame: WorkspaceFrame) {
  if (typeof frame.summary === "string" && frame.summary.trim()) return frame.summary.trim();
  if (typeof frame.input.command === "string") return frame.input.command;
  if (typeof frame.input.path === "string") return frame.input.path;
  if (typeof frame.input.pattern === "string") return frame.input.pattern;
  if (typeof frame.input.query === "string") return frame.input.query;
  if (typeof frame.input.url === "string") return frame.input.url;
  return "";
}
