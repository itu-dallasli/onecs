import { describe, expect, it } from "vitest";
import {
  buildPriorityBreakdown,
  buildUnitLoad,
  dashboardCount,
} from "./DashboardCharts";

describe("dashboard chart source semantics", () => {
  it("keeps missing and malformed counts distinct from measured zero", () => {
    for (const value of [
      undefined,
      null,
      "",
      false,
      -1,
      1.5,
      Number.NaN,
      "unknown",
    ])
      expect(dashboardCount(value)).toBeNull();
    expect(dashboardCount(0)).toBe(0);
    expect(dashboardCount("12")).toBe(12);
  });
  it("keeps work and case counts separate and never invents a missing case count", () => {
    const rows = buildUnitLoad([
      { id: "a", name: "A", open_work: 4, open_cases: 1 },
      { id: "b", name: "B", open_work: 2, open_cases: 5 },
      { id: "c", name: "C", open_work: 0 },
    ]);
    expect(rows.map((row) => row.id)).toEqual(["b", "a", "c"]);
    expect(rows[0]).toMatchObject({ work: 2, cases: 5, knownTotal: 7 });
    expect(rows[2]).toMatchObject({ work: 0, cases: null });
  });
  it("uses only the supplied visible agenda and includes unspecified priorities in its denominator", () => {
    const breakdown = buildPriorityBreakdown([
      { priority: "CRITICAL" },
      { priority: "high" },
      { priority: "NORMAL" },
      { priority: "CRITICAL" },
      {},
    ]);
    expect(breakdown.total).toBe(5);
    expect(
      Object.fromEntries(breakdown.parts.map((part) => [part.key, part.count])),
    ).toEqual({ CRITICAL: 2, HIGH: 1, NORMAL: 1, UNKNOWN: 1 });
    expect(breakdown.parts.reduce((sum, part) => sum + part.count, 0)).toBe(
      breakdown.total,
    );
  });
  it("does not manufacture a distribution for an empty agenda", () => {
    expect(buildPriorityBreakdown([])).toEqual({ total: 0, parts: [] });
    expect(buildUnitLoad([])).toEqual([]);
  });
});
