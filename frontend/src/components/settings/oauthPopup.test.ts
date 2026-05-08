import { describe, expect, it } from "vitest";

import { CONNECTIONS_UPDATED_MESSAGE_TYPE, isTrustedConnectionAuthMessage } from "./oauthPopup";

describe("isTrustedConnectionAuthMessage", () => {
  it("accepts messages from the expected origin and popup source", () => {
    const popup = window;

    expect(
      isTrustedConnectionAuthMessage(
        {
          data: { type: CONNECTIONS_UPDATED_MESSAGE_TYPE },
          origin: window.location.origin,
          source: popup,
        },
        popup,
        window.location.origin,
      ),
    ).toBe(true);
  });

  it("rejects messages from another origin", () => {
    const popup = window;

    expect(
      isTrustedConnectionAuthMessage(
        {
          data: { type: CONNECTIONS_UPDATED_MESSAGE_TYPE },
          origin: "https://evil.example",
          source: popup,
        },
        popup,
        window.location.origin,
      ),
    ).toBe(false);
  });

  it("rejects messages from another source", () => {
    const popup = window;
    const otherSource = {} as MessageEventSource;

    expect(
      isTrustedConnectionAuthMessage(
        {
          data: { type: CONNECTIONS_UPDATED_MESSAGE_TYPE },
          origin: window.location.origin,
          source: otherSource,
        },
        popup,
        window.location.origin,
      ),
    ).toBe(false);
  });
});
