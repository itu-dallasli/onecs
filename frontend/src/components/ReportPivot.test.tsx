import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ReportPivotView, SavedReportMarkdown } from "./ReportPivot";
import type {
  PivotSection,
  PivotSectionKey,
  ReportPivotData,
} from "../lib/reportPivot";

const sectionKeys: PivotSectionKey[] = [
  "highlights",
  "lowlights",
  "escalations",
  "information",
  "next_steps",
];
const source = {
  id: "work-1",
  type: "work",
  version: 3,
  title: "Sentetik uygulama incelemesi",
  status: "COMPLETED",
  priority: "HIGH",
  description: "Kaynakta kayıtlı faaliyet açıklaması.",
};
const sections: PivotSection[] = sectionKeys.map((key) => ({
  key,
  title: key,
  count: key === "highlights" ? 1 : 0,
  sources: key === "highlights" ? [source] : [],
}));
const data: ReportPivotData = {
  report_id: "report-1",
  report_version: 2,
  content_hash: "content-hash",
  period_start: "2026-11-11",
  period_end: "2026-11-18",
  as_of: "2026-11-18",
  source_count: 1,
  metadata_provenance: "snapshot",
  section_order: sectionKeys,
  general: {
    source_count: 1,
    counts: { open: 0, completed: 1, critical: 0, overdue: 0 },
    sections,
  },
  teams: [
    {
      id: "team-1",
      name: "Sentetik uygulama ekibi",
      code: "APP-TEST",
      metadata_provenance: "snapshot",
      source_count: 1,
      counts: { open: 0, completed: 1, critical: 0, overdue: 0 },
      sections,
      sources: [source],
    },
    {
      id: null,
      name: "Ekip bilgisi bulunmayan kaynaklar",
      code: "",
      metadata_provenance: "unassigned",
      source_count: 0,
      counts: { open: 0, completed: 0, critical: 0, overdue: 0 },
      sections: sectionKeys.map((key) => ({
        key,
        title: key,
        count: 0,
        sources: [],
      })),
      sources: [],
    },
  ],
};
const report = {
  id: "report-1",
  version: 2,
  content_hash: "content-hash",
  markdown: "# Genel yönetim metni\nYalnız genel rapora ait kayıtlı metin.",
};

function render(activeKey = "general", nextData = data, nextReport = report) {
  return renderToStaticMarkup(
    <ReportPivotView
      report={nextReport}
      data={nextData}
      activeKey={activeKey}
    />,
  );
}

describe("report pivot presentation", () => {
  it("starts with the general row and tab, followed by actual team rows", () => {
    const markup = render();
    const body = markup.split("<tbody>")[1].split("</tbody>")[0];
    expect(body.indexOf("Genel Rapor")).toBeLessThan(
      body.indexOf(data.teams[0].name),
    );
    const tabs = markup.split('role="tablist"')[1].split('role="tabpanel"')[0];
    expect(tabs.indexOf("Genel Rapor")).toBeLessThan(
      tabs.indexOf(data.teams[0].name),
    );
    expect(tabs).toMatch(/aria-selected="true"[^>]*>.*?Genel Rapor/s);
    expect(markup).toContain("Ekip bazında rapor özeti");
    expect(markup).toContain("Genel yönetim metni");
    expect(markup).toContain("Kaynak kayıtlar (1)");
  });

  it("shows the selected team's saved sources without reusing the general AI text", () => {
    const markup = render("team:team-1");
    expect(markup).not.toContain("Genel yönetim metni");
    expect(markup).not.toContain("Yalnız genel rapora ait kayıtlı metin.");
    expect(markup).toContain(source.title);
    expect(markup).toContain(source.description);
    expect(markup).toContain("Sürüm 3");
    expect(markup).toContain("Öne çıkanlar");
    expect(markup).toContain("Engeller ve gecikmeler");
    expect(markup).toContain("Kritik konular ve kararlar");
    expect(markup).toContain("Bilgi ve projeler");
    expect(markup).toContain("Sonraki adımlar");
    expect(markup).toContain("Kaynak kayıtlarda sonraki adım belirtilmemiş.");
  });

  it("connects every tab to the live report panel with a single keyboard tab stop", () => {
    const markup = render("team:team-1");
    const panelId = markup.match(/role="tabpanel" id="([^"]+)"/)?.[1];
    expect(panelId).toBeTruthy();
    const controls = [...markup.matchAll(/aria-controls="([^"]+)"/g)];
    expect(controls).toHaveLength(3);
    expect(controls.every((match) => match[1] === panelId)).toBe(true);
    const tabs = markup.split('role="tablist"')[1].split('role="tabpanel"')[0];
    expect([...tabs.matchAll(/tabindex="0"/g)]).toHaveLength(1);
    expect([...tabs.matchAll(/aria-selected="true"/g)]).toHaveLength(1);
  });

  it("does not invent next steps and displays separately saved next-step text", () => {
    const nextStepData = structuredClone(data);
    nextStepData.teams[0].sections[4] = {
      key: "next_steps",
      title: "Sonraki adımlar",
      count: 1,
      sources: [{ ...source, next_step: "Kaynakta belirtilen devam adımı." }],
    };
    const markup = render("team:team-1", nextStepData);
    expect(markup).toContain("Kaynakta belirtilen devam adımı.");
    expect(markup).not.toContain(
      "Kaynak kayıtlarda sonraki adım belirtilmemiş.",
    );
  });

  it("explains legacy organization metadata and handles unassigned sources", () => {
    const legacy = { ...data, metadata_provenance: "mixed" };
    const markup = render("team:unassigned", legacy);
    expect(markup).toContain("mevcut ve erişilebilir");
    expect(markup).toContain("Ekip bilgisi bulunmayan kaynaklar");
    expect(markup).toContain(
      "Ekip bilgisi bulunmayan kaynaklar ayrıca gösterilir.",
    );
    expect(markup).not.toContain(source.description);
  });

  it("falls back to the general report after an unavailable team is removed", () => {
    const markup = render("team:removed");
    expect(markup).toContain("Genel yönetim metni");
    expect(markup).not.toContain("EKİP RAPORU");
  });

  it("shows recorded sections when the report has no generated management text", () => {
    const markup = render("general", data, { ...report, markdown: "" });
    expect(markup).toContain("Genel rapor özeti henüz hazırlanmadı");
    expect(markup).toContain(source.title);
    expect(markup).not.toContain("AI destekli");
  });

  it("keeps markdown text escaped rather than executing HTML or links", () => {
    const markup = renderToStaticMarkup(
      <SavedReportMarkdown
        content={
          "# Başlık\n<script>alert(1)</script>\n[bağlantı](javascript:alert(1))"
        }
      />,
    );
    expect(markup).toContain("&lt;script&gt;");
    expect(markup).not.toContain("<script>");
    expect(markup).not.toContain("<a ");
  });
});
