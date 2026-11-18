import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  CalendarDays,
  CheckCheck,
  Clock3,
  FileText,
  Layers3,
  ShieldAlert,
  Users,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api, date, list, useResource } from "../lib/api";
import { useAuth } from "../lib/auth";
import { organizationLabel } from "../lib/organization";
import DashboardCharts, { dashboardCount } from "../components/DashboardCharts";
import DashboardAnnouncements from "../components/DashboardAnnouncements";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  SectionTitle,
  Status,
} from "../components/ui";
const kpiConfig = [
  {
    key: "critical",
    label: "Kritik gündem",
    icon: ShieldAlert,
    tone: "danger",
    description: "Öncelikli müdahale ve takip",
    to: "/cases",
  },
  {
    key: "overdue",
    label: "Geciken taahhüt ve SLA",
    icon: Clock3,
    tone: "warning",
    description: "Yönetici takibi gerekiyor",
    to: "/work?filter=overdue",
  },
  {
    key: "decisions",
    label: "Kararım bekleniyor",
    icon: CheckCheck,
    tone: "brand",
    description: "Onay ve doğrulama bekleyen",
    to: "/projects?filter=pending",
  },
  {
    key: "credentials",
    label: "Yaklaşan sertifikalar",
    icon: CalendarDays,
    tone: "success",
    description: "Önemli yenileme tarihleri",
    to: "/credentials",
  },
];
export default function Dashboard() {
  const { user } = useAuth();
  const r = useResource<any>("/dashboard");
  if (r.loading && !r.data) return <Loading />;
  if (r.error && !r.data)
    return <ErrorState message={r.error} onRetry={r.refresh} />;
  const d = r.data || {};
  const agenda = list(d.agenda);
  const updateTime = d.updated_at ? new Date(d.updated_at) : null;
  const updatedLabel =
    updateTime && !Number.isNaN(updateTime.getTime())
      ? new Intl.DateTimeFormat("tr-TR", {
          hour: "2-digit",
          minute: "2-digit",
        }).format(updateTime)
      : "Bilgi alınamadı";
  return (
    <div className="onecs-dashboard">
      <PageHeader
        eyebrow="DİREKTÖRLÜK OPERASYON MERKEZİ"
        title="Genel Bakış"
        description={`Merhaba ${user.display_name?.split(" ")[0] || user.username}, çalışma alanınızdaki öncelikler ve ekiplerin güncel durumu.`}
        actions={
          <>
            <span className={`live-label ${r.error ? "is-stale" : ""}`}>
              <span />
              {r.error ? "Son kayıtlı görünüm" : "Canlı görünüm"}
            </span>
            <Link className="btn btn-secondary" to="/reports">
              <FileText size={16} />
              Haftalık rapor
              <ArrowUpRight size={14} />
            </Link>
          </>
        }
      />
      {r.error && <ErrorState message={r.error} onRetry={r.refresh} />}
      <div className="kpi-grid">
        {kpiConfig.map((k) => {
          const raw = d.kpis?.[k.key];
          const value = dashboardCount(
            typeof raw === "object" ? raw?.count : raw,
          );
          const displayValue =
            value === null ? "—" : value.toLocaleString("tr-TR");
          return (
            <Link
              className={`kpi-card kpi-${k.tone}`}
              key={k.key}
              to={k.to}
              aria-label={`${k.label}: ${value === null ? "veri alınamadı" : displayValue}. ${k.description}`}
            >
              <div className="kpi-label">
                {k.label}
                <span className="kpi-icon">
                  <k.icon size={17} />
                </span>
              </div>
              <strong>{displayValue}</strong>
              <div className="kpi-bottom">
                <span>{k.description}</span>
                <ArrowUpRight size={15} />
              </div>
            </Link>
          );
        })}
      </div>
      <div className="dashboard-grid">
        <Card className="agenda-card">
          <SectionTitle
            title="Öncelikli gündem"
            description="Bugün dikkatinizi gerektiren en önemli 5 konu"
            actions={<Badge>{Math.min(agenda.length, 5)} konu</Badge>}
          />
          {agenda.length ? (
            <div className="agenda-list">
              {agenda.slice(0, 5).map((a: any, index: number) => (
                <Link
                  key={a.id}
                  className="agenda-row"
                  to={`/${a.resource_type === "project" ? "projects" : a.resource_type === "case" ? "cases" : "work"}?id=${a.id}`}
                >
                  <span
                    className={`priority-line ${String(a.priority).toLowerCase()}`}
                  />
                  <div className="agenda-index">
                    {String(index + 1).padStart(2, "0")}
                  </div>
                  <div className="agenda-main">
                    <div className="inline-badges">
                      <Status value={a.priority} />
                      <span className="record-kind">
                        {a.resource_type === "project"
                          ? "PROJE"
                          : a.resource_type === "case"
                            ? "VAKA"
                            : "İŞ"}
                      </span>
                    </div>
                    <strong>{a.title}</strong>
                    <p>
                      {a.reason ||
                        a.next_step ||
                        "Güncel durumu ve sonraki adımı inceleyin."}
                    </p>
                    <div className="row-meta">
                      <span>
                        <Users size={12} />
                        {a.owner_name || "Sorumlu bekleniyor"}
                      </span>
                      {a.due_at && (
                        <span>
                          <Clock3 size={12} />
                          {date(a.due_at, true)}
                        </span>
                      )}
                    </div>
                  </div>
                  <ArrowRight className="agenda-arrow" size={17} />
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState
              title="Gündeminiz güncel"
              description="Şu anda öncelikli aksiyon gerektiren bir kayıt bulunmuyor."
              icon={<CheckCheck size={30} />}
            />
          )}
          <Link className="card-footer-link" to="/work">
            Tüm işler ve taahhütler
            <ArrowRight size={15} />
          </Link>
        </Card>
        <DashboardAnnouncements
          published={d.announcements}
          pending={d.pending_announcements}
          counts={d.announcement_counts}
        />
      </div>
      <DashboardCharts
        units={list(d.unit_summaries)}
        agenda={agenda.slice(0, 5)}
        kpis={d.kpis || {}}
        updatedAt={d.updated_at}
      />
      <Card className="unit-overview">
        <SectionTitle
          title="Ekiplerin nabzı"
          description="Organizasyonunuzdaki operasyonel durumun kısa özeti"
          actions={
            <Link className="text-button" to="/organization">
              Organizasyonu aç
              <ArrowRight size={14} />
            </Link>
          }
        />
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>BİRİM / EKİP</th>
                <th>SORUMLU</th>
                <th>AÇIK İŞ</th>
                <th>AÇIK VAKA</th>
                <th>SLA İHLALİ</th>
                <th>PROJE KATKISI</th>
              </tr>
            </thead>
            <tbody>
              {list(d.unit_summaries).map((u: any) => (
                <tr key={u.id || u.code}>
                  <td>
                    <Link to={`/organization?id=${u.id}`}>
                      <strong>{organizationLabel(u.name)}</strong>
                      <small>{u.code}</small>
                    </Link>
                  </td>
                  <td>{u.manager_name || u.head_name || "—"}</td>
                  <td>{u.open_work ?? u.work_count ?? 0}</td>
                  <td>{u.open_cases ?? u.case_count ?? 0}</td>
                  <td>
                    <Badge
                      tone={
                        (u.sla_breaches ?? u.overdue ?? 0) > 0
                          ? "danger"
                          : "success"
                      }
                    >
                      {u.sla_breaches ?? u.overdue ?? 0}
                    </Badge>
                  </td>
                  <td>{u.project_contributions ?? u.project_count ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!list(d.unit_summaries).length && (
            <div className="compact-empty">
              Organizasyon özeti henüz oluşmadı.
            </div>
          )}
        </div>
      </Card>
      <div className="section-heading-row">
        <div>
          <div className="eyebrow">BİRLİKTE DAHA GÜÇLÜ</div>
          <h2>CS’de Neler Oluyor?</h2>
          <p className="muted">
            Ekipleri tanıyın, çalışmalardan haberdar olun, deneyim paylaşın.
          </p>
        </div>
        <Link className="text-button" to="/community">
          Tüm paylaşımlar
          <ArrowRight size={15} />
        </Link>
      </div>
      <div className="community-preview-grid">
        {list(d.community).length ? (
          list(d.community)
            .slice(0, 3)
            .map((c: any) => (
              <Link
                className="card community-preview"
                key={c.id}
                to={`/community?id=${c.id}`}
              >
                <span className="eyebrow">
                  {c.owner_org_name ||
                    c.org_name ||
                    (
                      {
                        HELP: "Destek çağrısı",
                        LESSON: "Öğrenilenler",
                        SUCCESS: "Ekip başarısı",
                        KNOWLEDGE: "Bilgi paylaşımı",
                      } as Record<string, string>
                    )[c.kind] ||
                    "EKİP PAYLAŞIMI"}
                </span>
                <h3>{c.title}</h3>
                <p>{c.summary || c.body || c.description}</p>
                <div>
                  <span>
                    {c.author_name || c.author?.display_name || "CS Ekibi"}
                  </span>
                  <ArrowUpRight size={16} />
                </div>
              </Link>
            ))
        ) : (
          <Card>
            <EmptyState
              title="Ekip paylaşımları burada buluşacak"
              description="Onaylanmış çalışmalar ve yardım çağrıları bütün ekipleri bir araya getirir."
              icon={<Users size={26} />}
            />
          </Card>
        )}
      </div>
      <div className="update-footer">
        <span>
          <span className="tiny-dot" />
          Son güncelleme: {updatedLabel}
        </span>
        <span>20 saniyede bir yenilenir</span>
      </div>
    </div>
  );
}
