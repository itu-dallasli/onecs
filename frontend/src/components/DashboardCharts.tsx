import { useId } from "react";
import { BarChart3, Clock3, Flag, Layers3 } from "lucide-react";
import { organizationLabel } from "../lib/organization";
import { Card, SectionTitle } from "./ui";
import "../styles/dashboard-charts.css";

type Row = Record<string, unknown>;
export type UnitLoad = {
  id: string;
  label: string;
  code: string;
  work: number | null;
  cases: number | null;
  knownTotal: number;
};
export type PriorityPart = {
  key: string;
  label: string;
  count: number;
  color: string;
};
/** A missing count is unknown; it is never silently presented as zero. */
export function dashboardCount(value: unknown): number | null {
  if (
    (typeof value !== "number" && typeof value !== "string") ||
    (typeof value === "string" && !value.trim())
  )
    return null;
  const count = Number(value);
  return Number.isFinite(count) && Number.isInteger(count) && count >= 0
    ? count
    : null;
}
export function buildUnitLoad(units: Row[]): UnitLoad[] {
  return units
    .map((unit, index) => {
      const work = dashboardCount(unit.open_work ?? unit.work_count),
        cases = dashboardCount(unit.open_cases ?? unit.case_count);
      return {
        id: String(unit.id ?? unit.code ?? index),
        label: organizationLabel(
          typeof unit.name === "string" ? unit.name : "Birim",
        ),
        code: typeof unit.code === "string" ? unit.code : "",
        work,
        cases,
        knownTotal: (work ?? 0) + (cases ?? 0),
      };
    })
    .sort(
      (a, b) =>
        b.knownTotal - a.knownTotal || a.label.localeCompare(b.label, "tr"),
    );
}
export function buildPriorityBreakdown(agenda: Row[]): {
  total: number;
  parts: PriorityPart[];
} {
  const parts: PriorityPart[] = [
    { key: "CRITICAL", label: "Kritik", count: 0, color: "#b85560" },
    { key: "HIGH", label: "Yüksek", count: 0, color: "#b59445" },
    { key: "NORMAL", label: "Normal", count: 0, color: "#357e9e" },
    {
      key: "UNKNOWN",
      label: "Diğer / belirtilmedi",
      count: 0,
      color: "#a2b0bd",
    },
  ];
  for (const record of agenda) {
    const priority = String(record.priority || "").toUpperCase();
    const part = parts.find((item) => item.key === priority) || parts[3];
    part.count += 1;
  }
  return {
    total: agenda.length,
    parts: parts.filter((part) => part.count > 0),
  };
}
const amount = (value: number | null) =>
  value === null ? "veri yok" : value.toLocaleString("tr-TR");
