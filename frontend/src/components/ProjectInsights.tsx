import { useEffect, useId, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  BarChart3,
  CalendarDays,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  FilePenLine,
  FileText,
  Flag,
  Layers3,
  Loader2,
  MessageSquare,
  Plus,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Target,
  Users,
} from "lucide-react";
import { api, ApiError, date, list, useResource } from "../lib/api";
import {
  Badge,
  Button,
  Drawer,
  EmptyState,
  ErrorState,
  Field,
  Loading,
  Status,
} from "./ui";
import "../styles/project-insights.css";

type ScoreKey = "delivery" | "quality" | "stakeholder" | "overall";
type Scores = Record<ScoreKey, number | null>;
type InsightPermissions = {
  manage?: boolean;
  deliverables?: boolean;
  quality?: boolean;
  report?: boolean;
  survey?: boolean;
};
type Deliverable = {
  id: string;
  title: string;
  org_id?: string;
  kind: string;
  weight: number;
  progress: number;
  evidence: string;
  quality_rating?: number | null;
  due_at?: string | null;
  version: number;
};
type Team = {
  id: string;
  org_id: string;
  org_name: string;
  weight: number;
  progress: number | null;
  version: number;
  deliverables: Deliverable[];
  coverage?: unknown;
};
type Survey = {
  id: string;
  title: string;
  version: number;
  status: string;
  questions: { id: string; label: string }[];
  invitee_ids: string[];
  responded: number;
  invited: number;
  response_rate: number;
  my_answers: Record<string, number> | null;
  my_response_version?: number | null;
  can_edit_response?: boolean;
  can_respond: boolean;
  results: {
    question_id: string;
    label: string;
    average: number | null;
    count: number;
  }[];
  closes_at?: string | null;
};
type InsightReport = {
  id: string;
  kind: string;
  status: string;
  mode?: string;
  original_markdown?: string;
  markdown?: string;
  computed_values?: Record<string, unknown>;
  reviewed_scores?: Partial<Scores>;
  sources?: unknown[];
  job?: {
    id: string;
    status: string;
    last_error?: string;
    generation_status?: string;
    fallback_reason?: string;
    context_abridged?: boolean;
  };
  version: number;
  period_start: string;
  period_end: string;
  edit_reason?: string;
  permissions?: { edit?: boolean; publish?: boolean };
  created_at?: string;
  published_at?: string;
  reviewed_by_name?: string;
};
type Insights = {
  project_id: string;
  project_version: number;
  permissions: InsightPermissions;
  teams: Team[];
  scores: Partial<Scores> & { coverage?: any; formula?: any };
  surveys: Survey[];
  reports: InsightReport[];
  trend?: unknown[];
  stakeholders?: { id: string; display_name: string; org_id?: string }[];
  allowed_teams?: { id: string; name: string }[];
  detail_restricted?: boolean;
};
const scoreLabels: Record<ScoreKey, string> = {
  delivery: "Teslimat ilerlemesi",
  quality: "Teslimat kalitesi",
  stakeholder: "Paydaş değerlendirmesi",
  overall: "Başarı endeksi",
};
const reportNames: Record<string, string> = {
  DAILY: "Günlük durum",
  WEEKLY: "Haftalık durum",
  CLOSURE: "Kapanış değerlendirmesi",
};
const statusNames: Record<string, string> = {
  GENERATING: "Hazırlanıyor",
  READY: "İncelemeye hazır",
  PUBLISHED: "Yayınlandı",
  FAILED: "Hazırlanamadı",
  QUEUED: "Sırada",
  RUNNING: "İşleniyor",
  SUCCEEDED: "Tamamlandı",
  RETRYING: "Yeniden deneniyor",
  UNKNOWN: "Sonuç doğrulanmalı",
  OPEN: "Yanıta açık",
  CLOSED: "Yanıta kapalı",
};
export function insightScore(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n =
    typeof value === "number"
      ? value
      : typeof value === "string"
        ? Number(value)
        : NaN;
  return Number.isFinite(n) && n >= 0 && n <= 100 ? n : null;
}
export function parseReviewedScores(input: Record<ScoreKey, string>): Scores {
  const output = {} as Scores;
  for (const key of Object.keys(scoreLabels) as ScoreKey[]) {
    if (!input[key].trim()) {
      output[key] = null;
      continue;
    }
    const value = insightScore(input[key]);
    if (value === null)
      throw new Error(`${scoreLabels[key]} 0–100 arasında olmalıdır.`);
    output[key] = value;
  }
  return output;
}
export function normalizeInsightTrend(value: unknown) {
  if (!Array.isArray(value)) return [];
  const byDate = new Map<string, { date: string; value: number }>();
  for (const item of value) {
    if (!item || typeof item !== "object") continue;
    const x = item as any;
    const timestamp = x.date || x.recorded_at || x.created_at || x.at;
    const score = insightScore(x.progress ?? x.delivery ?? x.scores?.delivery);
    if (
      !timestamp ||
      Number.isNaN(new Date(timestamp).getTime()) ||
      score === null
    )
      continue;
    byDate.set(String(timestamp), { date: String(timestamp), value: score });
  }
  return Array.from(byDate.values())
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
    .slice(-12);
}
function scoreText(value: unknown) {
  const score = insightScore(value);
  return score === null
    ? "Veri yok"
    : `${Number.isInteger(score) ? score : score.toFixed(1)}`;
}
function localDateInput(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
function modeLabel(mode?: string) {
  return mode === "AI"
    ? "AI taslağı"
    : mode === "RULE_BASED"
      ? "Kurallı kaynak özeti"
      : mode
        ? "Kaynak özeti"
        : "Henüz hazırlanmadı";
}
function fallbackExplanation(reason?: string) {
  const messages: Record<string, string> = {
    input_limit: "Kaynak özeti modelin giriş sınırını aştı.",
    budget_or_request_limit: "Modelin kullanım bütçesi veya istek sınırına ulaşıldı.",
    unconfigured: "Etkin yapay zekâ bağlantısı bulunmuyor.",
    output_truncated: "Model yanıtı çıktı sınırına ulaştığı için doğrulanamadı.",
    invalid_json: "Modelin yanıt biçimi doğrulanamadı.",
    invalid_citations: "Modelin kaynak atıfları doğrulanamadı.",
    previous_request_pending_or_unknown: "Önceki model isteğinin sonucu henüz doğrulanamadı.",
    failed: "Model yanıtı veya bağlantısı doğrulanamadı.",
  };
  return reason && messages[reason] ? messages[reason] : "";
}
function Download({
  text,
  name,
  type,
}: {
  text: string;
  name: string;
  type: string;
}) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
export function printableProjectReport(title: string, markdown: string) {
  return `<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHtml(title)}</title><style>body{font:15px/1.8 system-ui,sans-serif;color:#163047;max-width:900px;margin:50px auto;padding:0 25px}header{border-bottom:2px solid #c9a85d;padding-bottom:20px;margin-bottom:30px}h1{font-size:28px}small{color:#678297}pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere}@media print{body{margin:15mm;max-width:none;padding:0}}</style></head><body><header><small>onecs · PROJE YÖNETİMİ</small><h1>${escapeHtml(title)}</h1></header><pre>${escapeHtml(markdown)}</pre></body></html>`;
}
function InlineMarkdown({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((part, i) =>
        part.startsWith("**") && part.endsWith("**") ? (
          <strong key={i}>{part.slice(2, -2)}</strong>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}
function MarkdownPreview({ text }: { text: string }) {
  const lines = text.split("\n");
  const content: ReactNode[] = [];
  let code: string[] | null = null;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith("```")) {
      if (code) {
        content.push(
          <pre key={`code-${i}`}>
            <code>{code.join("\n")}</code>
          </pre>,
        );
        code = null;
      } else code = [];
      continue;
    }
    if (code) {
      code.push(line);
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)/);
    if (heading) {
      content.push(
        heading[1].length === 1 ? (
          <h2 key={i}>
            <InlineMarkdown text={heading[2]} />
          </h2>
        ) : (
          <h3 key={i}>
            <InlineMarkdown text={heading[2]} />
          </h3>
        ),
      );
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      content.push(
        <p className="pi-markdown-bullet" key={i}>
          <InlineMarkdown text={line.replace(/^\s*[-*]\s+/, "")} />
        </p>,
      );
      continue;
    }
    content.push(
      <p key={i}>
        <InlineMarkdown text={line || " "} />
      </p>,
    );
  }
  if (code)
    content.push(
      <pre key="code-open">
        <code>{code.join("\n")}</code>
      </pre>,
    );
  return <article className="pi-markdown">{content}</article>;
}
function Metric({
  label,
  value,
  description,
  primary = false,
}: {
  label: string;
  value: unknown;
  description: string;
  primary?: boolean;
}) {
  const score = insightScore(value);
  return (
    <div className={`pi-metric ${primary ? "is-primary" : ""}`}>
      <span>{label}</span>
      <strong>
        {scoreText(value)}
        {score !== null && <small>/100</small>}
      </strong>
      <p>{description}</p>
    </div>
  );
}
function Trend({ data }: { data: unknown }) {
  const id = useId();
  const points = normalizeInsightTrend(data);
  if (points.length < 2)
    return (
      <div className="pi-trend-empty">
        <BarChart3 size={23} />
        <div>
          <strong>Değişimler oldukça eğilim oluşacak</strong>
          <p>
            En az iki tarihli teslimat ölçümü gerektiğinden geçmiş veri
            üretilmez.
          </p>
        </div>
      </div>
    );
  const width = 620,
    height = 162,
    pad = 20;
  const span = Math.max(1, points.length - 1);
  const xy = points.map((point, i) => ({
    x: pad + (i / span) * (width - 2 * pad),
    y: height - pad - (point.value / 100) * (height - 2 * pad),
    ...point,
  }));
  const path = xy
    .map(
      (point, i) =>
        `${i ? "L" : "M"}${point.x.toFixed(1)},${point.y.toFixed(1)}`,
    )
    .join(" ");
  return (
    <figure className="pi-trend">
      <figcaption id={id}>Teslimat ilerlemesinin tarihli ölçümleri</figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby={id}>
        {[0, 25, 50, 75, 100].map((n) => (
          <g key={n}>
            <line
              x1={pad}
              y1={height - pad - (n / 100) * (height - 2 * pad)}
              x2={width - pad}
              y2={height - pad - (n / 100) * (height - 2 * pad)}
              stroke="#e4edf4"
              strokeDasharray="3 4"
            />
            <text
              x={0}
              y={height - pad - (n / 100) * (height - 2 * pad) + 4}
              fill="#8ba0b1"
              fontSize="9"
            >
              {n}
            </text>
          </g>
        ))}
        <path
          d={`${path} L${width - pad},${height - pad} L${pad},${height - pad} Z`}
          fill="#eaf4fb"
        />
        <path d={path} fill="none" stroke="#367fab" strokeWidth="2.5" />
        {xy.map((p) => (
          <circle
            key={p.date}
            cx={p.x}
            cy={p.y}
            r="3.2"
            fill="#fff"
            stroke="#367fab"
            strokeWidth="2"
          >
            <title>
              {date(p.date)} · %{p.value}
            </title>
          </circle>
        ))}
      </svg>
      <div className="pi-trend-labels">
        <span>{date(points[0].date)}</span>
        <span>{date(points[Math.floor(points.length / 2)].date)}</span>
        <span>{date(points[points.length - 1].date)}</span>
      </div>
      <details>
        <summary>Ölçüm tarihlerini ve değerlerini gör</summary>
        <div className="pi-trend-values">
          {points.map((p) => (
            <span key={p.date}>
              {date(p.date, true)} <strong>%{p.value}</strong>
            </span>
          ))}
        </div>
      </details>
    </figure>
  );
}

export default function ProjectInsights({
  project,
  onUpdated,
}: {
  project: any;
  onUpdated?: () => void;
}) {
  const [requestedTab, setTab] = useState("overview");
  const tabId = useId();
  const [deliverable, setDeliverable] = useState<{
    team?: Team;
    record?: Deliverable;
  } | null>(null);
  const [teamEdit, setTeamEdit] = useState<Team | "new" | null>(null);
  const [surveyCreate, setSurveyCreate] = useState(false);
  const [reportCreate, setReportCreate] = useState<
    "DAILY" | "WEEKLY" | "CLOSURE" | null
  >(null);
  const [selectedReport, setSelectedReport] = useState<InsightReport | null>(
    null,
  );
  const r = useResource<Insights>(`/projects/${project.id}/insights`);
  const data = r.data;
  const tab =
    data?.detail_restricted && requestedTab !== "surveys"
      ? "overview"
      : requestedTab;
  const permissions: InsightPermissions = [
    "PLANNED",
    "IN_PROGRESS",
    "WAITING",
    "COMPLETED",
  ].includes(project.status)
    ? data?.permissions || {}
    : {};
  const teams = list<Team>(data?.teams);
  const surveys = list<Survey>(data?.surveys);
  const reports = list<InsightReport>(data?.reports);
  const refresh = () => {
    r.refresh();
    onUpdated?.();
  };
  return (
    <section className="project-insights">
      <header className="pi-header">
        <span className="pi-section-icon">
          <BarChart3 size={21} />
        </span>
        <div>
          <div className="eyebrow">PROJEYİ KAYNAĞINDAN DEĞERLENDİR</div>
          <h3>İlerleme ve yönetim içgörüleri</h3>
          <p>
            Ekip teslimatları, paydaş geri bildirimi ve incelenebilir raporlar.
          </p>
        </div>
        <button
          className="icon-button"
          aria-label="Proje içgörülerini yenile"
          onClick={r.refresh}
        >
          <RefreshCw size={17} />
        </button>
      </header>
      <div className="pi-tabs" role="tablist" aria-label="Proje içgörüleri">
        {[
          ["overview", "Genel bakış", BarChart3],
          ["teams", "Ekip ilerlemesi", Users],
          ["surveys", "Paydaş anketleri", MessageSquare],
          ["reports", "Günlük / haftalık", FileText],
          ["closure", "Kapanış kalitesi", ShieldCheck],
        ]
          .filter(
            ([key]) =>
              !data?.detail_restricted ||
              ["overview", "surveys"].includes(String(key)),
          )
          .map(([key, label, Icon]: any) => (
            <button
              key={key}
              id={`${tabId}-${key}`}
              role="tab"
              tabIndex={tab === key ? 0 : -1}
              aria-controls={`${tabId}-panel`}
              aria-selected={tab === key}
              className={tab === key ? "active" : ""}
              onClick={() => setTab(key)}
              onKeyDown={(event) => {
                if (
                  !["ArrowRight", "ArrowLeft", "Home", "End"].includes(
                    event.key,
                  )
                )
                  return;
                event.preventDefault();
                const buttons = Array.from(
                  event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>(
                    '[role="tab"]',
                  ) || [],
                );
                const index = buttons.indexOf(event.currentTarget);
                const next =
                  event.key === "Home"
                    ? 0
                    : event.key === "End"
                      ? buttons.length - 1
                      : (index +
                          (event.key === "ArrowRight" ? 1 : -1) +
                          buttons.length) %
                        buttons.length;
                buttons[next]?.click();
                buttons[next]?.focus();
              }}
            >
              <Icon size={15} />
              {label}
            </button>
          ))}
      </div>
      {r.loading && !data ? (
        <Loading label="Projenin kaynak ölçümleri hazırlanıyor…" />
      ) : r.error && !data ? (
        <ErrorState message={r.error} onRetry={r.refresh} />
      ) : data ? (
        <div
          className="pi-content"
          role="tabpanel"
          id={`${tabId}-panel`}
          aria-labelledby={`${tabId}-${tab}`}
        >
          {r.error && <ErrorState message={r.error} onRetry={r.refresh} />}
          {data.detail_restricted && (
            <div className="info-strip">
              Bu projede özet görüntüleme kapsamındasınız. Teslimat ayrıntıları
              ve iç raporlar paylaşılmaz; davetli olduğunuz paydaş anketlerini
              yanıtlayabilirsiniz.
            </div>
          )}
          {tab === "overview" && !data.detail_restricted && (
            <>
              <div className="pi-score-grid">
                <Metric
                  label="Teslimat ilerlemesi"
                  value={data.scores?.delivery}
                  description="Ekip ve teslimat ağırlıklarına göre hesaplanır."
                />
                <Metric
                  label="Teslimat kalitesi"
                  value={data.scores?.quality}
                  description="Kanıta dayalı kalite değerlendirmelerinden."
                />
                <Metric
                  label="Paydaş değerlendirmesi"
                  value={data.scores?.stakeholder}
                  description="Yanıt veren yetkili paydaşların görüşü."
                />
                <Metric
                  label="Başarı endeksi"
                  value={data.scores?.overall}
                  description="Olasılık değildir; bileşenlerin ağırlıklı endeksidir."
                  primary
                />
              </div>
              <div className="pi-method-note">
                <Target size={16} />
                <p>
                  <strong>Ölçüm yöntemi açık.</strong> Teslimat %50, kalite %30,
                  paydaş görüşü %20. Eksik bileşen sıfır sayılmaz; üç bileşen
                  tamamlanmadan başarı endeksi hesaplanmaz. Proje yöneticisinin
                  %{project.progress ?? 0} ilerleme beyanı ayrı bir ölçümdür.
                </p>
              </div>
              <Coverage data={data.scores?.coverage} />
              <TeamBars teams={teams} />
              <Trend data={data.trend || []} />
            </>
          )}
          {tab === "teams" && (
            <>
              <div className="pi-subhead">
                <div>
                  <h4>Ekip bazında teslimatlar</h4>
                  <p>
                    Ağırlıklar yapılan işin payını gösterir; kişi performansı
                    sıralanmaz.
                  </p>
                </div>
                {permissions.deliverables && (
                  <div className="pi-actions">
                    <Button
                      variant="secondary"
                      onClick={() => setTeamEdit("new")}
                    >
                      <Users size={15} />
                      Ekip ağırlığı
                    </Button>
                    <Button onClick={() => setDeliverable({})}>
                      <Plus size={15} />
                      Teslimat ekle
                    </Button>
                  </div>
                )}
              </div>
              {teams.length ? (
                teams.map((team) => (
                  <div className="pi-team" key={team.org_id}>
                    <div className="pi-team-header">
                      <div>
                        <strong>{team.org_name}</strong>
                        <span>
                          Ekip ağırlığı {team.weight} ·{" "}
                          {list(team.deliverables).length} teslimat
                        </span>
                      </div>
                      <b>
                        {team.progress === null
                          ? "Veri yok"
                          : `%${scoreText(team.progress)}`}
                      </b>
                      {permissions.deliverables && (
                        <button
                          className="text-button"
                          onClick={() => setTeamEdit(team)}
                        >
                          Ağırlığı düzenle
                        </button>
                      )}
                    </div>
                    <div className="progress-track">
                      <span
                        style={{
                          width: `${insightScore(team.progress) ?? 0}%`,
                        }}
                      />
                    </div>
                    {list<Deliverable>(team.deliverables).length ? (
                      <div className="pi-deliverables">
                        {list<Deliverable>(team.deliverables).map((item) => (
                          <div className="pi-deliverable" key={item.id}>
                            <span className="pi-delivery-icon">
                              {item.kind === "MILESTONE" ? (
                                <Flag size={16} />
                              ) : (
                                <Layers3 size={16} />
                              )}
                            </span>
                            <div>
                              <strong>{item.title}</strong>
                              <small>
                                {item.kind === "MILESTONE"
                                  ? "Kilometre taşı"
                                  : "Teslimat"}{" "}
                                · Ağırlık {item.weight}
                                {item.due_at ? ` · ${date(item.due_at)}` : ""}
                              </small>
                              {item.evidence && <p>{item.evidence}</p>}
                            </div>
                            <div className="pi-delivery-numbers">
                              <b>%{scoreText(item.progress)}</b>
                              <span>
                                {item.quality_rating
                                  ? `${item.quality_rating}/5 kalite`
                                  : "Kalite bekliyor"}
                              </span>
                            </div>
                            {(permissions.deliverables ||
                              permissions.quality) && (
                              <button
                                className="icon-button"
                                aria-label={`${item.title} teslimatını düzenle`}
                                onClick={() =>
                                  setDeliverable({ team, record: item })
                                }
                              >
                                <FilePenLine size={17} />
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="pi-muted">
                        Bu ekip için teslimat planı henüz girilmedi; ilerleme
                        değeri üretilmez.
                      </p>
                    )}
                  </div>
                ))
              ) : (
                <EmptyState
                  title="Teslimat planı henüz oluşmadı"
                  description="Yetkili proje yöneticisi ekip ağırlıklarını ve beklenen teslimatları tanımlayabilir."
                  icon={<Target size={28} />}
                />
              )}
            </>
          )}
          {tab === "surveys" && (
            <>
              <div className="pi-subhead">
                <div>
                  <h4>Yetkili paydaş görüşleri</h4>
                  <p>
                    1–5 değerlendirme; yanıtlayan sayısı ve örneklemle birlikte.
                  </p>
                </div>
                {permissions.survey && (
                  <Button onClick={() => setSurveyCreate(true)}>
                    <Plus size={15} />
                    Anket oluştur
                  </Button>
                )}
              </div>
              {surveys.length ? (
                surveys.map((survey) => (
                  <SurveyCard
                    key={survey.id}
                    projectId={project.id}
                    survey={survey}
                    canManage={!!permissions.survey}
                    onChanged={refresh}
                  />
                ))
              ) : (
                <EmptyState
                  title="Henüz paydaş değerlendirmesi yok"
                  description="Yetkili paydaşlara sorulacak soruları ve son yanıt tarihini belirleyin."
                  icon={<MessageSquare size={28} />}
                />
              )}
            </>
          )}
          {(tab === "reports" || tab === "closure") && (
            <>
              <div className="pi-subhead">
                <div>
                  <h4>
                    {tab === "closure"
                      ? "Kapanış kalite değerlendirmesi"
                      : "Günlük ve haftalık yönetim raporları"}
                  </h4>
                  <p>
                    {tab === "closure"
                      ? "Hesaplanan ölçümler, AI önerisi ve yönetici incelemesi ayrı tutulur."
                      : "Belirlediğiniz dönem için kaynaklı taslak; insan kontrolüyle yayın."}
                  </p>
                </div>
                {(tab === "closure"
                  ? permissions.quality
                  : permissions.report) && (
                  <Button
                    onClick={() =>
                      setReportCreate(tab === "closure" ? "CLOSURE" : "WEEKLY")
                    }
                  >
                    <Sparkles size={15} />
                    {tab === "closure"
                      ? "Değerlendirme hazırla"
                      : "Rapor hazırla"}
                  </Button>
                )}
              </div>
              {tab === "closure" && (
                <div className="pi-method-note">
                  <ShieldCheck size={17} />
                  <p>
                    Başarı endeksi projenin teslimat, kalite ve paydaş
                    verisinden hesaplanır. AI çıktısı öneridir. Yönetici kendi
                    gerekçeli skor ve metin incelemesini ayrı kaydeder; yayın
                    işlemi projeyi kapatmaz.
                  </p>
                </div>
              )}
              {reports.filter((item) =>
                tab === "closure"
                  ? item.kind === "CLOSURE"
                  : item.kind !== "CLOSURE",
              ).length ? (
                <div className="pi-reports">
                  {reports
                    .filter((item) =>
                      tab === "closure"
                        ? item.kind === "CLOSURE"
                        : item.kind !== "CLOSURE",
                    )
                    .map((report) => (
                      <button
                        className="pi-report-row"
                        key={report.id}
                        onClick={() => setSelectedReport(report)}
                      >
                        <span className="pi-report-icon">
                          <FileText size={19} />
                        </span>
                        <span>
                          <strong>
                            {reportNames[report.kind] || "Proje raporu"}
                          </strong>
                          <small>
                            {date(report.period_start)} —{" "}
                            {date(report.period_end)} · {modeLabel(report.mode)}
                          </small>
                        </span>
                        <Badge
                          tone={
                            report.status === "PUBLISHED"
                              ? "success"
                              : report.status === "FAILED"
                                ? "danger"
                                : "neutral"
                          }
                        >
                          {statusNames[report.status] || "Taslak"}
                        </Badge>
                        <ChevronRight size={17} />
                      </button>
                    ))}
                </div>
              ) : (
                <EmptyState
                  title={
                    tab === "closure"
                      ? "Kapanış değerlendirmesi henüz hazırlanmadı"
                      : "Bu proje için rapor henüz hazırlanmadı"
                  }
                  description="Rapor işi kalıcı olarak kaydedilir; hazırlanma durumunu bu alanda izleyebilirsiniz."
                  icon={<FileText size={28} />}
                />
              )}
            </>
          )}
        </div>
      ) : null}
      {deliverable && (
        <DeliverableEditor
          projectId={project.id}
          teams={teams}
          selection={deliverable}
          allowedTeams={data?.allowed_teams || []}
          canDelivery={!!permissions.deliverables}
          canQuality={!!permissions.quality}
          onClose={() => setDeliverable(null)}
          onSaved={() => {
            setDeliverable(null);
            refresh();
          }}
        />
      )}
      {teamEdit && (
        <TeamWeightEditor
          projectId={project.id}
          selection={teamEdit}
          teams={teams}
          allowedTeams={data?.allowed_teams || []}
          onClose={() => setTeamEdit(null)}
          onSaved={() => {
            setTeamEdit(null);
            refresh();
          }}
        />
      )}
      {surveyCreate && (
        <SurveyCreator
          projectId={project.id}
          stakeholders={data?.stakeholders || []}
          onClose={() => setSurveyCreate(false)}
          onSaved={() => {
            setSurveyCreate(false);
            refresh();
          }}
        />
      )}
      {reportCreate && (
        <ReportCreator
          projectId={project.id}
          initialKind={reportCreate}
          onClose={() => setReportCreate(null)}
          onCreated={(report) => {
            setReportCreate(null);
            setSelectedReport(report);
            refresh();
          }}
        />
      )}
      {selectedReport && (
        <ProjectReportEditor
          key={selectedReport.id}
          projectId={project.id}
          initial={selectedReport}
          permissions={permissions}
          projectCompleted={project.status === "COMPLETED"}
          onClose={() => setSelectedReport(null)}
          onChanged={refresh}
        />
      )}
    </section>
  );
}
function Coverage({ data }: { data: any }) {
  if (!data || typeof data !== "object")
    return (
      <p className="pi-source-caption">
        Eksik veri veya paydaş yanıtı, ölçüm kapsamını tamamlamaz.
      </p>
    );
  const labels: Record<string, string> = {
    deliverables: "Teslimat",
    completed_deliverables: "Tamamlanan",
    rated_deliverables: "Kalitesi değerlendirilen",
    quality_rated: "Kalitesi değerlendirilen",
    responses: "Paydaş yanıtı",
    responded: "Yanıtlayan",
    invited: "Davetli",
    survey_responses: "Paydaş yanıtı",
    response_rate: "Yanıt oranı",
    teams: "Ekip",
    total_deliverables: "Toplam teslimat",
    rated: "Değerlendirilen",
    survey_invited: "Davetli paydaş",
    survey_responded: "Yanıtlayan paydaş",
    unplanned_teams: "Planı eksik ekip",
  };
  const entries = Object.entries(data).filter(
    ([key, value]) =>
      key in labels && (typeof value === "number" || typeof value === "string"),
  );
  return (
    <div className="pi-coverage">
      {entries.map(([key, value]) => (
        <span key={key}>
          <strong>
            {key === "response_rate" ? `%${value}` : String(value)}
          </strong>
          {labels[key]}
        </span>
      ))}
    </div>
  );
}
function TeamBars({ teams }: { teams: Team[] }) {
  return (
    <div className="pi-team-bars">
      <h4>Ekipler nasıl ilerliyor?</h4>
      {teams.length ? (
        teams.map((team) => (
          <div className="pi-team-bar" key={team.org_id}>
            <span>{team.org_name}</span>
            <div className="progress-track">
              <span style={{ width: `${insightScore(team.progress) ?? 0}%` }} />
            </div>
            <b>
              {team.progress === null ? "—" : `%${scoreText(team.progress)}`}
            </b>
          </div>
        ))
      ) : (
        <p className="pi-muted">
          Ekip planı ve teslimatlar girildiğinde hesaplanır.
        </p>
      )}
    </div>
  );
}
function DeliverableEditor({
  projectId,
  teams,
  selection,
  allowedTeams,
  canDelivery,
  canQuality,
  onClose,
  onSaved,
}: {
  projectId: string;
  teams: Team[];
  selection: { team?: Team; record?: Deliverable };
  allowedTeams: { id: string; name: string }[];
  canDelivery: boolean;
  canQuality: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const item = selection.record;
  const [title, setTitle] = useState(item?.title || "");
  const [org, setOrg] = useState(
    selection.team?.org_id || teams[0]?.org_id || "",
  );
  const [kind, setKind] = useState(item?.kind || "DELIVERABLE");
  const [weight, setWeight] = useState(item?.weight || 1);
  const [progress, setProgress] = useState(item?.progress || 0);
  const [evidence, setEvidence] = useState(item?.evidence || "");
  const [quality, setQuality] = useState(
    item?.quality_rating ? String(item.quality_rating) : "",
  );
  const [due, setDue] = useState(
    item?.due_at ? localDateInput(item.due_at) : "",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Drawer
      title={
        item
          ? canDelivery
            ? "Teslimatı düzenle"
            : "Teslimat kalitesini değerlendir"
          : "Teslimat veya kilometre taşı ekle"
      }
      subtitle="KAYNAKLI İLERLEME ÖLÇÜMÜ"
      onClose={onClose}
    >
      <form
        className="stack-form"
        onSubmit={async (e: FormEvent) => {
          e.preventDefault();
          setError("");
          if ((progress > 0 || quality) && !evidence.trim()) {
            setError(
              "İlerleme veya kalite değerlendirmesi için kanıt / sonuç açıklaması girin.",
            );
            return;
          }
          setBusy(true);
          try {
            await api(
              `/projects/${projectId}/deliverables${item ? `/${item.id}` : ""}`,
              {
                method: item ? "PATCH" : "POST",
                body: {
                  ...(item ? { version: item.version } : {}),
                  ...(canDelivery
                    ? {
                        title,
                        org_id: org,
                        kind,
                        weight: Number(weight),
                        progress: Number(progress),
                        due_at: due ? new Date(due).toISOString() : null,
                      }
                    : {}),
                  evidence,
                  ...(canQuality
                    ? { quality_rating: quality ? Number(quality) : null }
                    : {}),
                },
              },
            );
            onSaved();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label="Teslimat başlığı">
          <input
            required
            maxLength={240}
            value={title}
            disabled={!canDelivery}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Örn. Ayrıcalıklı hesapların geçişi"
          />
        </Field>
        <div className="form-grid">
          <Field label="Sorumlu ekip">
            <select
              required
              value={org}
              disabled={!!item || !canDelivery}
              onChange={(e) => setOrg(e.target.value)}
            >
              <option value="">Ekip seçin</option>
              {(allowedTeams.length
                ? allowedTeams
                : selection.team
                  ? [
                      {
                        id: selection.team.org_id,
                        name: selection.team.org_name,
                      },
                    ]
                  : []
              ).map((x) => (
                <option value={x.id} key={x.id}>
                  {x.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Kayıt türü">
            <select
              value={kind}
              disabled={!canDelivery}
              onChange={(e) => setKind(e.target.value)}
            >
              <option value="DELIVERABLE">Teslimat</option>
              <option value="MILESTONE">Kilometre taşı</option>
            </select>
          </Field>
        </div>
        <div className="form-grid">
          <Field label="Teslimat ağırlığı · 1–100">
            <input
              type="number"
              min={1}
              max={100}
              required
              value={weight}
              disabled={!canDelivery}
              onChange={(e) => setWeight(Number(e.target.value))}
            />
          </Field>
          <Field label="İlerleme · %0–100">
            <input
              type="number"
              min={0}
              max={100}
              required
              value={progress}
              disabled={!canDelivery}
              onChange={(e) => setProgress(Number(e.target.value))}
            />
          </Field>
        </div>
        <Field label="Hedef tarih">
          <input
            type="datetime-local"
            value={due}
            disabled={!canDelivery}
            onChange={(e) => setDue(e.target.value)}
          />
        </Field>
        {canQuality && (
          <Field label="Kanıta dayalı kalite değerlendirmesi">
            <select
              value={quality}
              onChange={(e) => setQuality(e.target.value)}
            >
              <option value="">Henüz değerlendirilmedi</option>
              {[1, 2, 3, 4, 5].map((n) => (
                <option value={n} key={n}>
                  {n}/5
                </option>
              ))}
            </select>
          </Field>
        )}
        <Field
          label="Kanıt / yapılan iş ve sonuç"
          hint="İlerleme sıfırdan büyükse veya kalite değerlendirmesi varsa zorunludur. Kaynak referansını ve ölçülebilir sonucu ekleyin."
        >
          <textarea
            required={progress > 0 || !!quality}
            rows={4}
            value={evidence}
            onChange={(e) => setEvidence(e.target.value)}
          />
        </Field>
        <div className="info-strip">
          Teslimat ağırlığı ekibin kendi ilerlemesini, ekip ağırlığı ise
          projenin toplam ilerlemesini etkiler. İki ağırlık ayrı yönetilir.
        </div>
        {error && <ErrorState message={error} />}
        <div className="form-actions">
          <Button variant="secondary" type="button" onClick={onClose}>
            Vazgeç
          </Button>
          <Button disabled={busy} type="submit">
            {busy ? "Kaydediliyor…" : "Teslimatı kaydet"}
            <Check size={15} />
          </Button>
        </div>
      </form>
    </Drawer>
  );
}
function TeamWeightEditor({
  projectId,
  selection,
  teams,
  allowedTeams,
  onClose,
  onSaved,
}: {
  projectId: string;
  selection: Team | "new";
  teams: Team[];
  allowedTeams: { id: string; name: string }[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const existing = selection !== "new" ? selection : null;
  const [org, setOrg] = useState(existing?.org_id || "");
  const [weight, setWeight] = useState(existing?.weight || 1);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <Drawer
      title={existing ? "Ekip ağırlığını düzenle" : "Proje ekip planı"}
      subtitle="TESLİMAT SAYISINDAN BAĞIMSIZ AĞIRLIK"
      onClose={onClose}
    >
      <form
        className="stack-form"
        onSubmit={async (e: FormEvent) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            await api(
              `/projects/${projectId}/team-plans${existing ? `/${existing.id}` : ""}`,
              {
                method: existing ? "PATCH" : "POST",
                body: existing
                  ? { version: existing.version, weight: Number(weight) }
                  : { org_id: org, weight: Number(weight) },
              },
            );
            onSaved();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label="Ekip">
          <select
            value={org}
            required
            disabled={!!existing}
            onChange={(e) => setOrg(e.target.value)}
          >
            <option value="">Ekip seçin</option>
            {allowedTeams
              .filter((x) => existing || !teams.some((t) => t.org_id === x.id))
              .map((x) => (
                <option value={x.id} key={x.id}>
                  {x.name}
                </option>
              ))}
          </select>
        </Field>
        <Field
          label="Projedeki ağırlık · 1–100"
          hint="Ekip ağırlıkları birbirine göre oransaldır. Toplamın 100 olması gerekmez."
        >
          <input
            type="number"
            min={1}
            max={100}
            required
            value={weight}
            onChange={(e) => setWeight(Number(e.target.value))}
          />
        </Field>
        <div className="info-strip">
          Bir ekibe daha çok teslimat açılması, o ekibin proje içindeki
          ağırlığını kendiliğinden artırmaz.
        </div>
        {error && <ErrorState message={error} />}
        <Button disabled={busy} type="submit">
          Ağırlığı kaydet
          <Check size={15} />
        </Button>
      </form>
    </Drawer>
  );
}
function SurveyCreator({
  projectId,
  stakeholders,
  onClose,
  onSaved,
}: {
  projectId: string;
  stakeholders: { id: string; display_name: string; org_id?: string }[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState("");
  const [questions, setQuestions] = useState(
    "Teslimatlar beklentilerinizi ne ölçüde karşıladı?\nEkipler arası koordinasyonu nasıl değerlendiriyorsunuz?",
  );
  const [invitees, setInvitees] = useState<string[]>([]);
  const [closes, setCloses] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <Drawer
      title="Paydaş değerlendirme anketi"
      subtitle="YETKİLİ PROJE PAYDAŞLARI"
      onClose={onClose}
    >
      <form
        className="stack-form"
        onSubmit={async (e: FormEvent) => {
          e.preventDefault();
          setError("");
          const lines = questions
            .split("\n")
            .map((x) => x.trim())
            .filter(Boolean);
          if (!lines.length || lines.length > 10) {
            setError("1–10 soru girin; her soru ayrı satırda olmalıdır.");
            return;
          }
          if (!invitees.length) {
            setError("En az bir yetkili paydaş seçin.");
            return;
          }
          if (!closes || new Date(closes).getTime() <= Date.now()) {
            setError("Gelecekte bir son yanıt tarihi seçin.");
            return;
          }
          setBusy(true);
          try {
            await api(`/projects/${projectId}/surveys`, {
              method: "POST",
              body: {
                title,
                questions: lines,
                invitee_ids: invitees,
                closes_at: new Date(closes).toISOString(),
              },
            });
            onSaved();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label="Anket başlığı">
          <input
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Örn. Geçiş sonrası proje değerlendirmesi"
          />
        </Field>
        <Field label="Sorular · Her satıra bir soru">
          <textarea
            required
            rows={5}
            value={questions}
            onChange={(e) => setQuestions(e.target.value)}
          />
        </Field>
        <Field label="Son yanıt tarihi">
          <input
            type="datetime-local"
            required
            value={closes}
            onChange={(e) => setCloses(e.target.value)}
          />
        </Field>
        <div className="pi-invitee-list">
          <div>
            <strong>Hedef paydaşlar</strong>
            <Badge>{invitees.length} seçildi</Badge>
          </div>
          {stakeholders.length ? (
            stakeholders.map((person) => (
              <label className="checkbox-row" key={person.id}>
                <input
                  type="checkbox"
                  checked={invitees.includes(person.id)}
                  onChange={(e) =>
                    setInvitees((current) =>
                      e.target.checked
                        ? [...current, person.id]
                        : current.filter((id) => id !== person.id),
                    )
                  }
                />
                {person.display_name}
              </label>
            ))
          ) : (
            <p>Bu projede ankete davet edilebilecek etkin paydaş bulunmuyor.</p>
          )}
        </div>
        <div className="info-strip">
          Değerlendirme 1–5 arasındadır. Yanıtlar isimli kaydedilir; bu ekranda
          kişinin kendi yanıtı ve toplu sonuçlar gösterilir. Davetli ve yanıtsız
          sayısı ayrıca korunur.
        </div>
        {error && <ErrorState message={error} />}
        <Button disabled={busy || !stakeholders.length} type="submit">
          Anketi oluştur
          <Plus size={15} />
        </Button>
      </form>
    </Drawer>
  );
}
function SurveyCard({
  projectId,
  survey,
  canManage,
  onChanged,
}: {
  projectId: string;
  survey: Survey;
  canManage: boolean;
  onChanged: () => void;
}) {
  const [answers, setAnswers] = useState<Record<string, number>>(
    survey.my_answers || {},
  );
  const [version, setVersion] = useState(survey.version);
  const [responseVersion, setResponseVersion] = useState(
    survey.my_response_version,
  );
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const closed =
    survey.status === "CLOSED" ||
    (!!survey.closes_at && new Date(survey.closes_at).getTime() <= Date.now());
  useEffect(() => {
    if (!dirty && (survey.my_response_version || 0) >= (responseVersion || 0)) {
      setAnswers(survey.my_answers || {});
      setVersion(survey.version);
      setResponseVersion(survey.my_response_version);
    }
  }, [
    survey.version,
    survey.my_response_version,
    survey.my_answers,
    dirty,
    responseVersion,
  ]);
  const submit = async (action: string) => {
    setError("");
    setSuccess("");
    setBusy(action);
    try {
      const updated = await api<Survey>(
        `/projects/${projectId}/surveys/${survey.id}/${action}`,
        {
          method: "POST",
          body: {
            version: action === "respond" ? version : survey.version,
            ...(action === "respond"
              ? {
                  answers,
                  ...(responseVersion
                    ? { response_version: responseVersion }
                    : {}),
                }
              : {}),
          },
        },
      );
      setAnswers(updated.my_answers || {});
      setVersion(updated.version);
      setResponseVersion(updated.my_response_version);
      setDirty(false);
      onChanged();
      setSuccess(
        action === "respond"
          ? "Paydaş değerlendirmeniz kaydedildi."
          : "Anket yanıta kapatıldı.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  return (
    <div className="pi-survey">
      <div className="pi-survey-header">
        <div>
          <h4>{survey.title}</h4>
          <span>
            {survey.closes_at
              ? `Son yanıt: ${date(survey.closes_at, true)}`
              : "Son yanıt tarihi belirtilmedi"}
          </span>
        </div>
        <Badge tone={closed ? "neutral" : "success"}>
          {closed ? "Yanıta kapalı" : "Yanıta açık"}
        </Badge>
      </div>
      <div className="pi-survey-sample">
        <span>
          <strong>{survey.responded}</strong> / {survey.invited} yanıtlayan
        </span>
        <span>
          <strong>
            %
            {Number.isFinite(Number(survey.response_rate))
              ? Number(survey.response_rate).toFixed(0)
              : "—"}
          </strong>{" "}
          yanıt oranı
        </span>
        <span>Yanıtsız: {Math.max(0, survey.invited - survey.responded)}</span>
      </div>
      <p className="pi-source-caption">
        Bu anket isimlidir. Projenin anket yöneticisi yanıtınızı kimliğinizle
        birlikte görebilir. Sonuçlar yalnız yanıt veren örneklemi temsil eder.
        Yanıt vermeyen paydaşlar sıfır puan sayılmaz.
      </p>
      <div className="pi-survey-questions">
        {list(survey.questions).map((question: any) => {
          const result = survey.results?.find(
            (item) => item.question_id === question.id,
          );
          return (
            <div className="pi-survey-question" key={question.id}>
              <div>
                <strong>{question.label}</strong>
                <small>
                  {result?.count
                    ? `${result.average?.toFixed(2) ?? "—"}/5 · ${result.count} yanıt`
                    : "Bu soru için henüz yanıt yok"}
                </small>
              </div>
              {(survey.can_respond || survey.can_edit_response) && !closed && (
                <select
                  aria-label={`${question.label} değerlendirme puanı`}
                  value={answers[question.id] || ""}
                  disabled={!!busy}
                  onChange={(e) => {
                    setAnswers((current) => ({
                      ...current,
                      [question.id]: Number(e.target.value),
                    }));
                    setDirty(true);
                    setSuccess("");
                  }}
                >
                  <option value="">Puan seçin</option>
                  <option value="1">1 · Çok yetersiz</option>
                  <option value="2">2 · Geliştirilmeli</option>
                  <option value="3">3 · Beklentiyi karşılıyor</option>
                  <option value="4">4 · İyi</option>
                  <option value="5">5 · Çok iyi</option>
                </select>
              )}
              {closed && survey.my_answers?.[question.id] && (
                <Badge>Yanıtınız {survey.my_answers[question.id]}/5</Badge>
              )}
            </div>
          );
        })}
      </div>
      {error && <ErrorState message={error} />}{" "}
      {success && (
        <div className="success-state" role="status">
          <Check size={15} />
          {success}
        </div>
      )}
      <div className="pi-actions">
        {(survey.can_respond || survey.can_edit_response) && !closed && (
          <Button
            disabled={
              !!busy ||
              survey.questions.some((question) => !answers[question.id])
            }
            variant="secondary"
            onClick={() => submit("respond")}
          >
            {survey.my_answers
              ? "Yanıtları güncelle"
              : "Değerlendirmeyi gönder"}
            <Check size={15} />
          </Button>
        )}
        {canManage && !closed && (
          <Button
            disabled={!!busy}
            variant="secondary"
            onClick={() => submit("close")}
          >
            Anketi kapat
            <CheckCheck size={15} />
          </Button>
        )}
      </div>
    </div>
  );
}
function ReportCreator({
  projectId,
  initialKind,
  onClose,
  onCreated,
}: {
  projectId: string;
  initialKind: "DAILY" | "WEEKLY" | "CLOSURE";
  onClose: () => void;
  onCreated: (report: InsightReport) => void;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const [kind, setKind] = useState(initialKind);
  const [start, setStart] = useState(
    initialKind === "WEEKLY"
      ? new Date(Date.now() - 6 * 86400000).toISOString().slice(0, 10)
      : today,
  );
  const [end, setEnd] = useState(today);
  const [generationMode, setGenerationMode] = useState("AI");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Drawer
      title={
        initialKind === "CLOSURE"
          ? "Kapanış değerlendirmesi hazırla"
          : "Dönem raporu hazırla"
      }
      subtitle="KALICI RAPOR İŞİ"
      onClose={onClose}
    >
      <form
        className="stack-form"
        onSubmit={async (e: FormEvent) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            const report = await api<InsightReport>(
              `/projects/${projectId}/insight-reports`,
              {
                method: "POST",
                body: {
                  kind,
                  period_start: start,
                  period_end: end,
                  generation_mode: generationMode,
                },
              },
            );
            onCreated(report);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {initialKind !== "CLOSURE" && (
          <Field label="Rapor türü">
            <select
              value={kind}
              onChange={(e) => {
                const value = e.target.value as "DAILY" | "WEEKLY";
                setKind(value);
                if (value === "DAILY") setEnd(start);
              }}
            >
              <option value="DAILY">Günlük durum raporu</option>
              <option value="WEEKLY">Haftalık durum raporu</option>
            </select>
          </Field>
        )}
        <div className="form-grid">
          <Field label="Dönem başlangıcı">
            <input
              type="date"
              required
              value={start}
              max={end}
              onChange={(e) => {
                setStart(e.target.value);
                if (kind === "DAILY") setEnd(e.target.value);
              }}
            />
          </Field>
          <Field label="Dönem sonu">
            <input
              type="date"
              required
              value={end}
              min={start}
              disabled={kind === "DAILY"}
              onChange={(e) => setEnd(e.target.value)}
            />
          </Field>
        </div>
        <Field
          label="Hazırlama yöntemi"
          hint="Kurallı taslak model çağrısı ve token tüketimi olmadan kaynak verilerini özetler."
        >
          <select
            value={generationMode}
            onChange={(e) => setGenerationMode(e.target.value)}
          >
            <option value="AI">Yapay zekâ ile hazırla</option>
            <option value="RULE_BASED">Kurallı kaynak taslağı</option>
          </select>
        </Field>
        <div className="info-strip">
          Kaynak ölçümleri sabitlenir, taslak arka planda hazırlanır. AI
          bağlantısı sorunu iş durumunda görünür; kurallı kaynak taslağını
          ayrıca seçebilirsiniz. Yayın öncesi metin ve yönetici skorları
          incelenebilir.
        </div>
        {error && <ErrorState message={error} />}
        <Button disabled={busy} type="submit">
          {busy ? "İş kaydediliyor…" : "Taslağı hazırla"}
          <Sparkles size={15} />
        </Button>
      </form>
    </Drawer>
  );
}
function ProjectReportEditor({
  projectId,
  initial,
  permissions,
  projectCompleted,
  onClose,
  onChanged,
}: {
  projectId: string;
  initial: InsightReport;
  permissions: InsightPermissions;
  projectCompleted: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [polling, setPolling] = useState(initial.status === "GENERATING");
  const r = useResource<InsightReport>(
    `/projects/${projectId}/insight-reports/${initial.id}`,
    initial,
    polling ? 2000 : 0,
  );
  const [local, setLocal] = useState(initial);
  const record = r.data && r.data.version >= local.version ? r.data : local;
  const [editingVersion, setEditingVersion] = useState(initial.version);
  const [markdown, setMarkdown] = useState(initial.markdown || "");
  const [reviewed, setReviewed] = useState<Record<ScoreKey, string>>({
    delivery: "",
    quality: "",
    stakeholder: "",
    overall: "",
  });
  const [reason, setReason] = useState(initial.edit_reason || "");
  const [dirty, setDirty] = useState(false);
  const [view, setView] = useState("preview");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [discardRequested, setDiscardRequested] = useState(false);
  const canEdit =
    (record.permissions?.edit ??
      (record.kind === "CLOSURE"
        ? permissions.quality
        : permissions.manage || permissions.quality)) === true &&
    record.status === "READY";
  const canPublish =
    (record.permissions?.publish ??
      (record.kind === "CLOSURE"
        ? permissions.quality && projectCompleted
        : permissions.manage)) === true;
  const requestClose = () => (dirty ? setDiscardRequested(true) : onClose());
  useEffect(() => {
    setPolling(record.status === "GENERATING");
  }, [record.status]);
  useEffect(() => {
    if (!dirty) {
      setMarkdown(record.markdown || "");
      setReason(record.edit_reason || "");
      setEditingVersion(record.version);
      setReviewed(
        Object.fromEntries(
          (Object.keys(scoreLabels) as ScoreKey[]).map((key) => [
            key,
            record.reviewed_scores?.[key] === null ||
            record.reviewed_scores?.[key] === undefined
              ? ""
              : String(record.reviewed_scores[key]),
          ]),
        ) as Record<ScoreKey, string>,
      );
    }
  }, [record.version, dirty]);
  const perform = async (action: "save" | "publish") => {
    setBusy(action);
    setError("");
    setSuccess("");
    try {
      if (action === "save" && !reason.trim()) {
        setError("Yönetici incelemesi için gerekçe girin.");
        return;
      }
      const updated = await api<InsightReport>(
        `/projects/${projectId}/insight-reports/${record.id}${action === "publish" ? "/publish" : ""}`,
        {
          method: action === "publish" ? "POST" : "PATCH",
          body:
            action === "publish"
              ? { version: record.version }
              : {
                  version: editingVersion,
                  markdown,
                  ...(permissions.quality
                    ? { reviewed_scores: parseReviewedScores(reviewed) }
                    : {}),
                  edit_reason: reason,
                },
        },
      );
      setLocal(updated);
      setDirty(false);
      r.refresh();
      onChanged();
      setSuccess(
        action === "publish"
          ? "İncelenen rapor sürümü yayınlandı."
          : "Yönetici incelemesi ayrı sürüm olarak kaydedildi.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  const exportReport = async (html: boolean) => {
    setBusy("export");
    setError("");
    try {
      const exported = await api<string>(
        `/projects/${projectId}/insight-reports/${record.id}/markdown`,
      );
      Download({
        text: html
          ? printableProjectReport(
              reportNames[record.kind] || "Proje raporu",
              exported,
            )
          : exported,
        name: `onecs-${record.kind.toLowerCase()}-${record.period_end}.${html ? "html" : "md"}`,
        type: html ? "text/html;charset=utf-8" : "text/markdown;charset=utf-8",
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  if (r.error && !r.data)
    return (
      <Drawer title="Rapor erişilemiyor" onClose={onClose}>
        <ErrorState message={r.error} onRetry={r.refresh} />
      </Drawer>
    );
  const baseline = (record.computed_values?.scores ||
    record.computed_values ||
    {}) as Record<string, unknown>;
  const ready = ["READY", "PUBLISHED"].includes(record.status);
  return (
    <Drawer
      title={reportNames[record.kind] || "Proje raporu"}
      subtitle={`${date(record.period_start)} — ${date(record.period_end)} · KAYIT SÜRÜMÜ ${record.version}`}
      onClose={requestClose}
      wide
    >
      <div className="pi-report-status">
        <Badge
          tone={
            record.status === "PUBLISHED"
              ? "success"
              : record.status === "FAILED"
                ? "danger"
                : "neutral"
          }
        >
          {statusNames[record.status] || "Taslak"}
        </Badge>
        <Badge tone={record.mode === "AI" ? "brand" : "neutral"}>
          {modeLabel(record.mode)}
        </Badge>
        {dirty && <Badge tone="warning">Kaydedilmemiş değişiklik</Badge>}
      </div>
      {discardRequested && (
        <div className="pi-discard" role="alert">
          <div>
            <strong>Kaydedilmemiş incelemeniz var.</strong>
            <p>Pencereyi kapatmak bu değişiklikleri siler.</p>
          </div>
          <div className="pi-actions">
            <Button
              variant="secondary"
              onClick={() => setDiscardRequested(false)}
            >
              Düzenlemeye dön
            </Button>
            <Button variant="danger" onClick={onClose}>
              Değişiklikleri sil ve kapat
            </Button>
          </div>
        </div>
      )}
      {record.status === "GENERATING" && (
        <div className="pi-generation">
          <Loader2 className="spin" size={25} />
          <div>
            <strong>Kaynaklara dayalı taslak hazırlanıyor</strong>
            <p>
              İş durumu: {statusNames[record.job?.status || ""] || "Sırada"}.
              Pencereyi kapatsanız da kayıtlı iş devam eder.
            </p>
          </div>
        </div>
      )}
      {record.status === "FAILED" && (
        <ErrorState
          message={
            record.job?.last_error ||
            "Rapor hazırlanamadı. Kaynak durumunu ve bağlantı ayarlarını kontrol ederek yeni bir taslak oluşturun."
          }
        />
      )}{" "}
      {record.mode === "RULE_BASED" && ready && (
        <div className="info-strip">
          <FileText size={16} />
          Bu taslak AI çıktısı değildir. Kaynak verilerinden kurallı olarak
          hazırlanmıştır; eksik bilgiler ve skorlar uydurulmaz.
          {fallbackExplanation(record.job?.fallback_reason) && (
            <span>{fallbackExplanation(record.job?.fallback_reason)}</span>
          )}
        </div>
      )}
      {r.error && <ErrorState message={r.error} onRetry={r.refresh} />}{" "}
      {error && <ErrorState message={error} />}{" "}
      {success && (
        <div className="success-state" role="status">
          <Check size={15} />
          {success}
        </div>
      )}
      {ready && (
        <>
          <div className="pi-subhead">
            <div>
              <h4>Hesaplanan kaynak değerleri</h4>
              <p>
                Bu ölçümler sabittir; yönetici incelemesi bu değerlerin üzerine
                yazmaz.
              </p>
            </div>
            <Badge>{list(record.sources).length} kaynak</Badge>
          </div>
          <div className="pi-score-grid compact">
            {(Object.keys(scoreLabels) as ScoreKey[]).map((key) => (
              <Metric
                key={key}
                label={scoreLabels[key]}
                value={baseline[key]}
                description="Kaynak ölçümü"
                primary={key === "overall"}
              />
            ))}
          </div>
          <div className="pi-report-toolbar">
            <div className="segmented">
              <button
                className={view === "preview" ? "active" : ""}
                onClick={() => setView("preview")}
              >
                Önizleme
              </button>
              {canEdit && (
                <button
                  className={view === "edit" ? "active" : ""}
                  onClick={() => setView("edit")}
                >
                  <FilePenLine size={14} />
                  İncele / düzenle
                </button>
              )}
            </div>
            <div className="pi-actions">
              <Button
                variant="secondary"
                disabled={dirty || !!busy}
                onClick={() => exportReport(false)}
              >
                <ArrowDownToLine size={14} />
                Markdown
              </Button>
              <Button
                variant="secondary"
                disabled={dirty || !!busy}
                onClick={() => exportReport(true)}
              >
                Yazdırılabilir HTML
              </Button>
            </div>
          </div>
          {view === "edit" && canEdit ? (
            <div className="pi-report-editor">
              <div className="pi-subhead">
                <div>
                  <h4>Yönetici incelemesi</h4>
                  <p>
                    Boş skor, yönetici puanı verilmediği anlamına gelir. Kaynak
                    verisi ayrı kalır.
                  </p>
                </div>
              </div>
              {permissions.quality ? (
                <div className="pi-review-scores">
                  {(Object.keys(scoreLabels) as ScoreKey[]).map((key) => (
                    <Field
                      key={key}
                      label={scoreLabels[key]}
                      hint={`Hesaplanan: ${scoreText(baseline[key])}`}
                    >
                      <input
                        type="number"
                        min={0}
                        max={100}
                        step="0.1"
                        value={reviewed[key]}
                        disabled={!!busy}
                        placeholder="İnceleme puanı yok"
                        onChange={(e) => {
                          setReviewed((current) => ({
                            ...current,
                            [key]: e.target.value,
                          }));
                          setDirty(true);
                          setSuccess("");
                        }}
                      />
                    </Field>
                  ))}
                </div>
              ) : (
                <ReviewedScoreSummary reviewed={record.reviewed_scores} />
              )}
              <Field label="Rapor metni · Markdown">
                <textarea
                  className="pi-markdown-editor"
                  rows={15}
                  maxLength={50000}
                  value={markdown}
                  disabled={!!busy}
                  onChange={(e) => {
                    setMarkdown(e.target.value);
                    setDirty(true);
                    setSuccess("");
                  }}
                />
              </Field>
              <Field label="İnceleme / değişiklik gerekçesi">
                <textarea
                  rows={3}
                  required
                  value={reason}
                  disabled={!!busy}
                  onChange={(e) => {
                    setReason(e.target.value);
                    setDirty(true);
                    setSuccess("");
                  }}
                  placeholder="Hangi kaynakları kontrol ettiniz? Sayı veya metin değişikliğinin gerekçesi nedir?"
                />
              </Field>
              <div className="pi-actions">
                <Button
                  disabled={!!busy || !dirty || !reason.trim()}
                  onClick={() => perform("save")}
                >
                  {busy === "save" ? "Kaydediliyor…" : "İncelemeyi kaydet"}
                  <Check size={15} />
                </Button>
                <span className="pi-source-caption">
                  Düzenleme sırasında gelen güncellemeler taslağınızı ezmez.
                </span>
              </div>
            </div>
          ) : (
            <>
              <ReviewedScoreSummary reviewed={record.reviewed_scores} />
              {dirty && (
                <p className="pi-source-caption">
                  Önizlemede kaydedilmemiş metin değişiklikleri gösteriliyor;
                  indirmek ve yayınlamak için kaydedin.
                </p>
              )}
              <MarkdownPreview
                text={markdown || "Bu raporda henüz metin bulunmuyor."}
              />
            </>
          )}
          <details className="pi-original">
            <summary>
              <Sparkles size={15} />
              Özgün {record.mode === "AI" ? "AI" : "kaynak"} taslağını gör
            </summary>
            <MarkdownPreview
              text={
                record.original_markdown || "Özgün taslak henüz kaydedilmedi."
              }
            />
          </details>
          {record.kind === "CLOSURE" &&
            !projectCompleted &&
            record.status === "READY" && (
              <div className="info-strip">
                Kapanış taslağını inceleyebilirsiniz. Başarı endeksini
                yayınlamak için projenin doğrulanmış kapanışı tamamlanmalıdır.
              </div>
            )}
          {canPublish && record.status === "READY" && (
            <div className="pi-publish">
              <div>
                <strong>İncelenen sürümü yayınla</strong>
                <p>
                  Yayınlanan metin ve yönetici puanları bu sürümle birlikte
                  korunur. Proje kapanışı ayrı karardır.
                </p>
              </div>
              <Button
                disabled={!!busy || dirty}
                onClick={() => perform("publish")}
              >
                <CheckCheck size={16} />
                İncelemeyi yayınla
              </Button>
            </div>
          )}
          {record.status === "PUBLISHED" && (
            <div className="pi-published">
              <ShieldCheck size={17} />
              <span>
                Yayınlanan sürüm korunur. Yeni bir değerlendirme için yeni dönem
                taslağı hazırlayın.
                {record.published_at
                  ? ` Yayın tarihi: ${date(record.published_at, true)}`
                  : ""}
              </span>
            </div>
          )}
        </>
      )}
    </Drawer>
  );
}
function ReviewedScoreSummary({ reviewed }: { reviewed?: Partial<Scores> }) {
  const entries = (Object.keys(scoreLabels) as ScoreKey[]).filter(
    (key) => insightScore(reviewed?.[key]) !== null,
  );
  return entries.length ? (
    <div className="pi-reviewed-summary">
      <strong>Yönetici inceleme puanları</strong>
      <div>
        {entries.map((key) => (
          <span key={key}>
            {scoreLabels[key]} <b>{scoreText(reviewed?.[key])}/100</b>
          </span>
        ))}
      </div>
    </div>
  ) : (
    <div className="pi-source-caption">
      Bu sürüm için ayrıca yönetici inceleme puanı verilmedi. Yukarıdaki
      değerler kaynak ölçümleridir.
    </div>
  );
}
