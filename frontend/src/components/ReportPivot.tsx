import { useId, useRef, useState } from "react";
import {
  ArrowUpRight,
  CheckCircle2,
  CircleAlert,
  FileText,
  Flag,
  LayoutGrid,
  ListChecks,
  MessageSquareText,
  Sun,
  Users,
} from "lucide-react";
import { date, useResource } from "../lib/api";
import {
  distinctReportSources,
  GENERAL_REPORT_KEY,
  nextReportTab,
  pivotMatchesReport,
  teamKey,
} from "../lib/reportPivot";
import type {
  PivotCounts,
  PivotReport,
  PivotSection,
  PivotSectionKey,
  PivotTeam,
  ReportPivotData,
  ReportSource,
} from "../lib/reportPivot";
import { Badge, EmptyState, ErrorState, Loading, Status } from "./ui";
import "../styles/reports-pivot.css";

const sectionDisplay = {
  highlights: {
    title: "Öne çıkanlar",
    subtitle: "Tamamlanan işler ve olumlu gelişmeler",
    empty: "Bu bölümde rapora alınmış bir gelişme bulunmuyor.",
    icon: Sun,
  },
  lowlights: {
    title: "Engeller ve gecikmeler",
    subtitle: "İlerlemesi engellenen veya geciken konular",
    empty: "Bu bölümde rapora alınmış bir engel veya gecikme bulunmuyor.",
    icon: CircleAlert,
  },
  escalations: {
    title: "Kritik konular ve kararlar",
    subtitle: "Yakından izlenmesi ve karar verilmesi gereken konular",
    empty: "Bu bölümde rapora alınmış kritik bir konu bulunmuyor.",
    icon: Flag,
  },
  information: {
    title: "Bilgi ve projeler",
    subtitle: "Devam eden faaliyetler ve proje gelişmeleri",
    empty: "Bu bölümde rapora alınmış bir faaliyet bulunmuyor.",
    icon: MessageSquareText,
  },
  next_steps: {
    title: "Sonraki adımlar",
    subtitle: "Kaynak kayıtlarda belirtilen devam adımları",
    empty: "Kaynak kayıtlarda sonraki adım belirtilmemiş.",
    icon: ListChecks,
  },
};

const sourceLabels: Record<string, string> = {
  project: "Proje",
  work: "İş ve taahhüt",
  case: "Vaka",
};

function SourceEntry({
  source,
  nextStep = false,
}: {
  source: ReportSource;
  nextStep?: boolean;
}) {
  return (
    <article className="report-pivot-source">
      <div className="report-pivot-source-heading">
        <h4>{source.title || "Başlıksız kaynak"}</h4>
        {source.status && <Status value={source.status} />}
      </div>
      {(nextStep ? source.next_step : source.description) && (
        <p>{nextStep ? source.next_step : source.description}</p>
      )}
      <div className="report-pivot-source-meta">
        <span>{sourceLabels[source.type] || "Kaynak kayıt"}</span>
        <span>Sürüm {source.version}</span>
        {source.priority === "CRITICAL" && <Badge tone="danger">Kritik</Badge>}
        {source.due_at && <span>Hedef: {date(source.due_at)}</span>}
      </div>
    </article>
  );
}

