import { useEffect, useRef } from "react";
import type { ChatThread, PermissionMode, ThreadPermissionsBundle } from "../types";
import MessageBubble from "./MessageBubble";

export default function ChatArea({
  thread,
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
  thread: ChatThread | null;
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
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const prevThreadIdRef = useRef<string | null>(null);

  const isUserNearBottom = () => {
    if (!scrollContainerRef.current) return false;
    const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
    const distanceFromBottom = scrollHeight - (scrollTop + clientHeight);
    return distanceFromBottom < 300;
  };

  useEffect(() => {
    const isThreadChange = thread?.id !== prevThreadIdRef.current;
    prevThreadIdRef.current = thread?.id ?? null;

    if (!bottomRef.current) return;

    // On thread change (opening old conversation) → instant scroll to bottom
    if (isThreadChange) {
      bottomRef.current.scrollIntoView({ behavior: "auto" });
    }
    // On new message within same thread → smooth scroll only if user is near bottom
    else if (isUserNearBottom()) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [thread?.messages.length, thread?.messages.at(-1)?.content, thread?.id]);

  const messages = thread?.messages ?? [];

  return (
    <div ref={scrollContainerRef} className="flex-1 py-3 sm:py-4" style={{ overflowY: 'scroll', scrollbarGutter: 'stable' }}>
        <div className="max-w-4xl mx-auto space-y-3 sm:space-y-4 pb-4 px-2">
        {messages.map((message, index) => (
          <MessageBubble
            key={message.id}
            message={message}
            isLastMessage={index === messages.length - 1}
            onFollowUpClick={onFollowUpClick}
            threadPermissions={threadPermissions}
            onApproveOnce={onApproveOnce}
            onApproveForChat={onApproveForChat}
            onBypassForChat={onBypassForChat}
            onPromoteThreadPermissions={onPromoteThreadPermissions}
            onOpenSecuritySettings={onOpenSecuritySettings}
            onAnswerAskUser={onAnswerAskUser}
            onOpenWorkspaceFrame={onOpenWorkspaceFrame}
          />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
