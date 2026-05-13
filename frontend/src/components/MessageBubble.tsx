import { memo } from "react";
import type { Message, MessageStreamItem, PermissionMode, ThreadPermissionsBundle, WorkspaceFrame } from "../types";
import ArtifactCard from "./ArtifactCard";
import AskUserCard from "./AskUserCard";
import FollowUps from "./FollowUps";
import MessageContent from "./MessageContent";
import PermissionPromptCard from "./PermissionPromptCard";
import ThinkingPanel from "./ThinkingPanel";
import TypingIndicator from "./TypingIndicator";
import { WorkspaceActivityGroupRow, WorkspaceActivityRow } from "./workspace/WorkspaceActivityList";
import { getOrderedMessageStreamItems, parsePermissionPromptFromContent } from "../utils/threads";
import { findRunStepById, runStepsToWorkspaceFrames } from "../utils/runSteps";
import { Clock } from "lucide-react";
import { useTranslation } from "react-i18next";

const TOOL_GROUP_THRESHOLD = 3;

function getWorkspaceFrameForItem(message: Message, item: MessageStreamItem): WorkspaceFrame | null {
  if (item.type === "run_step") {
    const step = findRunStepById(message, item.runStepId);
    if (!step || step.kind !== "tool") return null;
    return runStepsToWorkspaceFrames([step])[0] ?? null;
  }

  if (item.type === "workspace_frame") {
    return (message.workspaceFrames ?? []).find((candidate) => candidate.id === item.frameId) ?? null;
  }

  return null;
}

