import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Check, ChevronDown, Search, Send, UserRound, X } from "lucide-react";
import { api, list, useResource } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Button, Drawer, ErrorState, Field, Loading } from "./ui";
import "../styles/organization.css";

export type AssignmentPerson = {
  id: string;
  display_name: string;
  username?: string;
  primary_org_name?: string;
  is_active?: boolean;
};
export default function WorkAssignmentForm({
  defaultTarget,
  onClose,
  onCreated,
}: {
  defaultTarget?: AssignmentPerson;
  onClose: () => void;
  onCreated: (work?: any) => void;
}) {
  const { user } = useAuth();
  const manager = Boolean(user.permissions?.manage_unit);
  const [personal, setPersonal] = useState(!manager && !defaultTarget);
  const [target, setTarget] = useState<AssignmentPerson | null>(
    defaultTarget || null,
  );
  const [pickerOpen, setPickerOpen] = useState(!defaultTarget && manager);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [expected, setExpected] = useState("");
  const [priority, setPriority] = useState("NORMAL");
  const [kind, setKind] = useState("TASK");
  const [due, setDue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(
      () => setDebouncedSearch(search.trim()),
      250,
    );
    return () => window.clearTimeout(timer);
  }, [search]);
  const people = useResource<any>(
    !personal && pickerOpen
      ? `/people?assignable=true&limit=60&search=${encodeURIComponent(debouncedSearch)}`
      : null,
    undefined,
    0,
  );
  const targetScope = useResource<any>(
    !personal && target ? `/people/${target.id}/assignable-scope` : null,
    undefined,
    0,
  );
  const allowedTarget = targetScope.data?.assignment?.allowed_target;
  const targetAllowed =
    !targetScope.loading &&
    !targetScope.error &&
    targetScope.data?.permissions?.can_assign_work === true &&
    allowedTarget?.person_id === target?.id;
  const selectedTarget = personal ? user : target;
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!personal && !targetAllowed) {
      setError(
        "Atama kapsamındaki aktif bir kişiyi seçin ve yetki doğrulamasının tamamlanmasını bekleyin.",
      );
      return;
    }
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const work = await api("/work", {
        method: "POST",
        body: {
          title: title.trim(),
          description: description.trim(),
          expected_outcome: expected.trim(),
          assignee_id: personal ? user.id : target!.id,
          personal,
          priority,
          kind,
          ...(personal && due ? { due_at: new Date(due).toISOString() } : {}),
        },
      });
      onCreated(work);
      onClose();
    } catch (failure) {
      setError((failure as Error).message);
      targetScope.refresh();
    } finally {
      setBusy(false);
    }
  }
  return (
    <Drawer
      title={defaultTarget ? "İş ata" : "İş oluştur"}
      subtitle="BİRİM İŞLERİ VE TAAHHÜTLER"
      onClose={onClose}
      wide
    >
      <form className="stack-form atlas-assignment-form" onSubmit={submit}>
        <section
          className="atlas-assignment-recipient"
          aria-label="İşin sorumlusu"
        >
          <div className="atlas-assignment-recipient-heading">
            <UserRound size={19} />
            <strong>Sorumlu kişi</strong>
            {!personal && (
              <span>Organizasyon yetkiniz kapsamındaki kişiler</span>
            )}
          </div>
          {manager && !defaultTarget && (
            <div className="atlas-assignment-mode">
              <button
                type="button"
                aria-pressed={!personal}
                className={!personal ? "active" : ""}
                onClick={() => {
                  setPersonal(false);
                  setPickerOpen(!target);
                  setError("");
                }}
              >
                Birine ata · SLA
              </button>
              <button
                type="button"
                aria-pressed={personal}
                className={personal ? "active" : ""}
                onClick={() => {
                  setPersonal(true);
                  setPickerOpen(false);
                  setError("");
                }}
              >
                Kendime kişisel iş aç
              </button>
            </div>
          )}
          {personal ? (
            <div className="atlas-assignment-selected">
              <span className="atlas-org-avatar">
                {(user.display_name || user.username)
                  .slice(0, 2)
                  .toLocaleUpperCase("tr-TR")}
              </span>
              <span>
                <strong>{user.display_name || user.username}</strong>
                <small>
                  Sorumlu sizsiniz. Kişisel iş hedef tarihle izlenir.
                </small>
              </span>
              <Check size={19} />
            </div>
          ) : (
            <>
              {target && (
                <div className="atlas-assignment-selected">
                  <span className="atlas-org-avatar">
                    {target.display_name.slice(0, 2).toLocaleUpperCase("tr-TR")}
                  </span>
                  <span>
                    <strong>{target.display_name || target.username}</strong>
                    <small>
                      {target.primary_org_name ||
                        allowedTarget?.org_name ||
                        "Birim bilgisi doğrulanıyor"}
                    </small>
                  </span>
                  <button
                    type="button"
                    aria-label="Atanan kişiyi değiştir"
                    onClick={() => {
                      setTarget(null);
                      setPickerOpen(true);
                      setSearch("");
                    }}
                  >
                    <X size={17} />
                  </button>
                </div>
              )}
              {!pickerOpen && !target && (
                <button
                  type="button"
                  className="atlas-assignment-open-picker"
                  onClick={() => setPickerOpen(true)}
                >
                  Kişi seçin <ChevronDown size={18} />
                </button>
              )}
              {pickerOpen && (
                <div className="atlas-assignment-picker">
                  <label className="atlas-org-search">
                    <Search size={17} />
                    <input
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                      placeholder="Ad, kullanıcı adı veya birim ara…"
                      aria-label="Atanacak kişiyi ara"
                      autoFocus
                    />
                  </label>
                  {people.error ? (
                    <ErrorState
                      message={people.error}
                      onRetry={people.refresh}
                    />
                  ) : people.loading ? (
                    <Loading label="Yetkiniz kapsamındaki kişiler aranıyor…" />
                  ) : list<AssignmentPerson>(people.data).length ? (
                    <div
                      className="atlas-assignment-options"
                      role="group"
                      aria-label="Atanabilecek kişiler"
                    >
                      {list<AssignmentPerson>(people.data)
                        .filter((item) => item.is_active !== false)
                        .map((item) => (
                          <button
                            type="button"
                            aria-pressed={target?.id === item.id}
                            key={item.id}
                            onClick={() => {
                              setTarget(item);
                              setPickerOpen(false);
                              setError("");
                            }}
                          >
                            <span className="atlas-org-avatar">
                              {(item.display_name || item.username || "")
                                .slice(0, 2)
                                .toLocaleUpperCase("tr-TR")}
                            </span>
                            <span>
                              <strong>
                                {item.display_name || item.username}
                              </strong>
                              <small>
                                {item.primary_org_name ||
                                  "Birim bilgisi paylaşılmamış"}
                              </small>
                            </span>
                            <ChevronDown size={15} />
                          </button>
                        ))}
                    </div>
                  ) : (
                    <p className="atlas-org-empty-note">
                      Atanabilecek kişi bulunamadı. Yalnızca yönetim
                      kapsamınızdaki aktif kişiler listelenir.
                    </p>
                  )}
                  {(people.data?.count || 0) > list(people.data).length && (
                    <p className="atlas-org-empty-note">
                      İlk {list(people.data).length} kişi gösteriliyor; adıyla
                      arayarak daraltabilirsiniz.
                    </p>
                  )}
                </div>
              )}
              {target && targetScope.loading && (
                <p className="atlas-assignment-validation" role="status">
                  Kişinin aktifliği ve atama yetkisi doğrulanıyor…
                </p>
              )}
              {target &&
                (targetScope.error ||
                  (!targetScope.loading &&
                    targetScope.data &&
                    !targetAllowed)) && (
                  <ErrorState
                    message="Bu kişiye iş atama yetkiniz bulunmuyor veya kişi artık aktif değil. Başka bir kişi seçin."
                    onRetry={targetScope.refresh}
                  />
                )}
            </>
          )}
        </section>
        <div className="info-strip">
          {personal
            ? "Kişisel iş yalnız size açılır. Resmî SLA, yöneticiniz işi benimsediğinde başlar."
            : "Resmî işin SLA süresi atama anında başlar. Atanan kişiye uygulama içi bildirim ve yapılandırılmış e-posta kuyruğu kaydı oluşturulur."}
        </div>
        <Field label="İşin başlığı">
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            maxLength={240}
            required
            placeholder="Ne yapılmasını bekliyorsunuz?"
          />
        </Field>
        <Field label="Açıklama">
          <textarea
            rows={3}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            required
            placeholder="İşin bağlamını ve kapsamını kısaca açıklayın."
          />
        </Field>
        <div className="form-grid">
          <Field label="Kayıt türü">
            <select
              value={kind}
              onChange={(event) => setKind(event.target.value)}
            >
              <option value="TASK">İş</option>
              <option value="COMMITMENT">Taahhüt</option>
            </select>
          </Field>
          <Field label={personal ? "Öncelik" : "Kritiklik / SLA"}>
            <select
              value={priority}
              onChange={(event) => setPriority(event.target.value)}
            >
              <option value="NORMAL">
                Normal{personal ? "" : " · 1 takvim ayı"}
              </option>
              <option value="HIGH">
                Yüksek{personal ? "" : " · 7 takvim günü"}
              </option>
              <option value="CRITICAL">
                Kritik{personal ? "" : " · 24 saat"}
              </option>
            </select>
          </Field>
        </div>
        <Field
          label="Beklenen çıktı"
          hint={
            kind === "COMMITMENT"
              ? "Taahhütte beklenen çıktı zorunludur."
              : "İşin hangi çıktı ile tamamlanacağını belirtin."
          }
        >
          <textarea
            rows={3}
            value={expected}
            onChange={(event) => setExpected(event.target.value)}
            required={kind === "COMMITMENT"}
            placeholder="Tamamlandığında ne teslim edilmiş olacak?"
          />
        </Field>
        {personal && (
          <Field label="Hedef tarih · isteğe bağlı">
            <input
              type="datetime-local"
              value={due}
              onChange={(event) => setDue(event.target.value)}
            />
          </Field>
        )}
        {error && <ErrorState message={error} />}
        <div className="form-actions">
          <Button
            variant="secondary"
            type="button"
            onClick={onClose}
            disabled={busy}
          >
            Vazgeç
          </Button>
          <Button
            type="submit"
            disabled={busy || !selectedTarget || (!personal && !targetAllowed)}
          >
            {busy
              ? "Kaydediliyor…"
              : personal
                ? "Kişisel işi oluştur"
                : "İşi ata"}
            <Send size={16} />
          </Button>
        </div>
      </form>
    </Drawer>
  );
}
