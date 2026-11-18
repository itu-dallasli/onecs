import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { FormEvent } from "react";
import {
  Award,
  ArrowRight,
  CalendarDays,
  Check,
  Clock3,
  Compass,
  HandHelping,
  Heart,
  Lightbulb,
  MapPin,
  Megaphone,
  MessageSquare,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { api, date, list, personName, useResource } from "../lib/api";
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
type Kind = "community" | "events" | "credentials";
const sharingKindNames: Record<string, string> = {
  HELP: "Destek çağrısı",
  LESSON: "Öğrenilen ders",
  SUCCESS: "Ekip başarısı",
  OFFER: "Destek teklifi",
  KNOWLEDGE: "Bilgi paylaşımı",
  UPDATE: "Çalışma paylaşımı",
};
const cfg = {
  community: {
    title: "CS’de Neler Oluyor?",
    eyebrow: "ORTAK DENEYİM, ORTAK BAŞARI",
    description:
      "Ekipleri buluşturan çalışmalar, öğrenilenler ve yardım çağrıları.",
    new: "Paylaşım oluştur",
    endpoint: "/community",
    icon: Compass,
  },
  events: {
    title: "Etkinlikler",
    eyebrow: "CS TAKVİMİ",
    description:
      "Buluşmaları planlayın, bilgi paylaşın ve birlikte zaman ayırın.",
    new: "Etkinlik oluştur",
    endpoint: "/events",
    icon: CalendarDays,
  },
  credentials: {
    title: "Sertifikalar",
    eyebrow: "YETKİNLİK VE YENİLEME TAKİBİ",
    description:
      "Ekip yetkinlikleri, geçerlilik tarihleri ve yaklaşan yenilemeler.",
    new: "Sertifika ekle",
    endpoint: "/credentials",
    icon: Award,
  },
};
export default function Community({ kind }: { kind: Kind }) {
  const c = cfg[kind];
  const { user } = useAuth();
  const r = useResource<any>(c.endpoint);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [create, setCreate] = useState(false);
  const [selected, setSelected] = useState<any>(null);
  const [error, setError] = useState("");
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedId = searchParams.get("id")?.toLowerCase() || null;
  const validId =
    !!requestedId &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      requestedId,
    );
  const linkedRecord = useResource<any>(
    validId ? `${c.endpoint}/${requestedId}` : null,
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
  useEffect(() => {
    if (!validId || (linkedRecord.error && !linkedRecord.data)) {
      setSelected(null);
      return;
    }
    if (linkedRecord.data?.id === requestedId) setSelected(linkedRecord.data);
    else
      setSelected((current: any) =>
        current?.id === requestedId ? current : null,
      );
  }, [requestedId, c.endpoint, validId, linkedRecord.data, linkedRecord.error]);
  const rows = list(r.data);
  const visible = rows.filter(
    (x: any) =>
      (!query ||
        `${x.title || x.name} ${x.body || x.description || ""}`
          .toLocaleLowerCase("tr-TR")
          .includes(query.toLocaleLowerCase("tr-TR"))) &&
      (filter === "all" ||
        (filter === "mine" &&
          (x.author_id === user.id ||
            x.user_id === user.id ||
            x.user?.id === user.id ||
            x.created_by_id === user.id)) ||
        (filter === "HELP" && x.kind === "HELP") ||
        (filter === "upcoming" &&
          new Date(x.starts_at || x.expires_on || x.expires_at).getTime() >
            Date.now())),
  );
  const mutate = async (row: any, action: string, body: any = {}) => {
    setError("");
    try {
      const result = await api<any>(`${c.endpoint}/${row.id}/${action}`, {
        method: "POST",
        body: { version: row.version, ...body },
      });
      r.refresh();
      setSelected(
        result?.id === row.id ? result : await api(`${c.endpoint}/${row.id}`),
      );
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <>
      <PageHeader
        title={c.title}
        eyebrow={c.eyebrow}
        description={c.description}
        actions={
          (kind !== "events" || user.permissions?.manage_unit) && (
            <Button onClick={() => setCreate(true)}>
              <Plus size={16} />
              {c.new}
            </Button>
          )
        }
      />
      {kind === "community" && (
        <div className="community-intro">
          <div className="community-intro-icon">
            <Users size={25} />
          </div>
          <div>
            <strong>Birbirimizi tanıdıkça, daha iyi birlikte çalışırız.</strong>
            <p>
              Kim ne üzerinde çalışıyor? Hangi ekipten destek alabilirsiniz?
              Paylaşılabilir özetleri keşfedin.
            </p>
          </div>
          <a className="text-button" href="/organization">
            Ekipleri tanı
            <ArrowRight size={15} />
          </a>
        </div>
      )}
      {kind === "credentials" && (
        <div className="overview-strip">
          <div>
            <Award size={17} />
            <strong>{rows.length}</strong>
            <span>sertifika</span>
          </div>
          <div>
            <span className="tiny-dot warning" />
            <strong>
              {
                rows.filter(
                  (x: any) =>
                    new Date(x.expires_on || x.expires_at).getTime() <
                      Date.now() + 30 * 86400000 &&
                    new Date(x.expires_on || x.expires_at).getTime() >
                      Date.now(),
                ).length
              }
            </strong>
            <span>30 gün içinde yenilenecek</span>
          </div>
          <div>
            <ShieldCheck size={17} />
            <strong>
              {
                rows.filter((x: any) => x.verification_status === "VERIFIED")
                  .length
              }
            </strong>
            <span>doğrulanmış</span>
          </div>
        </div>
      )}
      <div className="standalone-toolbar">
        <div className="segmented">
          {[
            ["all", "Tümü"],
            ["mine", kind === "credentials" ? "Sertifikalarım" : "Bana ait"],
            [
              kind === "community" ? "HELP" : "upcoming",
              kind === "community" ? "Yardım çağrıları" : "Yaklaşanlar",
            ],
          ].map(([v, l]) => (
            <button
              key={v}
              className={filter === v ? "active" : ""}
              onClick={() => setFilter(v)}
            >
              {l}
            </button>
          ))}
        </div>
        <div className="table-search">
          <Search size={15} />
          <input
            placeholder={
              kind === "community"
                ? "Paylaşım ara…"
                : kind === "events"
                  ? "Etkinlik ara…"
                  : "Sertifika veya kurum ara…"
            }
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Kayıtlarda ara"
          />
        </div>
      </div>
      {requestedId &&
        (!validId || (linkedRecord.error && !linkedRecord.data)) && (
          <div>
            <ErrorState
              message={
                !validId
                  ? "Kayıt bağlantısı geçersiz. Listeye dönüp kaydı yeniden seçin."
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
        <Loading label="Kayıt ayrıntısı yükleniyor…" />
      )}
      {error && <ErrorState message={error} />}{" "}
      {r.error && <ErrorState message={r.error} onRetry={r.refresh} />}{" "}
      {r.loading && !r.data ? (
        <Loading />
      ) : visible.length ? (
        kind === "credentials" ? (
          <Card>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>SERTİFİKA</th>
                    <th>SAHİBİ</th>
                    <th>KURUM</th>
                    <th>GEÇERLİLİK</th>
                    <th>DURUM</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {visible.map((x: any) => (
                    <tr key={x.id}>
                      <td>
                        <button
                          className="record-title"
                          onClick={() => openSelected(x)}
                        >
                          <strong>{x.name || x.title}</strong>
                          <small>
                            {x.important
                              ? "Önemli sertifika"
                              : "Kişisel yetkinlik"}
                          </small>
                        </button>
                      </td>
                      <td>
                        {x.user_name ||
                          x.owner_name ||
                          personName(x.user || x.owner)}
                      </td>
                      <td>{x.issuer || "—"}</td>
                      <td>
                        <span className="date-cell">
                          <CalendarDays size={13} />
                          {x.no_expiry
                            ? "Süresiz"
                            : date(x.expires_on || x.expires_at)}
                        </span>
                      </td>
                      <td>
                        <Badge
                          tone={
                            new Date(x.expires_on || x.expires_at).getTime() <
                            Date.now()
                              ? "danger"
                              : x.verification_status === "REJECTED"
                                ? "danger"
                                : x.verification_status === "VERIFIED"
                                  ? "success"
                                  : "neutral"
                          }
                        >
                          {new Date(x.expires_on || x.expires_at).getTime() <
                          Date.now()
                            ? "Süresi doldu"
                            : x.verification_status === "REJECTED"
                              ? "Reddedildi"
                              : x.verification_status === "VERIFIED"
                                ? "Doğrulandı"
                                : "Beyan edildi"}
                        </Badge>
                      </td>
                      <td>
                        <button
                          className="icon-button"
                          aria-label="Sertifika ayrıntısı"
                          onClick={() => openSelected(x)}
                        >
                          <ArrowRight size={16} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        ) : (
          <div className={kind === "events" ? "event-grid" : "community-grid"}>
            {visible.map((x: any) =>
              kind === "events" ? (
                <Card key={x.id} className="event-card">
                  <div className="event-card-top">
                    <div className="event-date">
                      <span>
                        {x.starts_at
                          ? new Date(x.starts_at).toLocaleDateString("tr-TR", {
                              month: "short",
                            })
                          : "CS"}
                      </span>
                      <strong>
                        {x.starts_at ? new Date(x.starts_at).getDate() : "—"}
                      </strong>
                    </div>
                    <Badge>
                      {x.kind === "KNOWLEDGE"
                        ? "Bilgi paylaşımı"
                        : sharingKindNames[x.kind] || "CS Etkinliği"}
                    </Badge>
                  </div>
                  <button
                    className="card-title-button"
                    onClick={() => openSelected(x)}
                  >
                    <h3>{x.title}</h3>
                  </button>
                  <p>{x.description || x.summary}</p>
                  <div className="event-details">
                    <span>
                      <Clock3 size={14} />
                      {date(x.starts_at, true)}
                    </span>
                    <span>
                      <MapPin size={14} />
                      {x.location || "Konum belirtilmedi"}
                    </span>
                  </div>
                  <div className="card-bottom">
                    <span className="muted">
                      {x.counts?.YES ??
                        x.rsvp_count ??
                        x.participant_count ??
                        0}{" "}
                      katılım yanıtı
                    </span>
                    <Button variant="secondary" onClick={() => openSelected(x)}>
                      Ayrıntılar
                      <ArrowRight size={14} />
                    </Button>
                  </div>
                </Card>
              ) : (
                <Card
                  key={x.id}
                  className={`community-card community-${String(x.kind).toLowerCase()}`}
                >
                  <div className="community-card-top">
                    <span className="card-category-icon">
                      {x.kind === "HELP" ? (
                        <HandHelping size={19} />
                      ) : x.kind === "LESSON" ? (
                        <Lightbulb size={19} />
                      ) : (
                        <Sparkles size={19} />
                      )}
                    </span>
                    <Badge>
                      {(
                        {
                          HELP: "Destek çağrısı",
                          LESSON: "Öğrenilenler",
                          SUCCESS: "Ekip başarısı",
                          KNOWLEDGE: "Bilgi paylaşımı",
                          UPDATE: "Çalışma paylaşımı",
                        } as any
                      )[x.kind] || "Ekip paylaşımı"}
                    </Badge>
                    {x.status !== "PUBLISHED" && <Status value={x.status} />}
                  </div>
                  <button
                    className="card-title-button"
                    onClick={() => openSelected(x)}
                  >
                    <h3>{x.title}</h3>
                  </button>
                  <p>{x.body || x.summary || x.description}</p>
                  <div className="community-author">
                    <span className="avatar-sm">
                      {(
                        x.author_name ||
                        x.author?.display_name ||
                        x.org_name ||
                        "CS"
                      ).slice(0, 2)}
                    </span>
                    <div>
                      <strong>
                        {x.author_name || x.author?.display_name || "CS Ekibi"}
                      </strong>
                      <small>
                        {x.owner_org_name || x.org_name || date(x.created_at)}
                      </small>
                    </div>
                  </div>
                  <div className="card-bottom">
                    <span className="source-note">
                      <ShieldCheck size={12} />
                      Onaylı paylaşım kapsamı
                    </span>
                    <button
                      className="text-button"
                      onClick={() => openSelected(x)}
                    >
                      İncele
                      <ArrowRight size={14} />
                    </button>
                  </div>
                </Card>
              ),
            )}
          </div>
        )
      ) : (
        <Card>
          <EmptyState
            title={
              query
                ? "Eşleşen kayıt bulunamadı"
                : kind === "community"
                  ? "Paylaşılacak çok şey var"
                  : kind === "events"
                    ? "Takvimde henüz etkinlik yok"
                    : "Henüz sertifika eklenmedi"
            }
            description={
              kind === "community"
                ? "Bir çalışma, öğrenilen ders veya yardım çağrısıyla ilk paylaşımı oluşturun."
                : "Yeni kayıtlar bu alanda görünecek."
            }
            icon={<c.icon size={30} />}
          />
        </Card>
      )}
      {create && (
        <Create
          kind={kind}
          onClose={() => setCreate(false)}
          onCreated={r.refresh}
        />
      )}{" "}
      {selected && (
        <Drawer
          title={selected.title || selected.name}
          subtitle={
            kind === "community"
              ? "EKİP PAYLAŞIMI"
              : kind === "events"
                ? "CS ETKİNLİĞİ"
                : "SERTİFİKA AYRINTISI"
          }
          onClose={closeSelected}
        >
          <div className="detail-status-row">
            <Status value={selected.status} />
            {selected.kind && (
              <Badge>
                {sharingKindNames[selected.kind] || "Ekip paylaşımı"}
              </Badge>
            )}
          </div>
          <p className="detail-description">
            {selected.body || selected.description || selected.summary}
          </p>
          {kind === "community" && (
            <>
              <div className="detail-facts">
                <div>
                  <span>Paylaşan</span>
                  <strong>
                    {selected.author_name ||
                      selected.author?.display_name ||
                      "CS Ekibi"}
                  </strong>
                </div>
                <div>
                  <span>Tarih</span>
                  <strong>{date(selected.created_at, true)}</strong>
                </div>
              </div>
              <div className="info-strip">
                Bu kartın paylaşılması kaynak kaydın erişimini genişletmez.
                Hassas teknik ayrıntılar kendi yetkilerinde kalır.
              </div>
              <div className="detail-action-bar">
                {selected.status === "DRAFT" && (
                  <Button onClick={() => mutate(selected, "submit")}>
                    Yayın onayına gönder
                  </Button>
                )}
                {["SUBMITTED", "PENDING", "CONTENT_APPROVED"].includes(
                  selected.status,
                ) &&
                  user.permissions?.manage_unit && (
                    <Button onClick={() => mutate(selected, "publish")}>
                      Paylaşımı yayınla
                      <Check size={15} />
                    </Button>
                  )}
                {selected.source_type === "project" &&
                  ["DRAFT", "SUBMITTED"].includes(selected.status) &&
                  user.permissions?.manage_projects && (
                    <Button
                      variant="secondary"
                      onClick={() => mutate(selected, "approve-content")}
                    >
                      Proje içeriğini onayla
                      <Check size={15} />
                    </Button>
                  )}
                {selected.status === "PUBLISHED" && (
                  <Button
                    variant="secondary"
                    onClick={() => mutate(selected, "interest")}
                  >
                    <Heart size={15} />
                    İlgileniyorum / Destek verebilirim
                  </Button>
                )}
              </div>
              <p className="muted small-text">
                İlgi bildirmek projeye üyelik veya iş ataması oluşturmaz.
              </p>
            </>
          )}
          {kind === "events" && (
            <EventDetail
              event={selected}
              onChanged={(event) => {
                setSelected(event);
                r.refresh();
              }}
            />
          )}
          {kind === "credentials" && (
            <>
              <div className="detail-facts">
                <div>
                  <span>Kurum</span>
                  <strong>{selected.issuer || "—"}</strong>
                </div>
                <div>
                  <span>Geçerlilik sonu</span>
                  <strong>
                    {selected.no_expiry
                      ? "Süresiz"
                      : date(selected.expires_on || selected.expires_at)}
                  </strong>
                </div>
                <div>
                  <span>Sahibi</span>
                  <strong>
                    {selected.user_name ||
                      selected.owner_name ||
                      personName(selected.user || selected.owner)}
                  </strong>
                </div>
                <div>
                  <span>Doğrulama</span>
                  <strong>
                    {selected.verification_status === "REJECTED"
                      ? "Reddedildi"
                      : selected.verification_status === "VERIFIED"
                        ? "Doğrulandı"
                        : "Kişisel beyan"}
                  </strong>
                </div>
              </div>
              {selected.permissions?.manage === true && (
                <CredentialManagement
                  key={selected.id}
                  credential={selected}
                  onChanged={(updated) => {
                    setSelected(updated);
                    r.refresh();
                  }}
                />
              )}
              <p className="info-strip">
                Önemli sertifikalar yaklaşan yenileme gündeminde görünür.
                Sertifika beyanı denetçi doğrulaması yerine geçmez.
              </p>
            </>
          )}
          {error && <ErrorState message={error} />}
        </Drawer>
      )}
    </>
  );
}
function Create({
  kind,
  onClose,
  onCreated,
}: {
  kind: Kind;
  onClose: () => void;
  onCreated: () => void;
}) {
  const { user } = useAuth();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [type, setType] = useState("SUCCESS");
  const [sourceType, setSourceType] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [allCs, setAllCs] = useState(false);
  const [audience, setAudience] = useState<string[]>([]);
  const orgs = useResource<any>(kind === "community" ? "/organization" : null);
  const sources = useResource<any>(
    sourceType
      ? `/${sourceType === "project" ? "projects" : sourceType === "case" ? "cases" : "work"}`
      : null,
  );
  const [starts, setStarts] = useState("");
  const [ends, setEnds] = useState("");
  const [location, setLocation] = useState("");
  const [issuer, setIssuer] = useState("");
  const [issued, setIssued] = useState("");
  const [expires, setExpires] = useState("");
  const [noExpiry, setNoExpiry] = useState(false);
  const canMarkOwnCredential =
    user.roles?.some(
      (role) =>
        ["DIRECTOR", "UNIT_HEAD", "TEAM_MANAGER"].includes(role.role) &&
        role.org_id === user.primary_org?.id,
    ) || user.test_mode?.god_mode;
  const [important, setImportant] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <Drawer title={cfg[kind].new} subtitle="YENİ KAYIT" onClose={onClose}>
      <form
        className="stack-form"
        onSubmit={async (e: FormEvent) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            let payload: any = {};
            if (kind === "community")
              payload = {
                title,
                body,
                kind: type,
                all_cs: allCs,
                ...(audience.length ? { audience_org_ids: audience } : {}),
                ...(sourceId
                  ? { source_type: sourceType, source_id: sourceId }
                  : {}),
              };
            if (kind === "events")
              payload = {
                title,
                description: body,
                starts_at: new Date(starts).toISOString(),
                ends_at: ends ? new Date(ends).toISOString() : null,
                location,
              };
            if (kind === "credentials")
              payload = {
                name: title,
                issuer,
                issued_on: issued || null,
                expires_on: noExpiry ? null : expires,
                no_expiry: noExpiry,
                important,
              };
            await api(cfg[kind].endpoint, { method: "POST", body: payload });
            onCreated();
            onClose();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {kind === "community" && (
          <div className="info-strip">
            Hassas teknik ayrıntılara yer vermeyin. Paylaşımınız yetkili
            onayından sonra yayınlanır.
          </div>
        )}
        <Field label={kind === "credentials" ? "Sertifika adı" : "Başlık"}>
          <input
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={
              kind === "community"
                ? "Ekibinizden paylaşılmaya değer ne var?"
                : ""
            }
          />
        </Field>
        {kind === "community" && (
          <Field label="Paylaşım türü">
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="KNOWLEDGE">Bilgi paylaşımı</option>
              <option value="HELP">Destek çağrısı</option>
              <option value="LESSON">Öğrenilen ders</option>
              <option value="SUCCESS">Ekip başarısı</option>
            </select>
          </Field>
        )}
        {kind === "community" && (
          <>
            <Field label="İlgili çalışma (isteğe bağlı)">
              <select
                value={sourceType}
                onChange={(e) => {
                  setSourceType(e.target.value);
                  setSourceId("");
                }}
              >
                <option value="">Bağımsız paylaşım</option>
                <option value="project">Proje</option>
                <option value="work">Birim işi</option>
                <option value="case">Vaka</option>
              </select>
            </Field>
            {sourceType && (
              <Field label="Kaynak kayıt">
                <select
                  required
                  value={sourceId}
                  onChange={(e) => setSourceId(e.target.value)}
                >
                  <option value="">Erişiminiz olan bir kaydı seçin</option>
                  {list(sources.data).map((x: any) => (
                    <option key={x.id} value={x.id}>
                      {x.title}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={allCs}
                onChange={(e) => setAllCs(e.target.checked)}
              />
              Tüm CS ile paylaşılması için onaya gönder
            </label>
            {!allCs && (
              <Field label="Paylaşılacak ekipler">
                <select
                  multiple
                  value={audience}
                  onChange={(e) =>
                    setAudience(
                      Array.from(e.target.selectedOptions, (o) => o.value),
                    )
                  }
                  size={4}
                >
                  {list(orgs.data)
                    .filter((o: any) => o.kind !== "DIRECTORATE")
                    .map((o: any) => (
                      <option value={o.id} key={o.id}>
                        {o.name}
                      </option>
                    ))}
                </select>
                <small>
                  Seçilmezse kendi biriminizle paylaşılır. Birden fazla ekip
                  için ⌘/Ctrl ile seçin.
                </small>
              </Field>
            )}
          </>
        )}
        {kind !== "credentials" && (
          <Field label="Açıklama">
            <textarea
              rows={5}
              required
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </Field>
        )}
        {kind === "events" && (
          <>
            <div className="form-grid">
              <Field label="Başlangıç">
                <input
                  type="datetime-local"
                  required
                  value={starts}
                  onChange={(e) => setStarts(e.target.value)}
                />
              </Field>
              <Field label="Bitiş">
                <input
                  type="datetime-local"
                  value={ends}
                  onChange={(e) => setEnds(e.target.value)}
                  min={starts}
                />
              </Field>
            </div>
            <Field label="Yer / Bağlantı">
              <input
                value={location}
                onChange={(e) => setLocation(e.target.value)}
              />
            </Field>
          </>
        )}
        {kind === "credentials" && (
          <>
            <Field label="Sertifikayı veren kurum">
              <input
                required
                value={issuer}
                onChange={(e) => setIssuer(e.target.value)}
              />
            </Field>
            <div className="form-grid">
              <Field label="Alınma tarihi">
                <input
                  type="date"
                  value={issued}
                  onChange={(e) => setIssued(e.target.value)}
                />
              </Field>
              <Field label="Geçerlilik sonu">
                <input
                  type="date"
                  required={!noExpiry}
                  disabled={noExpiry}
                  value={expires}
                  min={issued}
                  onChange={(e) => setExpires(e.target.value)}
                />
              </Field>
            </div>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={noExpiry}
                onChange={(e) => {
                  setNoExpiry(e.target.checked);
                  if (e.target.checked) setExpires("");
                }}
              />
              Bu sertifikanın geçerlilik süresi yok
            </label>
            {canMarkOwnCredential && (
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={important}
                  onChange={(e) => setImportant(e.target.checked)}
                />
                Önemli sertifika olarak işaretle
              </label>
            )}
          </>
        )}
        {error && <ErrorState message={error} />}
        <div className="form-actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            Vazgeç
          </Button>
          <Button disabled={busy}>
            {busy ? "Kaydediliyor…" : "Kaydet"}
            <Plus size={15} />
          </Button>
        </div>
      </form>
    </Drawer>
  );
}

function EventDetail({
  event,
  onChanged,
}: {
  event: any;
  onChanged: (event: any) => void;
}) {
  const [tool, setTool] = useState<"poll" | "attendance" | null>(null);
  const [question, setQuestion] = useState("");
  const [optionsText, setOptionsText] = useState("");
  const [maximum, setMaximum] = useState(1);
  const [closesAt, setClosesAt] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const canManage = event.permissions?.manage === true;
  const canRsvp = event.permissions?.rsvp !== false;
  const participants = useResource<any>(
    canManage && tool === "attendance"
      ? `/events/${event.id}/participants`
      : null,
    undefined,
    0,
  );
  const options = optionsText
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);
  const participantRows = list(participants.data);
  const perform = async (action: string, payload: any, key = action) => {
    setBusy(key);
    setError("");
    setSuccess("");
    try {
      await api(`/events/${event.id}/${action}`, {
        method: "POST",
        body: { version: event.version, ...payload },
      });
      const updated = await api(`/events/${event.id}`);
      onChanged(updated);
      if (action === "attendance") participants.refresh();
      setSuccess(
        action === "poll"
          ? "Anket oluşturuldu. Davetli listesi bu anket için sabitlendi."
          : action === "attendance"
            ? "Gerçekleşmiş katılım kaydedildi. Katılım yanıtı değişmedi."
            : action === "rsvp"
              ? "Katılım yanıtınız kaydedildi."
              : "Anket yanıtınız kaydedildi.",
      );
      if (action === "poll") {
        setQuestion("");
        setOptionsText("");
        setClosesAt("");
        setMaximum(1);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  return (
    <>
      <div className="detail-facts">
        <div>
          <span>Başlangıç</span>
          <strong>{date(event.starts_at, true)}</strong>
        </div>
        <div>
          <span>Konum</span>
          <strong>{event.location || "—"}</strong>
        </div>
        <div>
          <span>Davetli / Katılacak / Yanıtsız</span>
          <strong>
            {event.counts?.invited ?? 0} / {event.counts?.YES ?? 0} /{" "}
            {event.counts?.unanswered ?? 0}
          </strong>
        </div>
        <div>
          <span>Gerçekleşmiş katılım</span>
          <strong>{event.counts?.attended ?? 0} kişi</strong>
        </div>
      </div>
      {error && <ErrorState message={error} />}{" "}
      {success && (
        <div className="success-state" role="status">
          <Check size={15} />
          {success}
        </div>
      )}
      <div className="detail-block">
        <h3>Katılım yanıtınız</h3>
        <p className="muted small-text">
          {event.rsvp
            ? `Güncel yanıtınız: ${{ YES: "Katılacağım", NO: "Katılamıyorum", MAYBE: "Kararsızım" }[event.rsvp as "YES" | "NO" | "MAYBE"]}`
            : "Henüz katılım yanıtı vermediniz."}
        </p>
        {canRsvp ? (
          <div className="detail-action-bar">
            {[
              ["YES", "Katılacağım"],
              ["MAYBE", "Kararsızım"],
              ["NO", "Katılamıyorum"],
            ].map(([response, label]) => (
              <Button
                key={response}
                variant={event.rsvp === response ? "primary" : "secondary"}
                disabled={!!busy}
                onClick={() => perform("rsvp", { response })}
              >
                {label}
                {event.rsvp === response && <Check size={14} />}
              </Button>
            ))}
          </div>
        ) : (
          <p className="info-strip">
            Bu etkinlik için davetli değilsiniz. Yönetim kapsamınızla etkinlik
            ayrıntılarını inceliyorsunuz.
          </p>
        )}
        <p className="muted small-text">
          Katılım yanıtı planlama içindir. Etkinlikte fiilen bulunma, yönetici
          tarafından ayrıca kaydedilir.
        </p>
      </div>
      {canManage && (
        <div className="detail-block">
          <h3>Etkinlik yönetimi</h3>
          <div className="detail-action-bar">
            <Button
              variant="secondary"
              onClick={() => {
                setTool(tool === "poll" ? null : "poll");
                setError("");
              }}
            >
              <Plus size={15} />
              Anket oluştur
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setTool(tool === "attendance" ? null : "attendance");
                setError("");
              }}
            >
              <Users size={15} />
              Gerçekleşmiş katılımı kaydet
            </Button>
          </div>
          {tool === "poll" && (
            <form
              className="inline-form"
              onSubmit={async (e: FormEvent) => {
                e.preventDefault();
                setError("");
                if (options.length < 2 || options.length > 20) {
                  setError("Anket için 2–20 seçenek girin.");
                  return;
                }
                if (new Set(options).size !== options.length) {
                  setError("Anket seçenekleri birbirinden farklı olmalıdır.");
                  return;
                }
                if (maximum < 1 || maximum > options.length) {
                  setError(
                    "Seçim sınırı 1 ile seçenek sayısı arasında olmalıdır.",
                  );
                  return;
                }
                if (!closesAt || new Date(closesAt).getTime() <= Date.now()) {
                  setError("Anket kapanış zamanı gelecekte olmalıdır.");
                  return;
                }
                await perform("poll", {
                  question,
                  options,
                  max_choices: maximum,
                  closes_at: new Date(closesAt).toISOString(),
                });
              }}
            >
              <Field label="Anket sorusu">
                <input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  required
                  maxLength={300}
                  placeholder="Örn. Bilgi paylaşımı oturumu için hangi tarih uygun?"
                />
              </Field>
              <Field label="Seçenekler · Her satıra bir seçenek">
                <textarea
                  rows={5}
                  required
                  value={optionsText}
                  onChange={(e) => setOptionsText(e.target.value)}
                  placeholder={"Perşembe 14.00\nCuma 11.00\nPazartesi 15.00"}
                />
                <small>
                  2–20 seçenek. Yayın sonrası anlamı değiştirilmez; gerekirse
                  yeni anket açılır.
                </small>
              </Field>
              <div className="form-grid">
                <Field label="En fazla kaç seçenek seçilebilir?">
                  <input
                    type="number"
                    min={1}
                    max={Math.max(1, options.length)}
                    required
                    value={maximum}
                    onChange={(e) => setMaximum(Number(e.target.value))}
                  />
                </Field>
                <Field label="Yanıt son tarihi">
                  <input
                    type="datetime-local"
                    value={closesAt}
                    onChange={(e) => setClosesAt(e.target.value)}
                    required
                  />
                </Field>
              </div>
              <div className="info-strip">
                Anket isimlidir. Davetli listesi oluşturma anında sabitlenir.
                Katılım yanıtı ve gerçekleşen katılım ayrı kalır.
              </div>
              <Button disabled={!!busy || !question.trim()} type="submit">
                {busy === "poll" ? "Anket oluşturuluyor…" : "Anketi oluştur"}
                <Plus size={15} />
              </Button>
            </form>
          )}
          {tool === "attendance" && (
            <div className="inline-form">
              <p className="muted small-text">
                Yalnız bu etkinliğin davetlileri gösterilir. Henüz kaydedilmemiş
                durum ile katılmadı yanıtı ayrı tutulur.
              </p>
              {participants.error && (
                <ErrorState
                  message={participants.error}
                  onRetry={participants.refresh}
                />
              )}{" "}
              {participants.loading ? (
                <Loading label="Davetliler ve katılım kayıtları yükleniyor…" />
              ) : participantRows.length ? (
                <div>
                  {participantRows.map((person: any) => (
                    <div className="subtask-row" key={person.id}>
                      <div>
                        <strong>
                          {person.display_name || personName(person.user)}
                        </strong>
                        <small>
                          Planlanan yanıt:{" "}
                          {{
                            YES: "Katılacağım",
                            NO: "Katılamıyorum",
                            MAYBE: "Kararsızım",
                          }[person.rsvp as "YES" | "NO" | "MAYBE"] ||
                            "Yanıt vermedi"}
                        </small>
                      </div>
                      <Field label="Gerçekleşmiş katılım">
                        <select
                          aria-label={`${person.display_name || "Davetli"} gerçekleşmiş katılımı`}
                          value={
                            person.present === true
                              ? "yes"
                              : person.present === false
                                ? "no"
                                : "unset"
                          }
                          disabled={!!busy}
                          onChange={(e) => {
                            if (e.target.value !== "unset")
                              void perform(
                                "attendance",
                                {
                                  user_id: person.id,
                                  present: e.target.value === "yes",
                                },
                                person.id,
                              );
                          }}
                        >
                          <option value="unset" disabled>
                            Henüz kaydedilmedi
                          </option>
                          <option value="yes">Katıldı</option>
                          <option value="no">Katılmadı</option>
                        </select>
                      </Field>
                    </div>
                  ))}
                </div>
              ) : (
                !participants.error && (
                  <EmptyState title="Bu etkinlikte davetli bulunmuyor" />
                )
              )}
            </div>
          )}
        </div>
      )}
      {list(event.polls).map((poll: any) => (
        <PollResponse
          key={poll.id}
          poll={poll}
          canRespond={canRsvp}
          busy={!!busy}
          onSubmit={(choices) =>
            perform("poll-response", { poll_id: poll.id, choices }, poll.id)
          }
        />
      ))}
    </>
  );
}
function PollResponse({
  poll,
  canRespond,
  busy,
  onSubmit,
}: {
  poll: any;
  canRespond: boolean;
  busy: boolean;
  onSubmit: (choices: string[]) => Promise<void>;
}) {
  const [choices, setChoices] = useState<string[]>(poll.my_choices || []);
  const closed = new Date(poll.closes_at).getTime() <= Date.now();
  const maximum = Number(poll.max_choices) || 1;
  const options = list(poll.options);
  return (
    <form
      className="detail-block stack-form"
      onSubmit={async (e: FormEvent) => {
        e.preventDefault();
        await onSubmit(choices);
      }}
    >
      <div>
        <div className="detail-status-row">
          <Badge tone={closed ? "neutral" : "success"}>
            {closed ? "Yanıta kapalı" : "Yanıta açık"}
          </Badge>
          <Badge>
            {maximum === 1 ? "Tek seçim" : `En fazla ${maximum} seçim`}
          </Badge>
        </div>
        <h3>{poll.question}</h3>
        <p className="muted small-text">
          Son tarih: {date(poll.closes_at, true)}
        </p>
      </div>
      <div className="stack-form" style={{ gap: 10 }}>
        {options.map((option: any) => {
          const selected = choices.includes(String(option.id));
          return (
            <label className="checkbox-row" key={option.id}>
              <input
                style={{
                  width: 15,
                  height: 15,
                  minHeight: 15,
                  accentColor: "#35495b",
                }}
                type={maximum === 1 ? "radio" : "checkbox"}
                name={`poll-${poll.id}`}
                checked={selected}
                value={option.id}
                disabled={
                  busy ||
                  closed ||
                  !canRespond ||
                  (!selected && maximum > 1 && choices.length >= maximum)
                }
                onChange={() =>
                  setChoices((previous) =>
                    maximum === 1
                      ? [String(option.id)]
                      : selected
                        ? previous.filter((x) => x !== String(option.id))
                        : [...previous, String(option.id)],
                  )
                }
              />
              <span>{option.label}</span>
              <Badge>
                {poll.result?.options?.[String(option.id)] ?? 0} yanıt
              </Badge>
            </label>
          );
        })}
      </div>
      <div className="row-meta">
        <span>{poll.result?.responded ?? 0} yanıtlayan</span>
        <span>{poll.result?.eligible ?? 0} seçmen</span>
        <span>{poll.result?.unanswered ?? 0} yanıtsız</span>
      </div>
      {canRespond && !closed && (
        <Button
          variant="secondary"
          type="submit"
          disabled={busy || !choices.length || choices.length > maximum}
        >
          {poll.my_choices?.length ? "Yanıtı güncelle" : "Yanıtı kaydet"}
          <Check size={14} />
        </Button>
      )}
      {closed && (
        <p className="muted small-text">
          Kapanmış ankette yanıt değiştirilemez.
        </p>
      )}
    </form>
  );
}

function CredentialManagement({
  credential,
  onChanged,
}: {
  credential: any;
  onChanged: (credential: any) => void;
}) {
  const [important, setImportant] = useState(!!credential.important);
  const [verification, setVerification] = useState(
    credential.verification_status || "DECLARED",
  );
  const [alertDays, setAlertDays] = useState(
    Number(credential.alert_days) || 30,
  );
  const [version, setVersion] = useState(credential.version);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  return (
    <form
      className="detail-block stack-form"
      onSubmit={async (e: FormEvent) => {
        e.preventDefault();
        setBusy(true);
        setError("");
        setSuccess("");
        try {
          if (
            !Number.isInteger(alertDays) ||
            alertDays < 1 ||
            alertDays > 365
          ) {
            setError("Uyarı süresi 1–365 gün arasında tam sayı olmalıdır.");
            return;
          }
          const updated = await api(`/credentials/${credential.id}`, {
            method: "PATCH",
            body: {
              version,
              important,
              verification_status: verification,
              alert_days: alertDays,
            },
          });
          setVersion(updated.version);
          onChanged(updated);
          setSuccess("Sertifikanın yönetim bilgileri kaydedildi.");
        } catch (e) {
          setError((e as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      <div>
        <h3>Yönetici değerlendirmesi</h3>
        <p className="muted small-text">
          Bu kayıt için organizasyon kapsamınızda yönetim yetkiniz bulunuyor.
          Bilgiler kaynak sürümü kontrol edilerek kaydedilir.
        </p>
      </div>
      <Field label="Doğrulama durumu">
        <select
          value={verification}
          onChange={(e) => {
            setVerification(e.target.value);
            setSuccess("");
          }}
        >
          <option value="DECLARED">Beyan edildi · İnceleme bekliyor</option>
          <option value="VERIFIED">Yönetici tarafından doğrulandı</option>
          <option value="REJECTED">Reddedildi</option>
        </select>
      </Field>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={important}
          onChange={(e) => {
            setImportant(e.target.checked);
            setSuccess("");
          }}
        />
        Yönetim takibi için önemli sertifika
      </label>
      <Field
        label="Bitişten kaç gün önce uyarı verilsin?"
        hint={
          credential.no_expiry
            ? "Süresiz sertifikalar için bitiş uyarısı üretilmez."
            : "Önemli ve süreli kayıtlarda 1–365 gün arasında uyarı eşiği uygulanır."
        }
      >
        <input
          type="number"
          required
          min={1}
          max={365}
          step={1}
          value={alertDays}
          disabled={credential.no_expiry}
          onChange={(e) => {
            setAlertDays(Number(e.target.value));
            setSuccess("");
          }}
        />
      </Field>
      {error && <ErrorState message={error} />}{" "}
      {success && (
        <div className="success-state" role="status">
          <Check size={15} />
          {success}
        </div>
      )}
      <Button type="submit" disabled={busy}>
        {busy ? "Kaydediliyor…" : "Yönetim bilgilerini kaydet"}
        <Check size={15} />
      </Button>
    </form>
  );
}