function StructuredSections({
  sections,
  order,
}: {
  sections: PivotSection[];
  order: PivotSectionKey[];
}) {
  return (
    <div className="report-pivot-sections">
      {order.map((key) => {
        const display = sectionDisplay[key];
        if (!display) return null;
        const section = sections.find((item) => item.key === key);
        const Icon = display.icon;
        return (
          <section className={`report-pivot-section is-${key}`} key={key}>
            <div className="report-pivot-section-label">
              <span className="report-pivot-section-icon">
                <Icon size={23} aria-hidden="true" />
              </span>
              <div>
                <h3>{display.title}</h3>
                <p>{display.subtitle}</p>
              </div>
              <span className="report-pivot-section-count">
                {section?.count ?? 0}
              </span>
            </div>
            <div className="report-pivot-section-content">
              {section?.sources.length ? (
                section.sources.map((source) => (
                  <SourceEntry
                    key={`${source.type}:${source.id}`}
                    source={source}
                    nextStep={key === "next_steps"}
                  />
                ))
              ) : (
                <p className="report-pivot-section-empty">{display.empty}</p>
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}

export function SavedReportMarkdown({ content }: { content: string }) {
  return (
    <article className="report-content report-pivot-markdown">
      {content.split("\n").map((line, index) =>
        line.startsWith("# ") ? (
          <h2 key={index}>{line.slice(2)}</h2>
        ) : line.startsWith("## ") ? (
          <h3 key={index}>{line.slice(3)}</h3>
        ) : line.startsWith("### ") ? (
          <h4 key={index}>{line.slice(4)}</h4>
        ) : line.startsWith("- ") ? (
          <p className="report-bullet" key={index}>
            {line.slice(2)}
          </p>
        ) : (
          <p key={index}>{line || "\u00a0"}</p>
        ),
      )}
    </article>
  );
}

function CountCells({
  counts,
  sourceCount,
}: {
  counts: PivotCounts;
  sourceCount: number;
}) {
  return (
    <>
      <td>{sourceCount}</td>
      <td>{counts.open}</td>
      <td>{counts.completed}</td>
      <td className={counts.critical ? "report-pivot-critical" : undefined}>
        {counts.critical}
      </td>
      <td className={counts.overdue ? "report-pivot-overdue" : undefined}>
        {counts.overdue}
      </td>
    </>
  );
}

function MetadataNote({ provenance }: { provenance: string }) {
  if (["current_authorized", "mixed"].includes(provenance))
    return (
      <p className="report-pivot-provenance">
        Ekip bilgisi, eski rapor kaynaklarının mevcut ve erişilebilir
        organizasyon kayıtlarından tamamlandı.
      </p>
    );
  if (provenance === "unassigned")
    return (
      <p className="report-pivot-provenance">
        Ekip bilgisi bulunmayan kaynaklar ayrıca gösterilir.
      </p>
    );
  return null;
}

export function ReportPivotView({
  report,
  data,
  activeKey = GENERAL_REPORT_KEY,
  onSelect = () => {},
}: {
  report: PivotReport;
  data: ReportPivotData;
  activeKey?: string;
  onSelect?: (key: string) => void;
}) {
  const id = useId();
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const selectedTeam = data.teams.find((team) => teamKey(team) === activeKey);
  const selectedKey = selectedTeam ? teamKey(selectedTeam) : GENERAL_REPORT_KEY;
  const tabs = [
    {
      key: GENERAL_REPORT_KEY,
      name: "Genel Rapor",
      sourceCount: data.general.source_count,
    },
    ...data.teams.map((team) => ({
      key: teamKey(team),
      name: team.name,
      sourceCount: team.source_count,
    })),
  ];
  const activeIndex = tabs.findIndex((tab) => tab.key === selectedKey);
  const markdown = String(
    report.markdown || report.content || report.summary || "",
  );
  const generalSources = distinctReportSources(data.general.sections);
  function selectTeam(team: PivotTeam) {
    onSelect(teamKey(team));
  }
  return (
    <div className="report-pivot">
      <div className="report-pivot-heading">
        <div>
          <span className="eyebrow">EKİP FAALİYET RAPORU</span>
          <h3>Genel görünüm ve ekip raporları</h3>
          <p>
            Önce genel raporu inceleyin, ardından bir ekibin faaliyetlerine
            geçin.
          </p>
        </div>
        <span className="report-pivot-snapshot">
          <CheckCircle2 size={15} aria-hidden="true" />
          Kayıtlı kaynak özeti
        </span>
      </div>
      <div className="report-pivot-table-wrap">
        <table className="report-pivot-table">
          <caption>
            Ekip bazında rapor özeti · {date(data.as_of)} dönemi sonu
          </caption>
          <thead>
            <tr>
              <th scope="col">Rapor / ekip</th>
              <th scope="col">Kaynak</th>
              <th scope="col">Açık</th>
              <th scope="col">Tamamlanan</th>
              <th scope="col">Kritik</th>
              <th scope="col">Geciken</th>
            </tr>
          </thead>
          <tbody>
            <tr className="report-pivot-total">
              <th scope="row">
                <button
                  type="button"
                  onClick={() => onSelect(GENERAL_REPORT_KEY)}
                >
                  <LayoutGrid size={15} aria-hidden="true" />
                  Genel Rapor
                  <ArrowUpRight size={14} aria-hidden="true" />
                </button>
              </th>
              <CountCells
                counts={data.general.counts}
                sourceCount={data.general.source_count}
              />
            </tr>
            {data.teams.map((team) => (
              <tr
                key={teamKey(team)}
                className={
                  selectedKey === teamKey(team) ? "is-selected" : undefined
                }
              >
                <th scope="row">
                  <button type="button" onClick={() => selectTeam(team)}>
                    <Users size={15} aria-hidden="true" />
                    <span>
                      {team.name}
                      {team.code && <small>{team.code}</small>}
                    </span>
                    <ArrowUpRight size={14} aria-hidden="true" />
                  </button>
                </th>
                <CountCells
                  counts={team.counts}
                  sourceCount={team.source_count}
                />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="report-pivot-table-note">
        Sayılar rapora kaydedilen kaynaklardan hesaplanır. Kritik ve geciken
        kayıtlar açık kayıtlarla kesişebilir.
      </p>
      <MetadataNote provenance={data.metadata_provenance} />
      <div
        className="report-pivot-tabs"
        role="tablist"
        aria-label="Rapor görünümü"
      >
        {tabs.map((tab, index) => (
          <button
            type="button"
            role="tab"
            key={tab.key}
            id={`${id}-tab-${index}`}
            aria-controls={`${id}-panel`}
            aria-selected={selectedKey === tab.key}
            tabIndex={selectedKey === tab.key ? 0 : -1}
            ref={(element) => {
              tabRefs.current[index] = element;
            }}
            onClick={() => onSelect(tab.key)}
            onKeyDown={(event) => {
              const next = nextReportTab(event.key, index, tabs.length);
              if (next === null) return;
              event.preventDefault();
              onSelect(tabs[next].key);
              tabRefs.current[next]?.focus();
            }}
          >
            {index === 0 ? (
              <LayoutGrid size={15} aria-hidden="true" />
            ) : (
              <Users size={15} aria-hidden="true" />
            )}
            {tab.name}
            <span>{tab.sourceCount}</span>
          </button>
        ))}
      </div>
      <section
        role="tabpanel"
        id={`${id}-panel`}
        aria-labelledby={`${id}-tab-${activeIndex}`}
        tabIndex={0}
        className="report-pivot-panel"
      >
        <div className="report-pivot-panel-heading">
          <div>
            <span className="eyebrow">
              {selectedTeam ? "EKİP RAPORU" : "YÖNETİM RAPORU"}
            </span>
            <h2>{selectedTeam?.name || "Genel Rapor"}</h2>
          </div>
          <Badge>
            {selectedTeam?.source_count ?? data.general.source_count} kaynak
          </Badge>
        </div>
        {selectedTeam ? (
          <>
            <p className="report-pivot-panel-note">
              Bu ekibin rapora kaydedilmiş faaliyetleri ve kaynak durumları.
            </p>
            <MetadataNote provenance={selectedTeam.metadata_provenance} />
            <StructuredSections
              sections={selectedTeam.sections}
              order={data.section_order}
            />
          </>
        ) : (
          <>
            {markdown ? (
              <SavedReportMarkdown content={markdown} />
            ) : (
              <div className="report-pivot-unwritten">
                <EmptyState
                  title="Genel rapor özeti henüz hazırlanmadı"
                  description="Bu raporun yönetim metni henüz hazırlanmadı. Kayıtlı faaliyetlerin özeti aşağıda yer alır."
                  icon={<FileText size={26} />}
                />
                <StructuredSections
                  sections={data.general.sections}
                  order={data.section_order}
                />
              </div>
            )}
            <details className="report-pivot-source-index">
              <summary>Kaynak kayıtlar ({data.general.source_count})</summary>
              {generalSources.length ? (
                <div>
                  {generalSources.map((source) => (
                    <SourceEntry
                      key={`${source.type}:${source.id}`}
                      source={source}
                    />
                  ))}
                </div>
              ) : (
                <p className="muted">Bu raporda kayıtlı kaynak bulunmuyor.</p>
              )}
            </details>
          </>
        )}
      </section>
    </div>
  );
}

export default function ReportPivot({ report }: { report: PivotReport }) {
  const pivot = useResource<ReportPivotData>(`/reports/${report.id}/pivot`);
  const [activeKey, setActiveKey] = useState(GENERAL_REPORT_KEY);
  if (pivot.error)
    return (
      <div className="report-pivot">
        <ErrorState
          message={`Ekip raporları yüklenemedi. ${pivot.error}`}
          onRetry={pivot.refresh}
        />
      </div>
    );
  if (pivot.data && !pivotMatchesReport(pivot.data, report))
    return (
      <div className="report-pivot">
        <ErrorState
          message="Raporun kaynak sürümü değişti. Güncel ekip görünümünü yükleyin."
          onRetry={pivot.refresh}
        />
      </div>
    );
  if (!pivot.data)
    return (
      <div className="report-pivot">
        <Loading label="Genel rapor ve ekip görünümü yükleniyor…" />
      </div>
    );
  return (
    <ReportPivotView
      report={report}
      data={pivot.data}
      activeKey={activeKey}
      onSelect={setActiveKey}
    />
  );
}
