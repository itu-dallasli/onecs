import { describe, expect, it } from "vitest";
import {
  distinctReportSources,
  nextReportTab,
  pivotMatchesReport,
  teamKey,
} from "./reportPivot";
import type { ReportPivotData } from "./reportPivot";

describe("report pivot identity and navigation", () => {
  const pivot = {
    report_id: "report-1",
    report_version: 4,
    content_hash: "saved-hash",
  } as ReportPivotData;
  const report = { id: "report-1", version: 4, content_hash: "saved-hash" };

  it("rejects cached content from a different report, version, or hash", () => {
    expect(pivotMatchesReport(pivot, report)).toBe(true);
    expect(pivotMatchesReport(undefined, report)).toBe(false);
    expect(pivotMatchesReport(pivot, { ...report, id: "report-2" })).toBe(
      false,
    );
    expect(pivotMatchesReport(pivot, { ...report, version: 5 })).toBe(false);
    expect(
      pivotMatchesReport(pivot, { ...report, content_hash: "new-hash" }),
    ).toBe(false);
  });

  it("wraps tab arrow navigation and supports Home and End", () => {
    expect(nextReportTab("ArrowRight", 2, 3)).toBe(0);
    expect(nextReportTab("ArrowLeft", 0, 3)).toBe(2);
    expect(nextReportTab("Home", 2, 3)).toBe(0);
    expect(nextReportTab("End", 0, 3)).toBe(2);
    expect(nextReportTab("Tab", 0, 3)).toBeNull();
    expect(nextReportTab("ArrowRight", 0, 0)).toBeNull();
  });

  it("uses separate, stable keys for general and unassigned team views", () => {
    expect(teamKey({ id: "team-1" })).toBe("team:team-1");
    expect(teamKey({ id: null })).toBe("team:unassigned");
  });

  it("deduplicates a source that appears in multiple sections without merging resource types", () => {
    const work = { type: "work", id: "id-1", title: "İş", version: 1 };
    const project = { ...work, type: "project", title: "Proje" };
    const sources = distinctReportSources([
      { key: "highlights", title: "Öne çıkanlar", count: 1, sources: [work] },
      {
        key: "next_steps",
        title: "Adımlar",
        count: 2,
        sources: [work, project],
      },
    ]);
    expect(sources).toEqual([work, project]);
  });
});
