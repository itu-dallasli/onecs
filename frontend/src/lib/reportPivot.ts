export type PivotSectionKey =
  "highlights" | "lowlights" | "escalations" | "information" | "next_steps";

export type ReportSource = {
  type: string;
  id: string;
  version: number;
  title: string;
  status?: string;
  priority?: string;
  description?: string;
  due_at?: string | null;
  section?: PivotSectionKey;
  team_id?: string | null;
  next_step?: string;
};

export type PivotCounts = {
  open: number;
  completed: number;
  critical: number;
  overdue: number;
};

export type PivotSection = {
  key: PivotSectionKey;
  title: string;
  count: number;
  sources: ReportSource[];
};

export type PivotGroup = {
  source_count: number;
  counts: PivotCounts;
  sections: PivotSection[];
};

export type PivotTeam = PivotGroup & {
  id: string | null;
  name: string;
  code: string;
  metadata_provenance: string;
  sources: ReportSource[];
};

export type ReportPivotData = {
  report_id: string;
  report_version: number;
  content_hash: string;
  period_start: string;
  period_end: string;
  as_of: string;
  source_count: number;
  metadata_provenance: string;
  section_order: PivotSectionKey[];
  general: PivotGroup;
  teams: PivotTeam[];
};

export type PivotReport = {
  id: string;
  version: number;
  content_hash?: string;
  markdown?: string;
  content?: string;
  summary?: string;
};

export const GENERAL_REPORT_KEY = "general";

export function teamKey(team: Pick<PivotTeam, "id">) {
  return team.id === null ? "team:unassigned" : `team:${team.id}`;
}

export function pivotMatchesReport(
  pivot: ReportPivotData | undefined,
  report: PivotReport,
) {
  return (
    pivot?.report_id === report.id &&
    pivot.report_version === report.version &&
    pivot.content_hash === (report.content_hash || "")
  );
}

export function nextReportTab(key: string, activeIndex: number, count: number) {
  if (count < 1) return null;
  if (key === "Home") return 0;
  if (key === "End") return count - 1;
  if (key === "ArrowRight") return (activeIndex + 1) % count;
  if (key === "ArrowLeft") return (activeIndex - 1 + count) % count;
  return null;
}

export function distinctReportSources(sections: PivotSection[]) {
  const sources = new Map<string, ReportSource>();
  for (const section of sections) {
    for (const source of section.sources) {
      const key = `${source.type}:${source.id}`;
      if (!sources.has(key)) sources.set(key, source);
    }
  }
  return [...sources.values()];
}
