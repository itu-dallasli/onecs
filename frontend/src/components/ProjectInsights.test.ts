import { describe, expect, it } from "vitest";
import {
  insightScore,
  normalizeInsightTrend,
  parseReviewedScores,
  printableProjectReport,
} from "./ProjectInsights";

describe("project insight presentation and export", () => {
  it("preserves missing scores separately from measured zero", () => {
    for (const value of [
      null,
      undefined,
      "",
      false,
      {},
      -1,
      101,
      NaN,
      "unavailable",
    ]) {
      expect(insightScore(value)).toBeNull();
    }
    expect(insightScore(0)).toBe(0);
    expect(insightScore("87.5")).toBe(87.5);
  });

  it("does not turn blank human reviews into invented zero scores", () => {
    expect(
      parseReviewedScores({
        delivery: "",
        quality: "  ",
        stakeholder: "0",
        overall: "75.5",
      }),
    ).toEqual({ delivery: null, quality: null, stakeholder: 0, overall: 75.5 });
    expect(() =>
      parseReviewedScores({
        delivery: "120",
        quality: "",
        stakeholder: "",
        overall: "",
      }),
    ).toThrow(/0–100/);
  });

  it("builds a trend only from real dated delivery snapshots", () => {
    const values = normalizeInsightTrend([
      { at: "2026-11-17T10:00:00Z", scores: { delivery: 45 } },
      { at: "2026-11-16T10:00:00Z", scores: { delivery: 0 } },
      { at: "2026-11-18T10:00:00Z", scores: { delivery: null } },
      { at: "invalid-date", scores: { delivery: 80 } },
      { at: "2026-11-17T10:00:00Z", scores: { delivery: 50 } },
    ]);
    expect(values).toEqual([
      { date: "2026-11-16T10:00:00Z", value: 0 },
      { date: "2026-11-17T10:00:00Z", value: 50 },
    ]);
    expect(normalizeInsightTrend([])).toEqual([]);
  });

  it("escapes report and title content in printable HTML", () => {
    const html = printableProjectReport(
      '</title><script>alert("title")</script>',
      '<img src=x onerror=alert(1)>\n**Rapor** & "inceleme"',
    );
    expect(html).not.toContain("<script>");
    expect(html).not.toContain("<img src");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("&lt;img src=x onerror=alert(1)&gt;");
    expect(html).toContain("&amp; &quot;inceleme&quot;");
  });
});
