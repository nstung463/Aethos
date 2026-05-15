import { useTranslation } from "react-i18next";
import type { WorkspaceFrame } from "../../types";
import { ErrorBoundary } from "../ErrorBoundary";
import ArtifactView from "./views/ArtifactView";
import BrowserView from "./views/BrowserView";
import FileTreeView from "./views/FileTreeView";
import FileView from "./views/FileView";
import GenericView from "./views/GenericView";
import InteractionView from "./views/InteractionView";
import SearchResultsView from "./views/SearchResultsView";
import SkillView from "./views/SkillView";
import TerminalView from "./views/TerminalView";

type ViewComponent = React.ComponentType<{ frame: WorkspaceFrame; rootDir?: string }>;

const VIEW_MAP: Record<string, ViewComponent> = {
  bash: TerminalView,
  powershell: TerminalView,
  read_file: FileView,
  write_file: FileView,
  edit_file: FileView,
  ls: FileTreeView,
  glob: FileTreeView,
  grep: SearchResultsView,
  tavily_search: SearchResultsView,
  web_fetch: BrowserView,
  skill: SkillView,
  ask_user: InteractionView,
  send_user_message: InteractionView,
  present_output_file: ArtifactView,
};

export default function ContentArea({ frame, rootDir }: { frame: WorkspaceFrame | null; rootDir?: string }) {
  const { t } = useTranslation();

  if (!frame) {
    return (
      <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-[var(--text-secondary)] transition-opacity duration-200">
        {t("workspace.waiting", "Waiting for agent activity...")}
      </div>
    );
  }

  const View: ViewComponent = VIEW_MAP[frame.toolName] ?? GenericView;

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden transition-all duration-200">
      <ErrorBoundary label={`${frame.toolName} workspace view`}>
        <View frame={frame} rootDir={rootDir} />
      </ErrorBoundary>
    </div>
  );
}
