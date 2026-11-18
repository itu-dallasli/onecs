import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import {
  CalendarClock,
  Check,
  Megaphone,
  Pin,
  Plus,
  Search,
  Send,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import { api, date, list, useResource } from "../lib/api";
import { useAuth } from "../lib/auth";
import RecordExtras, {
  emptyRecordExtras,
  RecordAttachments,
} from "../components/RecordExtras";
import { createRecordWithExtras } from "../lib/recordExtras";
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
} from "../components/ui";
import "../styles/settings.css";
type Announcement = {
  id: string;
  title: string;
  body: string;
  owner_org_id: string;
  all_cs: boolean;
  status: string;
  starts_at: string;
  ends_at: string | null;
  pinned: boolean;
  author_name: string;
  version: number;
  created_at: string;
  permissions?: { publish: boolean; withdraw: boolean };
};
type Org = {
  id: string;
  name: string;
  code: string;
  parent_id: string | null;
  kind: string;
};
const labels: Record<string, string> = {
  DRAFT: "Yayın kararı bekliyor",
  PUBLISHED: "Yayında",
  WITHDRAWN: "Geri çekildi",
};
const initial = {
  title: "",
  body: "",
  all_cs: false,
  audience_org_ids: [] as string[],
  starts_at: "",
  ends_at: "",
  pinned: false,
};
export default function Announcements() {
  const { user } = useAuth();
  const { data, loading, error, refresh } = useResource<any>("/announcements");
  const { data: orgData } = useResource<any>("/organization");
  const orgs = list<Org>(orgData),
    records = list<Announcement>(data);
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedStatus = searchParams.get("status") || "all";
  const [query, setQuery] = useState(""),
    [status, setStatus] = useState(() =>
      ["DRAFT", "PUBLISHED", "WITHDRAWN"].includes(requestedStatus)
        ? requestedStatus
        : "all",
    ),
    [creating, setCreating] = useState(false),
    [selected, setSelected] = useState<Announcement | null>(null),
    [busy, setBusy] = useState(""),
    [failure, setFailure] = useState(""),
    [success, setSuccess] = useState(""),
    [form, setForm] = useState(initial);
  const [extras, setExtras] = useState(emptyRecordExtras);
  useEffect(() => {
    setStatus(
      ["DRAFT", "PUBLISHED", "WITHDRAWN"].includes(requestedStatus)
        ? requestedStatus
        : "all",
    );
  }, [requestedStatus]);
  const requestedId = searchParams.get("id")?.toLowerCase() || null;
  const validId =
    !!requestedId &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      requestedId,
    );
  const linkedRecord = useResource<Announcement>(
    validId ? `/announcements/${requestedId}` : null,
  );
  const closeSelected = () => {
    setSelected(null);
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.delete("id");
      return next;
    });
  };
  const openSelected = (record: Announcement) => {
    setSelected(record);
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("id", record.id);
      return next;
    });
  };
  useEffect(() => {
    if (!validId || (linkedRecord.error && !linkedRecord.data)) {
      setSelected(null);
      return;
    }
    if (linkedRecord.data?.id === requestedId) setSelected(linkedRecord.data);
    else
      setSelected((current) => (current?.id === requestedId ? current : null));
  }, [requestedId, validId, linkedRecord.data, linkedRecord.error]);
  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) =>
    setForm((old) => ({ ...old, [key]: value }));
  const scope = (orgId: string, roles: string[]) => {
    const ids = new Set<string>();
    let current: string | null = orgId;
    while (current && !ids.has(current)) {
      ids.add(current);
      current = orgs.find((org) => org.id === current)?.parent_id || null;
    }
    return (
      user.roles?.some(
        (role) =>
          roles.includes(role.role.toUpperCase()) &&
          (!role.org_id || ids.has(role.org_id)),
      ) || false
    );
  };
  const visible = records
    .filter(
      (item) =>
        (status === "all" || item.status === status) &&
        `${item.title} ${item.body} ${item.author_name}`
          .toLocaleLowerCase("tr-TR")
          .includes(query.toLocaleLowerCase("tr-TR")),
    )
    .sort(
      (a, b) =>
        Number(b.pinned) - Number(a.pinned) ||
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    );
  const create = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy("create");
    setFailure("");
    try {
      await createRecordWithExtras(
        "/announcements",
        {
          ...form,
          starts_at: form.starts_at
            ? new Date(form.starts_at).toISOString()
            : undefined,
          ends_at: form.ends_at
            ? new Date(form.ends_at).toISOString()
            : undefined,
        },
        extras,
      );
      setCreating(false);
      setForm(initial);
      setExtras(emptyRecordExtras());
      setSuccess(
        "Anons taslağı kaydedildi. Yayın kararını yetkili Birim yöneticisi veya direktör verir.",
      );
      refresh();
    } catch (error) {
      setFailure(
        error instanceof Error ? error.message : "Anons kaydedilemedi.",
      );
    } finally {
      setBusy("");
    }
  };
  const action = async (item: Announcement, name: "publish" | "withdraw") => {
    setBusy(item.id);
    setFailure("");
    try {
      await api(`/announcements/${item.id}/${name}`, {
        method: "POST",
        body: { version: item.version },
      });
      closeSelected();
      setSuccess(
        name === "publish"
          ? "Anons seçilen hedef kitle için yayınlandı."
          : "Anons yayından geri çekildi.",
      );
      refresh();
    } catch (error) {
      setFailure(
        error instanceof Error ? error.message : "İşlem tamamlanamadı.",
      );
    } finally {
      setBusy("");
    }
  };
  return (
    <div className="announcements-page">
      <PageHeader
        eyebrow="EKİPLER ARASI İLETİŞİM"
        title="Anonslar"
        description="Ortak gündemi seçilen ekiplerle paylaşın. Yayın kararını ve hedef kitleyi izleyin."
        actions={
          <Button
            onClick={() => {
              setFailure("");
              setCreating(true);
            }}
          >
            <Plus size={16} />
            Anons öner
          </Button>
        }
      />
      {requestedId &&
        (!validId || (linkedRecord.error && !linkedRecord.data)) && (
          <div>
            <ErrorState
              message={
                !validId
                  ? "Anons bağlantısı geçersiz. Listeden bir anons seçin."
                  : linkedRecord.error
              }
              onRetry={validId ? linkedRecord.refresh : undefined}
            />
            <Button variant="secondary" onClick={closeSelected}>
              Listeye dön
            </Button>
          </div>
        )}
      {validId && linkedRecord.loading && !selected && (
        <Loading label="Anons ayrıntısı yükleniyor…" />
      )}
      {error && <ErrorState message={error} onRetry={refresh} />}{" "}
      {failure && !creating && <ErrorState message={failure} />}{" "}
      {success && (
        <div className="announcements-success" role="status">
          <Check size={16} />
          {success}
          <button onClick={() => setSuccess("")} aria-label="Bilgiyi kapat">
            <X size={15} />
          </button>
        </div>
      )}
      <div className="announcements-summary">
        <span className="onecs-settings-title-icon">
          <Megaphone size={23} />
        </span>
        <div>
          <strong>Doğru bilgi, doğru ekipler</strong>
          <p>
            Çalışanlar taslak hazırlayabilir. Birim yöneticisi ve direktör,
            kendi kapsamlarındaki anonsları yayınlar.
          </p>
        </div>
        <ShieldCheck size={20} />
      </div>
      <Card>
        <div className="announcements-toolbar">
          <div className="onecs-settings-search">
            <Search size={16} />
            <input
              aria-label="Anonslarda ara"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Başlık, içerik veya hazırlayan kişi ara…"
            />
          </div>
          <div
            className="announcements-filters"
            role="group"
            aria-label="Anons durum filtresi"
          >
            {[
              { value: "all", label: "Tümü" },
              { value: "PUBLISHED", label: "Yayında" },
              { value: "DRAFT", label: "Bekleyenler" },
              { value: "WITHDRAWN", label: "Geri çekilenler" },
            ].map((option) => (
              <button
                key={option.value}
                className={status === option.value ? "active" : ""}
                onClick={() => {
                  setStatus(option.value);
                  setSearchParams((current) => {
                    const next = new URLSearchParams(current);
                    if (option.value === "all") next.delete("status");
                    else next.set("status", option.value);
                    return next;
                  });
                }}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </Card>
      {loading && !data ? (
        <Loading />
      ) : !visible.length ? (
        <Card>
          <EmptyState
            icon={<Megaphone size={30} />}
            title={
              query
                ? "Aramanızla eşleşen anons bulunamadı."
                : "Bu görünümde anons bulunmuyor."
            }
            description="Seçilen ekipler için bir duyuru taslağı hazırlayabilirsiniz."
          />
        </Card>
      ) : (
        <div className="announcements-grid">
          {visible.map((item) => (
            <Card
              className={`announcement-card ${item.pinned ? "pinned" : ""}`}
              key={item.id}
            >
              <div className="announcement-card-header">
                <Badge
                  tone={
                    item.status === "PUBLISHED"
                      ? "success"
                      : item.status === "WITHDRAWN"
                        ? "neutral"
                        : "warning"
                  }
                >
                  {labels[item.status] || item.status}
                </Badge>
                {item.pinned && (
                  <span className="announcement-pin">
                    <Pin size={13} />
                    Sabit
                  </span>
                )}
              </div>
              <button
                className="announcement-title"
                onClick={() => openSelected(item)}
              >
                <h2>{item.title}</h2>
              </button>
              <p className="announcement-preview">{item.body}</p>
              <div className="announcement-audience">
                <Users size={14} />
                {item.all_cs ? "Tüm CS" : "Seçili ekipler"}
                {item.status === "PUBLISHED" &&
                  new Date(item.starts_at) > new Date() && (
                    <Badge>Planlandı</Badge>
                  )}
              </div>
              <footer>
                <div>
                  <span>{item.author_name || "Hazırlayan"}</span>
                  <small>
                    <CalendarClock size={12} />
                    {date(item.starts_at, true)}
                  </small>
                </div>
                <button
                  className="announcement-detail-link"
                  onClick={() => openSelected(item)}
                >
                  Ayrıntılar
                </button>
              </footer>
              {item.status === "DRAFT" &&
                (item.permissions?.publish ??
                  scope(item.owner_org_id, ["DIRECTOR", "UNIT_HEAD"])) && (
                  <div className="announcement-card-action">
                    <Button
                      variant="secondary"
                      disabled={busy === item.id}
                      onClick={() => action(item, "publish")}
                    >
                      <Send size={14} />
                      Yayınla
                    </Button>
                  </div>
                )}
            </Card>
          ))}
        </div>
      )}
      {creating && (
        <Drawer
          title="Anons öner"
          subtitle="İçerik ve hedef kitle, yetkili yönetici kararına sunulur."
          onClose={() => {
            if (!busy) setCreating(false);
          }}
        >
          <form onSubmit={create} className="announcements-form">
            {failure && <ErrorState message={failure} />}
            <Field label="Başlık">
              <input
                required
                maxLength={240}
                value={form.title}
                onChange={(event) => set("title", event.target.value)}
                placeholder="Anonsun kısa ve anlaşılır başlığı"
              />
            </Field>
            <Field
              label="İçerik"
              hint="Yalnız seçtiğiniz hedef kitlenin okuyabileceği bilgileri paylaşın."
            >
              <textarea
                required
                rows={7}
                maxLength={10000}
                value={form.body}
                onChange={(event) => set("body", event.target.value)}
                placeholder="Ne oldu, kimleri ilgilendiriyor ve beklenen aksiyon ne?"
              />
            </Field>
            <label className="announcements-checkbox">
              <input
                type="checkbox"
                checked={form.all_cs}
                onChange={(event) => set("all_cs", event.target.checked)}
              />
              <span>
                <strong>Tüm CS’ye duyur</strong>
                <small>Direktörlük genelinde yayın kararı istenir.</small>
              </span>
            </label>
            <fieldset
              className="announcements-audience-options"
              disabled={form.all_cs}
            >
              <legend>Hedef ekipler</legend>
              {orgs
                .filter((org) => ["UNIT", "TEAM"].includes(org.kind))
                .map((org) => (
                  <label key={org.id}>
                    <input
                      type="checkbox"
                      checked={form.audience_org_ids.includes(org.id)}
                      onChange={(event) =>
                        set(
                          "audience_org_ids",
                          event.target.checked
                            ? [...form.audience_org_ids, org.id]
                            : form.audience_org_ids.filter(
                                (id) => id !== org.id,
                              ),
                        )
                      }
                    />
                    <span>
                      <strong>{org.code}</strong>
                      <small>{org.name}</small>
                    </span>
                  </label>
                ))}
            </fieldset>
            <p className="onecs-settings-footnote">
              Ekip seçilmezse kendi biriminize yönelik taslak oluşur.
            </p>
            <div className="announcements-date-grid">
              <Field label="Başlangıç (isteğe bağlı)">
                <input
                  type="datetime-local"
                  value={form.starts_at}
                  onChange={(event) => set("starts_at", event.target.value)}
                />
              </Field>
              <Field label="Bitiş (isteğe bağlı)">
                <input
                  type="datetime-local"
                  min={form.starts_at || undefined}
                  value={form.ends_at}
                  onChange={(event) => set("ends_at", event.target.value)}
                />
              </Field>
            </div>
            <label className="announcements-checkbox">
              <input
                type="checkbox"
                checked={form.pinned}
                onChange={(event) => set("pinned", event.target.checked)}
              />
              <span>Yayınlandığında öne çıkar</span>
            </label>
            <RecordExtras
              value={extras}
              onChange={setExtras}
              disabled={!!busy}
              emailHint="Seçtiğiniz kişilere e-posta, anons yayınlandıktan ve başlangıç zamanı geldikten sonra gönderilir. Kişiler anonsun hedef kitlesinde olmalıdır; e-posta seçimi erişim hakkı vermez."
            />
            <div className="drawer-actions">
              <Button
                type="button"
                variant="secondary"
                onClick={() => setCreating(false)}
                disabled={!!busy}
              >
                Vazgeç
              </Button>
              <Button type="submit" disabled={!!busy}>
                {busy === "create" ? "Kaydediliyor…" : "Taslağı kaydet"}
              </Button>
            </div>
          </form>
        </Drawer>
      )}
      {selected && (
        <Drawer
          title={selected.title}
          subtitle={`${selected.author_name} · ${date(selected.created_at, true)}`}
          onClose={closeSelected}
        >
          <div className="announcements-detail">
            <div className="announcement-card-header">
              <Badge
                tone={selected.status === "PUBLISHED" ? "success" : "warning"}
              >
                {labels[selected.status] || selected.status}
              </Badge>
              <span className="announcement-audience">
                <Users size={14} />
                {selected.all_cs ? "Tüm CS" : "Seçili ekipler"}
              </span>
            </div>
            <p>{selected.body}</p>
            <RecordAttachments
              resourceType="announcement"
              resourceId={selected.id}
            />
            <dl>
              <div>
                <dt>Başlangıç</dt>
                <dd>{date(selected.starts_at, true)}</dd>
              </div>
              <div>
                <dt>Bitiş</dt>
                <dd>
                  {selected.ends_at
                    ? date(selected.ends_at, true)
                    : "Süre sınırı yok"}
                </dd>
              </div>
              <div>
                <dt>Kaynak birim</dt>
                <dd>
                  {orgs.find((org) => org.id === selected.owner_org_id)?.code ||
                    "—"}
                </dd>
              </div>
              <div>
                <dt>Kayıt sürümü</dt>
                <dd>{selected.version}</dd>
              </div>
            </dl>
            {failure && <ErrorState message={failure} />}
            <div className="drawer-actions">
              {selected.status === "DRAFT" &&
                (selected.permissions?.publish ??
                  scope(selected.owner_org_id, ["DIRECTOR", "UNIT_HEAD"])) && (
                  <Button
                    onClick={() => action(selected, "publish")}
                    disabled={!!busy}
                  >
                    <Send size={15} />
                    Yayınla
                  </Button>
                )}
              {selected.status === "PUBLISHED" &&
                (selected.permissions?.withdraw ??
                  scope(selected.owner_org_id, [
                    "DIRECTOR",
                    "UNIT_HEAD",
                    "TEAM_MANAGER",
                  ])) && (
                  <Button
                    variant="secondary"
                    onClick={() => action(selected, "withdraw")}
                    disabled={!!busy}
                  >
                    Yayından geri çek
                  </Button>
                )}
              <Button variant="secondary" onClick={closeSelected}>
                Kapat
              </Button>
            </div>
          </div>
        </Drawer>
      )}
    </div>
  );
}