function snapshotLabel(value?: string) {
  if (!value) return "Güncelleme zamanı alınamadı";
  const time = new Date(value);
  return Number.isNaN(time.getTime())
    ? "Güncelleme zamanı alınamadı"
    : `Anlık özet · ${time.toLocaleString("tr-TR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}`;
}
export default function DashboardCharts({
  units,
  agenda,
  kpis,
  updatedAt,
}: {
  units: Row[];
  agenda: Row[];
  kpis: Row;
  updatedAt?: string;
}) {
  const chartId = useId();
  const rows = buildUnitLoad(units);
  const max = Math.max(1, ...rows.map((row) => row.knownTotal));
  const priorities = buildPriorityBreakdown(agenda);
  const circumference = 2 * Math.PI * 58;
  let offset = 0;
  const overdue = dashboardCount(kpis.overdue),
    decisions = dashboardCount(kpis.decisions);
  return (
    <section className="dashboard-insights" aria-label="Operasyon grafikleri">
      <Card className="dashboard-chart-card unit-load-chart">
        <SectionTitle
          title="Birimlerin açık iş ve vaka yükü"
          description="Güncel kayıt adedi · zaman içindeki değişim değildir"
          actions={
            <span className="chart-heading-icon">
              <BarChart3 size={20} />
            </span>
          }
        />
        <div className="chart-legend" aria-label="Grafik açıklaması">
          <span>
            <i className="work" />
            Açık iş
          </span>
          <span>
            <i className="case" />
            Açık vaka
          </span>
          <small>{rows.length} birim</small>
        </div>
        {rows.length ? (
          <div
            className="unit-load-scroll"
            tabIndex={rows.length > 6 ? 0 : undefined}
            aria-label="Birimlerin açık iş ve vaka sayıları"
          >
            <ol className="unit-load-list">
              {rows.map((row) => (
                <li key={row.id}>
                  <div className="unit-load-heading">
                    <div>
                      <strong>{row.label}</strong>
                      <span>{row.code}</span>
                    </div>
                    <span className="unit-load-values">
                      <b>{amount(row.work)}</b> iş{" "}
                      <span aria-hidden="true">/</span>
                      <b>{amount(row.cases)}</b> vaka
                    </span>
                  </div>
                  <div className="unit-load-track" aria-hidden="true">
                    <span
                      className="unit-load-work"
                      style={{ width: `${((row.work ?? 0) / max) * 100}%` }}
                    />
                    <span
                      className="unit-load-case"
                      style={{ width: `${((row.cases ?? 0) / max) * 100}%` }}
                    />
                  </div>
                </li>
              ))}
            </ol>
          </div>
        ) : (
          <div className="dashboard-chart-empty">
            <Layers3 size={25} />
            <strong>Bu kapsamda birim özeti yok.</strong>
            <p>
              Görüntülemeye yetkili olduğunuz kayıtlar hazır olduğunda yük
              dağılımı burada görünür.
            </p>
          </div>
        )}
        <div className="chart-footnote">
          <span>{snapshotLabel(updatedAt)}</span>
          <span>Çubuklar en yüksek kayıt adedine göre ölçeklenir.</span>
        </div>
      </Card>
      <Card className="dashboard-chart-card priority-load-chart">
        <SectionTitle
          title="Öncelik ve süre takibi"
          description="Gösterilen gündem kayıtları ve yönetim göstergeleri"
          actions={
            <span className="chart-heading-icon">
              <Flag size={19} />
            </span>
          }
        />
        {priorities.total ? (
          <figure
            className="priority-figure"
            aria-labelledby={`${chartId}-caption`}
          >
            <div className="priority-donut">
              <svg
                viewBox="0 0 160 160"
                role="img"
                aria-labelledby={`${chartId}-title ${chartId}-description`}
              >
                <title id={`${chartId}-title`}>
                  Öncelikli gündemin öncelik dağılımı
                </title>
                <desc
                  id={`${chartId}-description`}
                >{`${priorities.total} gündem kaydı. ${priorities.parts.map((part) => `${part.label}: ${part.count}`).join(". ")}. Bu grafik tüm portföyü kapsamaz.`}</desc>
                <circle
                  className="priority-donut-base"
                  cx="80"
                  cy="80"
                  r="58"
                  fill="none"
                  strokeWidth="17"
                />
                {priorities.parts.map((part) => {
                  const length =
                    (part.count / priorities.total) * circumference;
                  const start = offset;
                  offset += length;
                  return (
                    <circle
                      key={part.key}
                      cx="80"
                      cy="80"
                      r="58"
                      fill="none"
                      stroke={part.color}
                      strokeWidth="17"
                      strokeDasharray={`${length} ${circumference - length}`}
                      strokeDashoffset={-start}
                      transform="rotate(-90 80 80)"
                    />
                  );
                })}
                <text
                  x="80"
                  y="78"
                  textAnchor="middle"
                  className="priority-donut-count"
                  aria-hidden="true"
                >
                  {priorities.total}
                </text>
                <text
                  x="80"
                  y="98"
                  textAnchor="middle"
                  className="priority-donut-caption"
                  aria-hidden="true"
                >
                  gündem kaydı
                </text>
              </svg>
            </div>
            <ul className="priority-legend" aria-label="Öncelik sayıları">
              {priorities.parts.map((part) => (
                <li key={part.key}>
                  <i style={{ background: part.color }} />
                  <span>{part.label}</span>
                  <strong>{part.count}</strong>
                </li>
              ))}
            </ul>
            <figcaption id={`${chartId}-caption`}>
              Yalnız gösterilen {priorities.total} öncelikli gündem kaydı; tüm
              portföyün dağılımı değildir.
            </figcaption>
          </figure>
        ) : (
          <div className="dashboard-chart-empty compact">
            <Flag size={23} />
            <strong>Öncelikli gündem kaydı bulunmuyor.</strong>
          </div>
        )}
        <dl className="dashboard-timing-metrics">
          <div>
            <dt>
              <Clock3 size={16} />
              Geciken taahhüt / SLA
            </dt>
            <dd>{overdue === null ? "—" : overdue.toLocaleString("tr-TR")}</dd>
          </div>
          <div>
            <dt>
              <Flag size={16} />
              Karar bekleyen
            </dt>
            <dd>
              {decisions === null ? "—" : decisions.toLocaleString("tr-TR")}
            </dd>
          </div>
        </dl>
        <div className="chart-footnote">
          <span>
            KPI değerleri güncel yetki kapsamınızı yansıtır. Göstergeler
            kesişebilir; birlikte toplanmaz.
          </span>
        </div>
      </Card>
    </section>
  );
}
