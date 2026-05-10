import { describe, expect, it } from "vitest";
import { normalizeRunSteps, runStepsToWorkspaceFrames } from "./runSteps";

describe("normalizeRunSteps", () => {
  it("recovers presented output artifacts from persisted JSON output", () => {
    const steps = normalizeRunSteps([
      {
        id: "step_tool_file",
        kind: "tool",
        status: "completed",
        startedAt: "2026-05-08T22:20:31.465Z",
        toolName: "present_output_file",
        output: JSON.stringify({
          __aethos_presented_output_file__: true,
          message: "Presented output file: report.xlsx",
          artifact: {
            file_id: "file_1",
            filename: "report.xlsx",
            content_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            size: 123,
            artifact_type: "spreadsheet",
            title: "Q1 report",
            description: "Final workbook",
            content_url: "/api/files/file_1/content",
          },
        }),
      },
    ]);

    expect(steps[0]?.artifact?.file_id).toBe("file_1");
    expect(runStepsToWorkspaceFrames(steps)[0]?.artifact?.title).toBe("Q1 report");
  });
});
