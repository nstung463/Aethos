import { describe, expect, it } from "vitest";
import type { Message } from "../types";
import { mergeReasoning } from "./threads";

function buildMessage(): Message {
  return {
    id: "msg-1",
    role: "assistant",
    content: "",
    reasoning: "",
    toolEvents: [],
    createdAt: "2026-05-07T00:00:00.000Z",
    status: "streaming",
    streamItems: [],
  };
}

describe("mergeReasoning", () => {
  it("keeps tool narration text as reasoning text without stripping heuristics", () => {
    const message = buildMessage();

    const merged = mergeReasoning(message, "Using tool `powershell`: Get-Location\n");

    expect(merged.reasoning).toBe("Using tool `powershell`: Get-Location\n");
    expect(merged.toolEvents).toEqual([]);
    expect(merged.streamItems?.[0]).toMatchObject({
      type: "reasoning",
      content: "Using tool `powershell`: Get-Location\n",
    });
  });
});