function MessageBubble({
  message,
  isLastMessage,
  onFollowUpClick,
  threadPermissions,
  onApproveOnce,
  onApproveForChat,
  onBypassForChat,
  onPromoteThreadPermissions,
  onOpenSecuritySettings,
  onAnswerAskUser,
  onOpenWorkspaceFrame,
}: {
  message: Message;
  isLastMessage: boolean;
  onFollowUpClick: (prompt: string) => void;
  threadPermissions: ThreadPermissionsBundle | null;
  onApproveOnce: (messageId: string) => Promise<void>;
  onApproveForChat: (messageId: string, mode: PermissionMode) => Promise<void>;
  onBypassForChat: (messageId: string) => Promise<void>;
  onPromoteThreadPermissions: () => Promise<void>;
  onOpenSecuritySettings: () => void;
  onAnswerAskUser?: (messageId: string, answers: Record<string, string>, notes: Record<string, string>) => void;
  onOpenWorkspaceFrame?: (messageId: string, frameId: string) => void;
}) {
  const { t } = useTranslation();
  const isUser = message.role === "user";
  const isStreaming = message.status === "streaming";
  const isInterrupted = message.status === "interrupted";
  const permissionPrompt =
    message.role === "assistant"
      ? message.permissionRequest ?? parsePermissionPromptFromContent(message.content)
      : null;
  const shouldHidePermissionProse =
    permissionPrompt !== null &&
    /approval|would you like to proceed|need your approval|approve/i.test(message.content);

  if (isUser) {
    return (
      <div className="flex justify-end px-4 py-1">
        <div
          className={`max-w-[85%] min-w-[120px] rounded-2xl rounded-br-sm border border-[var(--border-subtle)] bg-[var(--panel-elevated)] px-3 py-2.5 leading-7 sm:px-4 sm:py-3 transition-opacity ${
            message.optimistic ? "opacity-60" : "opacity-100 text-[var(--text-primary)]"
          }`}
          style={{ fontSize: "var(--message-text-size)" }}
        >
          <MessageContent content={message.content} />
          {message.optimistic ? (
            <div className="mt-1 flex items-center gap-1 text-[10px] text-[var(--text-soft)]">
              <Clock size={10} strokeWidth={2} className="animate-pulse" />
              <span>Sending…</span>
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  const orderedItems = getOrderedMessageStreamItems(message);
  const hasReasoningStreamItem = orderedItems.some((item) => item.type === "reasoning");
  const hasThinking =
    !hasReasoningStreamItem && (Boolean(message.reasoning && message.reasoning.trim().length > 0) || isStreaming);

  return (
    <div className="flex gap-2 px-4 py-1 sm:gap-3">
      <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[var(--accent)] to-[var(--accent-2)] sm:h-7 sm:w-7">
        <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
          <path
            d="M7 1C3.69 1 1 3.69 1 7s2.69 6 6 6 6-2.69 6-6-2.69-6-6-6zm0 2.25a1.5 1.5 0 110 3 1.5 1.5 0 010-3zM7 12a4.5 4.5 0 01-3.75-2.02C3.25 8.9 5.5 8.25 7 8.25s3.75.65 3.75 1.73A4.5 4.5 0 017 12z"
            fill="var(--accent-contrast)"
          />
        </svg>
      </div>

      <div className="min-w-0 flex-1 pt-0.5">
        {hasThinking ? (
          <ThinkingPanel
            reasoning={message.reasoning}
            isStreaming={isStreaming}
            thinkingDuration={message.thinkingDuration}
          />
        ) : null}

        {shouldHidePermissionProse || permissionPrompt ? null : orderedItems.length > 0 ? (
          <div className="space-y-3 leading-7 text-[var(--text-primary)]" style={{ fontSize: "var(--message-text-size)" }}>
            {(() => {
              const renderedItems: React.ReactNode[] = [];

              for (let index = 0; index < orderedItems.length; index += 1) {
                const item = orderedItems[index];

                if (item.type === "text") {
                  renderedItems.push(
                    <div key={item.id}>
                      <MessageContent content={item.content} />
                    </div>,
                  );
                  continue;
                }

                if (item.type === "reasoning") {
                  renderedItems.push(
                    <ThinkingPanel
                      key={item.id}
                      reasoning={item.content}
                      isStreaming={isStreaming && index === orderedItems.length - 1}
                      thinkingDuration={message.status === "done" ? item.thinkingDuration ?? message.thinkingDuration : undefined}
                    />,
                  );
                  continue;
                }

                const groupedFrames: WorkspaceFrame[] = [];
                const groupedKeys: string[] = [];
                let cursor = index;

                while (cursor < orderedItems.length) {
                  const candidate = orderedItems[cursor];
                  if (candidate.type !== "run_step" && candidate.type !== "workspace_frame") break;

                  const frame = getWorkspaceFrameForItem(message, candidate);
                  if (!frame) break;
                  if (groupedFrames.length > 0 && frame.artifact) break;

                  groupedFrames.push(frame);
                  groupedKeys.push(candidate.id);
                  cursor += 1;
                  if (frame.artifact) break;
                }

                if (groupedFrames.length >= TOOL_GROUP_THRESHOLD) {
                  renderedItems.push(
                    <WorkspaceActivityGroupRow
                      key={`tool-group-${groupedKeys[0] ?? groupedFrames[0]?.id}`}
                      messageId={message.id}
                      frames={groupedFrames}
                      onOpenFrame={onOpenWorkspaceFrame}
                      autoExpand={isStreaming}
                    />,
                  );
                } else {
                  groupedFrames.forEach((frame, frameIndex) => {
                    if (frame.artifact) {
                      renderedItems.push(
                        <ArtifactCard
                          key={groupedKeys[frameIndex] ?? frame.id}
                          artifact={frame.artifact}
                          onOpenPreview={() => onOpenWorkspaceFrame?.(message.id, frame.id)}
                        />,
                      );
                      return;
                    }
                    renderedItems.push(
                      <WorkspaceActivityRow
                        key={groupedKeys[frameIndex] ?? frame.id}
                        messageId={message.id}
                        frame={frame}
                        onOpenFrame={onOpenWorkspaceFrame}
                      />,
                    );
                  });
                }

                index = cursor - 1;
              }

              return renderedItems;
            })()}
          </div>
        ) : isStreaming && !hasThinking ? (
          <div className="leading-7 text-[var(--text-primary)]" style={{ fontSize: "var(--message-text-size)" }}>
            <TypingIndicator />
          </div>
        ) : null}

        {message.error ? (
          <div className="mt-2 rounded-lg border px-3 py-2 text-xs text-[var(--danger)]" style={{ background: "var(--danger-bg)", borderColor: "var(--danger-border)" }}>
            {message.error}
          </div>
        ) : null}

        {isInterrupted ? (
          <div className="mt-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-3 py-2 text-xs text-[var(--text-secondary)]">
            {t("chat.responseStopped", "Response stopped")}
          </div>
        ) : null}

        {message.askUserRequest ? (
          <AskUserCard
            request={message.askUserRequest}
            onSubmit={(answers, notes) => onAnswerAskUser?.(message.id, answers, notes)}
          />
        ) : permissionPrompt ? (
          <PermissionPromptCard
            prompt={permissionPrompt}
            threadPermissions={threadPermissions}
            onApproveOnce={() => onApproveOnce(message.id)}
            onApproveForChat={(mode) => onApproveForChat(message.id, mode)}
            onBypassForChat={() => onBypassForChat(message.id)}
            onPromoteThreadPermissions={onPromoteThreadPermissions}
            onOpenSecuritySettings={onOpenSecuritySettings}
          />
        ) : null}

        {isLastMessage && message.status === "done" && (message.followUps?.length ?? 0) > 0 ? (
          <FollowUps followUps={message.followUps ?? []} onClick={onFollowUpClick} />
        ) : null}
      </div>
    </div>
  );
}

export default memo(MessageBubble);
