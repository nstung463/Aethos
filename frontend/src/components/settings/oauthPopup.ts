export const CONNECTIONS_UPDATED_MESSAGE_TYPE = "aethos-connections-updated";

export function isTrustedConnectionAuthMessage(
  event: Pick<MessageEvent, "data" | "origin" | "source">,
  popupWindow: Window | null,
  expectedOrigin: string,
): boolean {
  if (event.data?.type !== CONNECTIONS_UPDATED_MESSAGE_TYPE) return false;
  if (event.origin !== expectedOrigin) return false;
  if (!popupWindow || event.source !== popupWindow) return false;
  return true;
}
