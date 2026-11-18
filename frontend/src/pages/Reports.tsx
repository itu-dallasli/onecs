import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  ArrowDownToLine,
  ArrowRight,
  Check,
  CircleCheck,
  FileText,
  Link2,
  Plus,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Star,
} from "lucide-react";
import { api, date, list, useResource } from "../lib/api";
import { useAuth } from "../lib/auth";
import {
  Badge,
  Button,
  Card,
  Drawer,
  EmptyState,
  ErrorState,
  Field,
  Loading,
  PageHeader,
  SectionTitle,
  Status,
} from "../components/ui";
export default function Reports() {
  const { user } = useAuth();
  const r = useResource<any>("/reports");
  const [selected, setSelected] = useState<any>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedId = searchParams.get("id")?.toLowerCase() || null;
  const validId =
    !!requestedId &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      requestedId,
    );
  const closeSelected = () => {
    setSelected(null);
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.delete("id");
      return next;
    });
  };
  const openSelected = (record: any) => {
    setSelected(record);
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("id", record.id);
      return next;
    });
  };
  const [create, setCreate] = useState(false);
  const [title, setTitle] = useState("Haftalık Yönetim Özeti");
  const [start, setStart] = useState(
    new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10),
  );
  const [end, setEnd] = useState(new Date().toISOString().slice(0, 10));
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const detail = useResource<any>(
    validId ? `/reports/${requestedId}` : null,
    undefined,
    3000,
  );
  useEffect(() => {
    if (!validId || (detail.error && !detail.data)) {
      setSelected(null);
      return;
    }
    if (detail.data?.id === requestedId) setSelected(detail.data);
    else
      setSelected((current: any) =>
        current?.id === requestedId ? current : null,
      );
  }, [requestedId, validId, detail.data, detail.error]);
  const report =
    detail.error && !detail.data
      ? null
      : detail.data?.id === selected?.id
        ? detail.data
        : selected;
  const canManage = report?.permissions?.manage === true;
  async function action(name: string) {
    setBusy(name);
    setError("");
    try {
      const next = await api<any>(`/reports/${report.id}/${name}`, {
        method: "POST",
        body: {
          version: report.version,
          ...(name === "approve" ? { content_hash: report.content_hash } : {}),
        },
      });
      setSelected(next?.id ? next : report);
      detail.refresh();
      r.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  function download() {
    const content = report.markdown || report.content || report.summary || "";
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `atlas-rapor-${report.id.slice(0, 8)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <>
      <PageHeader
        eyebrow="KAYNAĞINDAN YÖNETİM ÖZETİNE"
        title="Raporlar"
        description="Yıldızlanan işleri ve önemli değişiklikleri kısa, kaynaklı bir yönetim raporuna dönüştürün."
        actions={
          (user.permissions?.manage_unit ||
            user.permissions?.manage_projects) && (
            <Button onClick={() => setCreate(true)}>
              <Plus size={16} />
              Haftalık rapor oluştur
            </Button>
          )
        }
      />
      <div className="report-workflow">
        <div>
          <span>01</span>
          <Star size={18} />
          <strong>Konuları seçin</strong>
          <p>İşleri tek tıkla rapor havuzuna ekleyin.</p>
        </div>
        <ArrowRight size={20} />
        <div>
          <span>02</span>
          <Sparkles size={18} />
          <strong>AI ile özetleyin</strong>
          <p>İlerleme ve sonraki adımları birleştirin.</p>
        </div>
        <ArrowRight size={20} />
        <div>
          <span>03</span>
          <ShieldCheck size={18} />
          <strong>Kontrol edip paylaşın</strong>
          <p>Kaynakları inceleyin, onaylayın ve indirin.</p>
        </div>
      </div>
      {requestedId && !validId && (
        <div>
          <ErrorState message="Rapor bağlantısı geçersiz. Listeden bir rapor seçin." />
          <Button variant="secondary" onClick={closeSelected}>
            Listeye dön
          </Button>
        </div>
      )}
      {validId && detail.loading && !selected && (
        <Loading label="Rapor ayrıntısı yükleniyor…" />
      )}
      {detail.error && (
        <ErrorState message={detail.error} onRetry={detail.refresh} />
      )}
      {error && <ErrorState message={error} />}
      <Card>
        <SectionTitle
          title="Yönetim raporları"
          description="Her rapor dönemi ve kaynak sürümleriyle kayıtlıdır"
        />
        {r.error && <ErrorState message={r.error} onRetry={r.refresh} />}{" "}
        {r.loading && !r.data ? (
          <Loading />
        ) : list(r.data).length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>RAPOR</th>
                  <th>DÖNEM</th>
                  <th>DURUM</th>
                  <th>KAYNAK</th>
                  <th>OLUŞTURULMA</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list(r.data).map((x: any) => (
                  <tr key={x.id}>
                    <td>
                      <button
                        className="record-title"
                        onClick={() => openSelected(x)}
                      >
                        <strong>{x.title}</strong>
                        <small>
                          {x.scope_label ||
                            x.org_name ||
                            "Yetkili yönetim kapsamı"}
                        </small>
                      </button>
                    </td>
                    <td>
                      {date(x.period_start)} — {date(x.period_end)}
                    </td>
                    <td>
                      <Status value={x.status} />
                    </td>
                    <td>{x.source_count ?? x.sources?.length ?? "—"}</td>
                    <td>{date(x.created_at)}</td>
                    <td>
                      <Button
                        variant="secondary"
                        onClick={() => openSelected(x)}
                      >
                        Raporu aç
                        <ArrowRight size={14} />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="İlk raporunuzu oluşturun"
            description="Güncel kayıtlardan seçilen konularla haftalık yönetim özeti hazırlayın."
            icon={<FileText size={30} />}
          />
        )}
      </Card>
      <div className="context-note">
        <Link2 size={15} />
        Her AI özeti yetkiniz kapsamındaki kaynaklara dayanır. Yetersiz bilgi ve
        bağlantı sorunu açıkça gösterilir.
      </div>
      {create && (
        <Drawer
          title="Haftalık rapor oluştur"
          subtitle="RAPOR DÖNEMİ"
          onClose={() => setCreate(false)}
        >
          <form
            className="stack-form"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy("create");
              setError("");
              try {
                const data = await api<any>("/reports", {
                  method: "POST",
                  body: { title, period_start: start, period_end: end },
                });
                setCreate(false);
                r.refresh();
                openSelected(data);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy("");
              }
            }}
          >
            <Field label="Rapor başlığı">
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
              />
            </Field>
            <div className="form-grid">
              <Field label="Başlangıç">
                <input
                  type="date"
                  value={start}
                  onChange={(e) => setStart(e.target.value)}
                  required
                />
              </Field>
              <Field label="Bitiş">
                <input
                  type="date"
                  value={end}
                  min={start}
                  onChange={(e) => setEnd(e.target.value)}
                  required
                />
              </Field>
            </div>
            <div className="info-strip">
              <Star size={16} />
              Yıldızlanan konular ile kritik, geciken ve karar bekleyen kayıtlar
              rapor adaylarını oluşturur.
            </div>
            {error && <ErrorState message={error} />}
            <Button disabled={!!busy}>
              Rapor çalışma alanını aç
              <ArrowRight size={15} />
            </Button>
          </form>
        </Drawer>
      )}
      {report && (
        <Drawer
          title={report.title}
          subtitle={`${date(report.period_start)} — ${date(report.period_end)}`}
          onClose={closeSelected}
          wide
        >
          <div className="detail-status-row">
            <Status value={report.status} />
            <Badge>
              {report.source_count ?? report.sources?.length ?? 0} kaynak
            </Badge>
            {report.generated_mode === "AI" && (
              <Badge tone="brand">
                <Sparkles size={11} />
                AI destekli
              </Badge>
            )}
          </div>
          {report.generated_mode && report.generated_mode !== "AI" && (
            <div className="info-strip">
              Bu çıktı kaynak kayıtlarının yapılandırılmış özetidir. Yapay zeka
              sağlayıcısı kullanılmadı.
            </div>
          )}
          {!canManage && (
            <p className="info-strip">
              Bu onaylı rapor üst yönetim görünümünde salt okunurdur.
            </p>
          )}
          <div className="detail-action-bar">
            {canManage && (
              <Button
                disabled={
                  !!busy || ["GENERATING", "APPROVED"].includes(report.status)
                }
                onClick={() => action("generate")}
              >
                <Sparkles size={15} />
                {busy === "generate"
                  ? "Özet hazırlanıyor…"
                  : "AI özeti hazırla"}
              </Button>
            )}
            <Button
              variant="secondary"
              disabled={
                !!busy || !(report.markdown || report.content || report.summary)
              }
              onClick={download}
            >
              <ArrowDownToLine size={15} />
              Markdown
            </Button>
            <Button
              variant="secondary"
              disabled={
                !!busy || !(report.markdown || report.content || report.summary)
              }
              onClick={() => window.print()}
            >
              PDF / Yazdır
            </Button>
            {canManage && report.status !== "APPROVED" && (
              <Button
                variant="secondary"
                disabled={
                  !!busy ||
                  !(report.markdown || report.content || report.summary)
                }
                onClick={() => action("approve")}
              >
                <Check size={15} />
                Onayla
              </Button>
            )}
          </div>
          {error && <ErrorState message={error} />}{" "}
          {detail.loading && !detail.data ? (
            <Loading />
          ) : report.markdown || report.content || report.summary ? (
            <article className="report-content">
              {String(report.markdown || report.content || report.summary)
                .split("\n")
                .map((line: string, index: number) =>
                  line.startsWith("# ") ? (
                    <h2 key={index}>{line.slice(2)}</h2>
                  ) : line.startsWith("## ") ? (
                    <h3 key={index}>{line.slice(3)}</h3>
                  ) : line.startsWith("- ") ? (
                    <p className="report-bullet" key={index}>
                      {line.slice(2)}
                    </p>
                  ) : (
                    <p key={index}>{line || " "}</p>
                  ),
                )}
            </article>
          ) : (
            <EmptyState
              title="Rapor özeti henüz hazırlanmadı"
              description="Kaynakları gözden geçirin ve AI özeti hazırlayın. Model yapılandırılmamışsa kaynak özeti kullanılabilir."
              icon={<FileText size={30} />}
            />
          )}
          <div className="detail-block">
            <h3>Kaynak kayıtlar</h3>
            {list(report.sources || report.items).map(
              (s: any, index: number) => (
                <div className="report-source" key={s.id || index}>
                  <span>[{index + 1}]</span>
                  <div>
                    <strong>{s.title || s.source_title || s.id}</strong>
                    <small>
                      {(
                        {
                          project: "Proje",
                          work: "İş ve taahhüt",
                          case: "Vaka",
                        } as Record<string, string>
                      )[s.resource_type || s.source_type || s.type] ||
                        "Kaynak kayıt"}{" "}
                      · sürüm
                      {s.version || s.source_version || 1}
                    </small>
                  </div>
                  <Link2 size={15} />
                </div>
              ),
            )}
            {!list(report.sources || report.items).length && (
              <p className="muted">
                Kaynak listesi rapor hazırlandığında gösterilir.
              </p>
            )}
          </div>
        </Drawer>
      )}
    </>
  );
}
