import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  Check,
  CheckCheck,
  ChevronDown,
  Clock3,
  FileText,
  Filter,
  Flag,
  GitBranch,
  Layers3,
  MessageSquare,
  MoreHorizontal,
  Plus,
  Search,
  ShieldAlert,
  Star,
  UserRound,
  Users,
} from "lucide-react";
import { api, date, list, personName, useResource } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { RecordItem } from "../lib/types";
import WorkAssignmentForm from "../components/WorkAssignmentForm";
import RecordExtras, {
  emptyRecordExtras,
  RecordAttachments,
} from "../components/RecordExtras";
import { createRecordWithExtras } from "../lib/recordExtras";
import ProjectInsights from "../components/ProjectInsights";
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
type Kind = "projects" | "work" | "cases";
const config = {
  projects: {
    title: "Projeler",
    eyebrow: "PROJE YÖNETİMİ",
    description:
      "Başvurudan teslimata, proje yönetimi ve ekiplerin ortak katkıları.",
    new: "Proje başvurusu",
    empty: "Henüz proje bulunmuyor",
    icon: Layers3,
  },
  work: {
    title: "İşler ve Taahhütler",
    eyebrow: "BİRİM OPERASYONLARI",
    description: "Sorumlular, sonraki adımlar ve taahhütler aynı yerde.",
    new: "İş oluştur",
    empty: "Bu görünümde iş bulunmuyor",
    icon: GitBranch,
  },
  cases: {
    title: "Vakalar",
    eyebrow: "ORTAK VAKA TAKİBİ",
    description:
      "Tek vaka altında koordinasyon, ekip aksiyonları ve doğrulanmış kapanış.",
    new: "Vaka oluştur",
    empty: "Henüz açık vaka bulunmuyor",
    icon: ShieldAlert,
  },
};
const workStatuses = [
  "OPEN",
  "IN_PROGRESS",
  "WAITING",
  "VERIFYING",
  "COMPLETED",
];
function PeopleSelect({
  value,
  onChange,
  people,
  required = false,
  label = "Sorumlu",
}: {
  value: string;
  onChange: (v: string) => void;
  people: any[];
  required?: boolean;
  label?: string;
}) {
  return (
    <Field label={label}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
      >
        <option value="">Seçiniz</option>
        {people.map((p) => (
          <option value={p.id} key={p.id}>
            {p.display_name || p.username}
            {p.primary_org?.code ? ` · ${p.primary_org.code}` : ""}
          </option>
        ))}
      </select>
    </Field>
  );
}
function CreateRecord(props: {
  kind: Kind;
  onClose: () => void;
  onCreated: () => void;
}) {
  return props.kind === "work" ? (
    <WorkAssignmentForm onClose={props.onClose} onCreated={props.onCreated} />
  ) : (
    <CreateRecordFields {...props} />
  );
}
function CreateRecordFields({
  kind,
  onClose,
  onCreated,
}: {
  kind: Kind;
  onClose: () => void;
  onCreated: () => void;
}) {
  const { user } = useAuth();
  const people = useResource<any>("/people");
  const pms = useResource<any>(
    kind === "projects" ? "/project-managers" : null,
  );
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("NORMAL");
  const [assignee, setAssignee] = useState(user.id);
  const [pm, setPm] = useState("");
  const [personal, setPersonal] = useState(!user.permissions?.manage_unit);
  const [due, setDue] = useState("");
  const [expected, setExpected] = useState("");
  const [caseKind, setCaseKind] = useState("SECURITY_INCIDENT");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [extras, setExtras] = useState(emptyRecordExtras);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const body: any = { title, description, priority };
      if (kind === "projects") {
        body.pm_id = pm;
        body.expected_outcome = expected;
        if (due) body.due_at = new Date(due).toISOString();
      }
      if (kind === "work") {
        body.assignee_id = personal ? user.id : assignee;
        body.personal = personal;
        body.expected_outcome = expected;
        if (due) body.due_at = new Date(due).toISOString();
      }
      if (kind === "cases") {
        body.coordinator_id = assignee;
        body.kind = caseKind;
      }
      await createRecordWithExtras(`/${kind}`, body, extras);
      onCreated();
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Drawer
      title={config[kind].new}
      subtitle="YENİ KAYIT"
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <form className="stack-form" onSubmit={submit}>
        <div className="info-strip">
          {kind === "projects"
            ? "Taslağınızı oluşturun, ardından proje yöneticisinin onayına gönderin."
            : kind === "cases"
              ? "Vaka resmî olarak açıldığında seçilen SLA saati başlar."
              : "Kişisel işler ve yönetim taahhütleri ayrı kurallarla izlenir."}
        </div>
        <Field label="Başlık">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={240}
            required
            placeholder={
              kind === "projects"
                ? "Örn. Ayrıcalıklı erişim dönüşümü"
                : "İşin açık ve anlaşılır başlığı"
            }
          />
        </Field>
        <Field label={kind === "projects" ? "Amaç ve kapsam" : "Açıklama"}>
          <textarea
            rows={4}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            required
            placeholder="Beklenen etki, mevcut durum ve gerekli bağlam…"
          />
        </Field>
        {kind === "projects" && (
          <PeopleSelect
            label="Proje yöneticisi"
            value={pm}
            onChange={setPm}
            people={list(pms.data).map((x: any) => x.user || x)}
            required
          />
        )}
        {kind === "work" && user.permissions?.manage_unit && (
          <Field label="İş türü">
            <select
              value={personal ? "personal" : "formal"}
              onChange={(e) => setPersonal(e.target.value === "personal")}
            >
              <option value="formal">Yönetim taahhüdü · SLA uygulanır</option>
              <option value="personal">Kişisel iş · Hedef tarih</option>
            </select>
          </Field>
        )}
        {kind !== "projects" && (!personal || kind === "cases") && (
          <PeopleSelect
            label={kind === "cases" ? "Vaka koordinatörü" : "Atanan kişi"}
            value={assignee}
            onChange={setAssignee}
            people={list(people.data)}
            required
          />
        )}
        {kind === "cases" && (
          <Field label="Vaka türü">
            <select
              value={caseKind}
              onChange={(e) => setCaseKind(e.target.value)}
            >
              <option value="SECURITY_INCIDENT">Güvenlik olayı</option>
              <option value="VULNERABILITY">Zafiyet takibi</option>
              <option value="OPERATIONAL">Operasyonel sorun</option>
            </select>
          </Field>
        )}
        <div className="form-grid">
          <Field label={kind === "projects" ? "Öncelik" : "Kritiklik / SLA"}>
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
            >
              <option value="NORMAL">
                Normal
                {kind !== "projects" && !personal ? " · 1 takvim ayı" : ""}
              </option>
              <option value="HIGH">
                Yüksek
                {kind !== "projects" && !personal ? " · 7 takvim günü" : ""}
              </option>
              <option value="CRITICAL">
                Kritik{kind !== "projects" ? " · 24 saat" : ""}
              </option>
            </select>
          </Field>
          {kind !== "cases" && (
            <Field
              label={
                kind === "work"
                  ? "Kişisel hedef / önerilen tarih"
                  : "Önerilen teslim tarihi"
              }
            >
              <input
                type="datetime-local"
                value={due}
                onChange={(e) => setDue(e.target.value)}
                disabled={kind === "work" && !personal}
              />
            </Field>
          )}
        </div>
        {kind !== "cases" && (
          <Field label="Beklenen çıktı">
            <textarea
              rows={3}
              value={expected}
              onChange={(e) => setExpected(e.target.value)}
              placeholder="Tamamlandığında ne teslim edilmiş olacak?"
            />
          </Field>
        )}
        <RecordExtras
          value={extras}
          onChange={setExtras}
          disabled={busy}
          defaultRecipients={
            kind === "projects"
              ? list(pms.data)
                  .map((item: any) => item.user || item)
                  .filter((person: any) => person.id === pm)
              : list(people.data).filter(
                  (person: any) => person.id === assignee,
                )
          }
          emailHint={
            kind === "projects"
              ? "Seçilen kişilere proje başvurusu onaya gönderildiğinde bildirim gönderilir. Taslak kaydı e-posta göndermez."
              : "Vaka açıldığında seçilen, kayıt erişimi olan kişilere kısa bir e-posta bildirimi gönderilir."
          }
        />
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
          <Button disabled={busy} type="submit">
            {busy
              ? "Kaydediliyor…"
              : kind === "projects"
                ? "Taslak oluştur"
                : "Kaydı oluştur"}
            <Plus size={15} />
          </Button>
        </div>
      </form>
    </Drawer>
  );
}
function Detail({
  kind,
  initial,
  onClose,
  onUpdate,
}: {
  kind: Kind;
  initial: RecordItem;
  onClose: () => void;
  onUpdate: () => void;
}) {
  const { user } = useAuth();
  const resource = useResource<any>(
    `/${kind}/${initial.id}${kind === "work" ? "?all_contexts=true" : ""}`,
    initial,
  );
  const row = resource.data || initial;
  const childResource = useResource<any>(
    `/${kind}/${initial.id}/${kind === "projects" ? "tasks" : kind === "cases" ? "actions" : "children"}${kind === "work" ? "?all_contexts=true" : ""}`,
  );
  const childRows = list(childResource.data);
  const people = useResource<any>("/people");
  const [note, setNote] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [progress, setProgress] = useState(row.progress || 0);
  const [assign, setAssign] = useState("");
  const [childTitle, setChildTitle] = useState("");
  const [showChild, setShowChild] = useState(false);
  const [childExtras, setChildExtras] = useState(emptyRecordExtras);
  const [showAssign, setShowAssign] = useState(false);
  const [showResource, setShowResource] = useState(false);
  const [verifyUser, setVerifyUser] = useState("");
  const [showSla, setShowSla] = useState(false);
  const [newDue, setNewDue] = useState("");
  const currentStatus = String(row.status).toUpperCase();
  const isOwner =
    user.id ===
    (row.assigned_to_id ||
      row.owner_id ||
      row.coordinator_id ||
      row.created_by_id);
  const projectManager = !!row.permissions?.manage;
  const unitManager = !!row.permissions?.manage;
  const canAct =
    kind === "projects"
      ? projectManager || row.members?.some((m: any) => m.id === user.id)
      : kind === "cases"
        ? !!row.permissions?.manage ||
          row.members?.some((m: any) => m.id === user.id)
        : !!row.permissions?.update;
  const mutate = async (action: string, body: any = {}) => {
    setBusy(action);
    setError("");
    setSuccess("");
    try {
      const path =
        action === "children" ? "/work" : `/${kind}/${row.id}/${action}`;
      const payload =
        action === "children"
          ? { ...body, parent_id: row.id, personal: false }
          : { version: row.version, ...body };
      if (["children", "tasks", "actions"].includes(action)) {
        await createRecordWithExtras(path, payload, childExtras);
        setChildExtras(emptyRecordExtras());
      } else {
        await api(path, { method: "POST", body: payload });
      }
      resource.refresh();
      childResource.refresh();
      onUpdate();
      setSuccess("Değişiklik kaydedildi.");
      setNote("");
      setNext("");
      setShowAssign(false);
      setShowChild(false);
      setShowResource(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  const close = useCallback(() => onClose(), [onClose]);
  const contributions = list(
    row.contributions || row.activity || row.progress_entries,
  );
  if (resource.error && !resource.data)
    return (
      <Drawer title="Kayda erişilemiyor" onClose={close}>
        <ErrorState message={resource.error} onRetry={resource.refresh} />
      </Drawer>
    );
  return (
    <Drawer
      title={row.title}
      subtitle={`${kind === "projects" ? "PROJE" : kind === "cases" ? "VAKA" : "BİRİM İŞİ"} · ${String(row.id).slice(0, 8).toUpperCase()}`}
      onClose={close}
      wide
    >
      <div className="detail-status-row">
        <Status value={row.status} />
        <Status value={row.priority} />
        <Badge>
          {row.context === "PROJECT_TASK"
            ? "Proje görevi"
            : row.context === "CASE_ACTION"
              ? "Vaka aksiyonu"
              : row.formal === false
                ? "Kişisel iş"
                : kind === "work"
                  ? "Yönetim taahhüdü"
                  : kind === "projects"
                    ? "Proje yönetimi"
                    : "Ortak vaka"}
        </Badge>
      </div>
      {error && <ErrorState message={error} />}{" "}
      {success && (
        <div className="success-state" role="status">
          <Check size={16} />
          {success}
        </div>
      )}
      <p className="detail-description">
        {row.description || row.summary || "Açıklama eklenmemiş."}
      </p>
      <RecordAttachments
        resourceType={
          kind === "projects" ? "project" : kind === "cases" ? "case" : "work"
        }
        resourceId={row.id}
        enabled={row.visibility !== "SUMMARY"}
      />
      <div className="detail-facts">
        <div>
          <span>{kind === "projects" ? "Proje yöneticisi" : "Sorumlu"}</span>
          <strong>
            {personName(
              row.assigned_to ||
                row.pm ||
                row.project_manager ||
                row.coordinator ||
                row.owner ||
                row.owner_name,
            )}
          </strong>
        </div>
        <div>
          <span>{row.sla ? "SLA hedefi" : "Hedef tarih"}</span>
          <strong>
            {date(
              row.sla?.current_due_at ||
                row.sla?.due_at ||
                row.sla_due_at ||
                row.due_at,
              true,
            )}
          </strong>
        </div>
        <div>
          <span>Son güncelleme</span>
          <strong>{date(row.updated_at, true)}</strong>
        </div>
        <div>
          <span>Kayıt sürümü</span>
          <strong>v{row.version ?? 1}</strong>
        </div>
      </div>
      {row.sla && (
        <div
          className={`sla-banner ${row.sla.is_overdue || row.sla.breached_at ? "is-breached" : ""}`}
        >
          <Clock3 size={17} />
          <div>
            <strong>
              {row.sla.is_overdue || row.sla.breached_at
                ? "SLA ihlali var"
                : "SLA takibi etkin"}
            </strong>
            <p>
              {row.sla.policy_name ||
                row.sla.policy?.name ||
                "Yönetim tamamlama hedefi"}{" "}
              · Atama ve bekleme süreyi sıfırlamaz.
            </p>
          </div>
        </div>
      )}
      {row.expected_outcome && (
        <div className="detail-block">
          <h3>Beklenen çıktı</h3>
          <p>{row.expected_outcome}</p>
        </div>
      )}
      {kind === "projects" && (
        <div className="detail-block">
          <div className="progress-heading">
            <h3>Proje yöneticisinin ilerleme beyanı</h3>
            <strong>%{row.progress || 0}</strong>
          </div>
          <div className="progress-track">
            <span style={{ width: `${row.progress || 0}%` }} />
          </div>
          <small className="muted">
            Teslimatların hesaplanan ilerlemesinden ayrı takip edilir.
          </small>
        </div>
      )}
      {kind === "projects" && (
        <ProjectInsights
          project={row}
          onUpdated={() => {
            resource.refresh();
            childResource.refresh();
            onUpdate();
          }}
        />
      )}
      {kind === "projects" &&
        currentStatus === "SUBMITTED" &&
        row.permissions?.approve && (
          <Field label="Karar notu">
            <textarea
              rows={2}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Onay, düzeltme veya ret gerekçesi…"
            />
          </Field>
        )}
      <div className="detail-action-bar">
        {kind === "projects" &&
          ["DRAFT", "REVISION", "REVISION_REQUESTED"].includes(currentStatus) &&
          user.id ===
            (row.created_by_id || row.created_by?.id || row.proposer_id) && (
            <Button disabled={!!busy} onClick={() => mutate("submit")}>
              Onaya gönder
              <ArrowRight size={15} />
            </Button>
          )}
        {kind === "projects" &&
          currentStatus === "SUBMITTED" &&
          row.permissions?.approve && (
            <>
              <Button
                disabled={!!busy}
                onClick={() => mutate("review", { decision: "APPROVE", note })}
              >
                <Check size={15} />
                Onayla ve yayınla
              </Button>
              <Button
                variant="secondary"
                disabled={!!busy}
                onClick={() =>
                  mutate("review", {
                    decision: "REVISION",
                    note:
                      note ||
                      "Proje kapsamını ve beklenen çıktıyı güncelleyin.",
                  })
                }
              >
                Düzeltme iste
              </Button>
            </>
          )}
        {kind === "work" &&
          canAct &&
          !["COMPLETED", "CANCELLED"].includes(currentStatus) && (
            <>
              <select
                aria-label="İş durumunu değiştir"
                value={currentStatus}
                disabled={!!busy}
                onChange={(e) => {
                  const status = e.target.value;
                  if (status === "COMPLETED" && !note) {
                    setError("Tamamlama için aşağıya sonuç açıklaması girin.");
                    return;
                  }
                  void mutate("status", {
                    status,
                    result: note,
                    blocker: note,
                  });
                }}
              >
                {workStatuses.map((s) => (
                  <option key={s} value={s}>
                    {
                      (
                        {
                          OPEN: "Açık",
                          IN_PROGRESS: "Devam ediyor",
                          WAITING: "Beklemede",
                          VERIFYING: "Doğrulama bekliyor",
                          COMPLETED: "Tamamlandı",
                        } as any
                      )[s]
                    }
                  </option>
                ))}
              </select>
            </>
          )}
        {kind === "work" &&
          currentStatus === "VERIFYING" &&
          row.permissions?.accept && (
            <Button
              disabled={!!busy}
              onClick={() =>
                mutate("accept", {
                  result: note || "Sonuç kontrol edilerek kabul edildi.",
                })
              }
            >
              <CheckCheck size={15} />
              Sonucu kabul et
            </Button>
          )}
        {kind === "work" && row.context === "UNIT_WORK" && unitManager && (
          <Button variant="secondary" onClick={() => setShowChild(!showChild)}>
            <GitBranch size={15} />
            Alt iş
          </Button>
        )}
        {kind === "work" && row.context === "UNIT_WORK" && unitManager && (
          <Button
            variant="secondary"
            onClick={() => setShowAssign(!showAssign)}
          >
            <UserRound size={15} />
            Ata
          </Button>
        )}
        {kind === "work" &&
          row.context === "UNIT_WORK" &&
          row.formal === false &&
          unitManager && (
            <Button
              variant="secondary"
              disabled={!!busy}
              onClick={() =>
                mutate("adopt", { priority: row.priority || "NORMAL" })
              }
            >
              Resmî takibe al
            </Button>
          )}
        {kind === "work" &&
          row.context === "UNIT_WORK" &&
          row.sla &&
          unitManager && (
            <Button variant="secondary" onClick={() => setShowSla(!showSla)}>
              <Clock3 size={15} />
              Termin istisnası
            </Button>
          )}
        {kind === "cases" &&
          row.permissions?.manage &&
          !["CLOSED", "VERIFYING"].includes(currentStatus) && (
            <Button
              disabled={!!busy}
              onClick={() =>
                mutate("request-close", {
                  summary: note,
                  evidence: next || note,
                })
              }
            >
              Kapanış iste
              <CheckCheck size={15} />
            </Button>
          )}
        {kind === "cases" &&
          currentStatus === "VERIFYING" &&
          row.permissions?.verify && (
            <Button
              disabled={!!busy}
              onClick={() => mutate("verify-close", { evidence: note })}
            >
              Kapanışı doğrula
              <Check size={15} />
            </Button>
          )}
        {kind === "projects" &&
          projectManager &&
          ["PLANNED", "IN_PROGRESS", "WAITING"].includes(currentStatus) && (
            <Button
              variant="secondary"
              disabled={!!busy}
              onClick={() => mutate("close", { summary: note })}
            >
              Projeyi kapat
            </Button>
          )}
        {kind !== "work" &&
          row.permissions?.manage &&
          !["DRAFT", "REVISION", "SUBMITTED", "COMPLETED", "CLOSED"].includes(
            currentStatus,
          ) && (
            <>
              <Button
                variant="secondary"
                onClick={() => setShowChild(!showChild)}
              >
                <Plus size={15} />
                {kind === "projects" ? "Proje görevi" : "Vaka aksiyonu"}
              </Button>
              <Button
                variant="secondary"
                onClick={() => setShowResource(!showResource)}
              >
                <Users size={15} />
                Personel talep et
              </Button>
            </>
          )}
      </div>
      {showResource && (
        <div className="inline-form">
          <PeopleSelect
            label="Talep edilen kişi"
            value={assign}
            onChange={setAssign}
            people={list(people.data)}
          />
          <p className="muted">
            Kaynak yöneticisinin kabulü sonrası kişi projeye/vakaya katılır.
            Talep gerekçesini aşağıdaki sonuç alanına ekleyin.
          </p>
          <Button
            disabled={!assign || !note || !!busy}
            onClick={() =>
              mutate("members", { user_id: assign, summary: note })
            }
          >
            Personel talebini gönder
          </Button>
        </div>
      )}
      {showAssign && (
        <div className="inline-form">
          <PeopleSelect
            people={list(people.data)}
            value={assign}
            onChange={setAssign}
          />
          <Button
            disabled={!assign || !!busy}
            onClick={() => mutate("assign", { assignee_id: assign })}
          >
            Atamayı kaydet
          </Button>
        </div>
      )}
      {showChild && (
        <div className="inline-form">
          <Field label="Alt iş başlığı">
            <input
              value={childTitle}
              onChange={(e) => setChildTitle(e.target.value)}
            />
          </Field>
          <PeopleSelect
            people={list(people.data)}
            value={assign}
            onChange={setAssign}
          />
          <RecordExtras
            value={childExtras}
            onChange={setChildExtras}
            defaultRecipients={list(people.data).filter(
              (person: any) => person.id === assign,
            )}
            disabled={!!busy}
            emailHint="Atanan kişiye gerekli atama bildirimi gönderilir. Bu alan, kayıt erişimi olan seçili kişilere ek bildirim göndermenizi sağlar."
          />
          <Button
            disabled={!assign || !childTitle || !!busy}
            onClick={() =>
              mutate(
                kind === "projects"
                  ? "tasks"
                  : kind === "cases"
                    ? "actions"
                    : "children",
                {
                  title: childTitle,
                  description: note || row.expected_outcome || row.title,
                  assignee_id: assign,
                  priority: row.priority,
                  expected_outcome: note,
                },
              )
            }
          >
            Alt iş oluştur
          </Button>
        </div>
      )}
      {showSla && (
        <div className="inline-form">
          <Field label="Önerilen yeni termin">
            <input
              type="datetime-local"
              value={newDue}
              onChange={(e) => setNewDue(e.target.value)}
            />
          </Field>
          <p className="muted">
            Gerekçeyi aşağıya girin. Önceki termin ve ihlal geçmişi korunur.
          </p>
          <Button
            disabled={!newDue || !note || !!busy}
            onClick={() =>
              mutate("sla-adjust", {
                due_at: new Date(newDue).toISOString(),
                reason: note,
              })
            }
          >
            İstisna talep et
          </Button>
        </div>
      )}
      {childRows.length > 0 && (
        <div className="detail-block">
          <h3>
            {kind === "projects"
              ? "Proje görevleri"
              : kind === "cases"
                ? "Ekip aksiyonları"
                : "Alt işler"}
          </h3>
          {childRows.map((t: any) => (
            <div className="subtask-row" key={t.id}>
              <div>
                <Link className="text-button" to={`/work?id=${t.id}`}>
                  {t.title}
                  <ArrowRight size={12} />
                </Link>
                <small>
                  {personName(t.assigned_to || t.owner || t.assignee)}
                </small>
              </div>
              <Status value={t.status} />
            </div>
          ))}
        </div>
      )}
      {canAct &&
        (kind !== "projects" ||
          ["PLANNED", "IN_PROGRESS", "WAITING"].includes(currentStatus)) && (
          <div className="detail-block contribution-form">
            <h3>
              {kind === "projects"
                ? "İlerleme güncelle"
                : "Yapılanlar ve sonraki adım"}
            </h3>
            {kind === "projects" && projectManager && (
              <Field label={`Tamamlanma oranı · %${progress}`}>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="5"
                  value={progress}
                  onChange={(e) => setProgress(Number(e.target.value))}
                />
              </Field>
            )}
            <Field label="Yapılanlar / Sonuç">
              <textarea
                rows={3}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Bu konuda ne yapıldı? Karar veya kapanış gerekçesi…"
              />
            </Field>
            <Field
              label={
                kind === "cases"
                  ? "Sonraki adım / Kapanış kanıtı"
                  : "Sonraki adım"
              }
            >
              <input
                value={next}
                onChange={(e) => setNext(e.target.value)}
                placeholder="Bir sonraki somut adım nedir?"
              />
            </Field>
            {kind === "cases" && (
              <p className="muted small-text">
                Kapanış, isteği yapan kişiden farklı bir yetkili yönetici
                tarafından doğrulanır. Kanıt bağlantısını sonraki adım alanına
                ekleyebilirsiniz.
              </p>
            )}
            <Button
              variant="secondary"
              disabled={!note || !!busy}
              onClick={() =>
                mutate("progress", {
                  done: note,
                  next_step: next,
                  ...(kind === "projects" && projectManager
                    ? { progress }
                    : {}),
                })
              }
            >
              <MessageSquare size={15} />
              Güncellemeyi kaydet
            </Button>
          </div>
        )}
      {kind === "projects" &&
        (row.permissions?.edit || row.permissions?.manage) && (
          <ProjectGovernance
            row={row}
            onUpdate={() => {
              resource.refresh();
              onUpdate();
            }}
          />
        )}
      <div className="detail-block">
        <h3>Katkı geçmişi</h3>
        {contributions.length ? (
          <div className="timeline">
            {contributions.map((c: any) => (
              <div className="timeline-item" key={c.id}>
                <i />
                <div>
                  <strong>
                    {c.actor_name ||
                      c.author_name ||
                      personName(c.actor || c.author)}
                  </strong>
                  <small>{date(c.created_at, true)}</small>
                  <p>{c.done || c.description || c.message}</p>
                  {c.next_step && (
                    <p className="muted">Sonraki adım: {c.next_step}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">Henüz katkı kaydı bulunmuyor.</p>
        )}
      </div>
    </Drawer>
  );
}
export default function Records({ kind }: { kind: Kind }) {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState(params.get("filter") || "all");
  const [create, setCreate] = useState(false);
  const [selected, setSelected] = useState<RecordItem | null>(null);
  const [mutationError, setMutationError] = useState("");
  const [showRequests, setShowRequests] = useState(
    params.get("requests") === "1",
  );
  useEffect(() => {
    setShowRequests(params.get("requests") === "1");
  }, [params]);
  const closeRequests = () => {
    setShowRequests(false);
    setParams((current) => {
      const next = new URLSearchParams(current);
      next.delete("requests");
      next.delete("request_id");
      return next;
    });
  };
  const [showNotices, setShowNotices] = useState(params.get("notices") === "1");
  useEffect(() => {
    setShowNotices(params.get("notices") === "1");
  }, [params]);
  const closeNotices = () => {
    setShowNotices(false);
    setParams((current) => {
      const next = new URLSearchParams(current);
      next.delete("notices");
      next.delete("notice_id");
      return next;
    });
  };
  const notices = useResource<any>(kind === "cases" ? "/case-notices" : null);
  const pendingNotices = list(notices.data).filter(
    (x: any) => x.status === "PENDING",
  ).length;
  const requests = useResource<any>("/participation-requests");
  const requestCount = list(requests.data).filter(
    (x: any) => x.status === "PENDING",
  ).length;
  const r = useResource<any>(
    `/${kind}${kind === "work" && filter === "mine" ? "?mine=true&all_contexts=true" : ""}`,
  );
  const selections = useResource<any>("/report-selections");
  const selectedIds = new Set(
    list(selections.data).map((s: any) => s.source_id),
  );
  const rows = list<RecordItem>(r.data).map((row): RecordItem => ({
    ...row,
    report_candidate: selectedIds.has(row.id),
  }));
  const selectedResource = useResource<RecordItem>(
    params.get("id")
      ? `/${kind}/${params.get("id")}${kind === "work" ? "?all_contexts=true" : ""}`
      : null,
  );
  useEffect(() => {
    if (selectedResource.data && params.get("id"))
      setSelected(selectedResource.data);
  }, [selectedResource.data, params]);
  const cfg = config[kind];
  useEffect(() => {
    const id = params.get("id");
    if (id && rows.length) {
      const item = rows.find((p) => p.id === id);
      if (item) setSelected(item);
    }
  }, [params, r.data]);
  const visible = rows.filter((row) => {
    const status = String(row.status).toUpperCase();
    const match =
      !query ||
      `${row.title} ${row.description || ""} ${row.assigned_to?.display_name || row.owner_name || ""}`
        .toLocaleLowerCase("tr-TR")
        .includes(query.toLocaleLowerCase("tr-TR"));
    return (
      match &&
      (filter === "all" ||
        (filter === "mine" &&
          (row.assigned_to_id === user.id ||
            row.pm_id === user.id ||
            row.pm?.id === user.id ||
            row.coordinator_id === user.id ||
            row.coordinator?.id === user.id ||
            row.created_by_id === user.id)) ||
        (filter === "pending" &&
          ["DRAFT", "SUBMITTED", "VERIFYING"].includes(status)) ||
        (filter === "overdue" &&
          new Date(
            row.sla?.current_due_at || row.sla_due_at || row.due_at || "9999",
          ).getTime() < Date.now() &&
          !["COMPLETED", "CLOSED", "CANCELLED"].includes(status)) ||
        (filter === "active" &&
          !["COMPLETED", "CLOSED", "CANCELLED", "REJECTED"].includes(status)))
    );
  });
  const canCreate = kind !== "cases" || user.permissions?.create_case;
  return (
    <>
      <PageHeader
        eyebrow={cfg.eyebrow}
        title={cfg.title}
        description={cfg.description}
        actions={
          canCreate ? (
            <Button onClick={() => setCreate(true)}>
              <Plus size={17} />
              {cfg.new}
            </Button>
          ) : (
            <Button variant="secondary" onClick={() => setCreate(true)}>
              <Plus size={17} />
              Vaka bildirimi
            </Button>
          )
        }
      />
      {(user.permissions?.manage_unit || user.permissions?.manage_projects) &&
        requestCount > 0 && (
          <div className="requests-banner">
            <Users size={17} />
            <span>
              <strong>{requestCount} personel talebi</strong> değerlendirme veya
              kaynak yöneticisi kararı bekliyor.
            </span>
            <Button variant="secondary" onClick={() => setShowRequests(true)}>
              Talepleri aç
              <ArrowRight size={14} />
            </Button>
          </div>
        )}
      {kind === "cases" && pendingNotices > 0 && (
        <div className="requests-banner">
          <ShieldAlert size={17} />
          <span>
            <strong>{pendingNotices} vaka bildirimi</strong> resmî değerlendirme
            bekliyor.
          </span>
          <Button variant="secondary" onClick={() => setShowNotices(true)}>
            Bildirimleri aç
            <ArrowRight size={14} />
          </Button>
        </div>
      )}
      {selectedResource.error && (
        <ErrorState message={selectedResource.error} />
      )}
      <div className="overview-strip">
        <div>
          <cfg.icon size={17} />
          <strong>{rows.length}</strong>
          <span>toplam kayıt</span>
        </div>
        <div>
          <span className="tiny-dot warning" />
          <strong>
            {
              rows.filter((x) =>
                ["CRITICAL", "HIGH"].includes(x.priority || ""),
              ).length
            }
          </strong>
          <span>öncelikli</span>
        </div>
        <div>
          <span className="tiny-dot success" />
          <strong>
            {
              rows.filter((x) => ["COMPLETED", "CLOSED"].includes(x.status))
                .length
            }
          </strong>
          <span>tamamlanan</span>
        </div>
        <span className="strip-note">
          {kind === "projects"
            ? "Projeler, proje yöneticisinin yönetimindedir."
            : kind === "work"
              ? "Atama, birim ve ekip yetkileriniz kapsamındadır."
              : "Kapanış, bağımsız doğrulama ile tamamlanır."}
        </span>
      </div>
      <Card>
        <div className="list-toolbar">
          <div className="segmented">
            {[
              ["all", "Tümü"],
              ["mine", "Bana ait"],
              ["active", "Açık kayıtlar"],
              [
                kind === "projects" ? "pending" : "overdue",
                kind === "projects" ? "Onay bekleyen" : "Gecikenler",
              ],
            ].map(([value, label]) => (
              <button
                key={value}
                className={filter === value ? "active" : ""}
                onClick={() => setFilter(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="table-search">
            <Search size={15} />
            <input
              placeholder={
                kind === "projects"
                  ? "Proje ara…"
                  : kind === "cases"
                    ? "Vaka ara…"
                    : "İş, sorumlu veya açıklama ara…"
              }
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Kayıtlarda ara"
            />
          </div>
        </div>
        {mutationError && <ErrorState message={mutationError} />}{" "}
        {r.error && <ErrorState message={r.error} onRetry={r.refresh} />}{" "}
        {r.loading && !r.data ? (
          <Loading />
        ) : visible.length ? (
          <div className="table-scroll">
            <table className="records-table">
              <thead>
                <tr>
                  <th className="star-cell">
                    <Star size={13} />
                  </th>
                  <th>
                    {kind === "projects"
                      ? "PROJE"
                      : kind === "cases"
                        ? "VAKA"
                        : "İŞ / TAAHHÜT"}
                  </th>
                  <th>DURUM</th>
                  <th>ÖNCELİK</th>
                  <th>
                    {kind === "projects" ? "PROJE YÖNETİCİSİ" : "SORUMLU"}
                  </th>
                  <th>{kind === "projects" ? "İLERLEME" : "TERMİN / SLA"}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visible.map((row) => (
                  <tr key={row.id}>
                    <td className="star-cell">
                      <button
                        className={`icon-button star-button ${row.report_candidate ? "is-starred" : ""}`}
                        aria-label={
                          row.report_candidate
                            ? "Rapordan çıkar"
                            : "Haftalık rapora ekle"
                        }
                        aria-pressed={!!row.report_candidate}
                        onClick={async () => {
                          setMutationError("");
                          try {
                            await api("/report-selections", {
                              method: "POST",
                              body: {
                                source_type:
                                  kind === "projects"
                                    ? "project"
                                    : kind === "cases"
                                      ? "case"
                                      : "work",
                                source_id: row.id,
                                selected: !row.report_candidate,
                              },
                            });
                            selections.refresh();
                            r.refresh();
                          } catch (e) {
                            setMutationError((e as Error).message);
                          }
                        }}
                      >
                        <Star
                          size={16}
                          fill={row.report_candidate ? "currentColor" : "none"}
                        />
                      </button>
                    </td>
                    <td>
                      <button
                        className="record-title"
                        onClick={() => {
                          setSelected(row);
                          setParams({ id: row.id });
                        }}
                      >
                        <strong>{row.title}</strong>
                        <small>
                          {kind === "work"
                            ? row.context === "PROJECT_TASK"
                              ? "Proje görevi"
                              : row.context === "CASE_ACTION"
                                ? "Vaka aksiyonu"
                                : row.formal === false
                                  ? "Kişisel iş"
                                  : "Birim taahhüdü"
                            : row.requesting_org?.name ||
                              row.owner_org?.name ||
                              (
                                {
                                  SECURITY_INCIDENT: "Güvenlik olayı",
                                  VULNERABILITY: "Zafiyet takibi",
                                  OPERATIONAL: "Operasyonel sorun",
                                  TASK: "İş",
                                  COMMITMENT: "Taahhüt",
                                } as Record<string, string>
                              )[row.kind] ||
                              String(row.id).slice(0, 8)}
                        </small>
                      </button>
                    </td>
                    <td>
                      <Status value={row.status} />
                    </td>
                    <td>
                      <Status value={row.priority} />
                    </td>
                    <td>
                      <span className="person-inline">
                        <span className="avatar-sm">
                          {personName(
                            row.assigned_to ||
                              row.pm ||
                              row.project_manager ||
                              row.coordinator ||
                              row.owner_name,
                          )
                            .slice(0, 2)
                            .toLocaleUpperCase("tr-TR")}
                        </span>
                        {personName(
                          row.assigned_to ||
                            row.pm ||
                            row.project_manager ||
                            row.coordinator ||
                            row.owner_name,
                        )}
                      </span>
                    </td>
                    <td>
                      {kind === "projects" ? (
                        <div className="mini-progress">
                          <span style={{ width: `${row.progress || 0}%` }} />
                          <small>%{row.progress || 0}</small>
                        </div>
                      ) : (
                        <span
                          className={`date-cell ${new Date(row.sla?.current_due_at || row.sla_due_at || row.due_at || "9999").getTime() < Date.now() ? "overdue" : ""}`}
                        >
                          <Clock3 size={13} />
                          {date(
                            row.sla?.current_due_at ||
                              row.sla_due_at ||
                              row.due_at,
                          )}
                        </span>
                      )}
                    </td>
                    <td>
                      <button
                        className="icon-button"
                        aria-label={`${row.title} ayrıntısını aç`}
                        onClick={() => {
                          setSelected(row);
                          setParams({ id: row.id });
                        }}
                      >
                        <ArrowRight size={17} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title={query ? "Aramanızla eşleşen kayıt yok" : cfg.empty}
            description="Filtreleri değiştirin veya yeni bir kayıt oluşturun."
            icon={<cfg.icon size={30} />}
          />
        )}
        <div className="table-footer">
          <span>{visible.length} kayıt gösteriliyor</span>
          <span>Yetkiniz kapsamındaki kayıtlar · 20 sn yenileme</span>
        </div>
      </Card>
      <div className="context-note">
        <ShieldAlert size={15} />
        {kind === "projects"
          ? "Proje onayı ile personel tahsisi ayrı işlemlerdir. Birim yöneticisi rolü proje yönetim yetkisi sağlamaz."
          : kind === "work"
            ? "Üst taahhüdün sorumluluğu korunur. Alt iş açılması veya yeniden atama SLA saatini sıfırlamaz."
            : "Vaka SLA’sı iç koordinasyon hedefidir. Acil müdahale için mevcut olay müdahale kanalını kullanın."}
      </div>
      {showNotices && (
        <CaseNoticeReview
          focusedId={params.get("notice_id")}
          onClose={closeNotices}
          onUpdate={() => {
            notices.refresh();
            r.refresh();
          }}
        />
      )}
      {showRequests && (
        <ParticipationRequests
          focusedId={params.get("request_id")}
          onClose={closeRequests}
          onUpdate={requests.refresh}
        />
      )}
      {create && (canCreate || kind !== "cases") && (
        <CreateRecord
          kind={kind}
          onClose={() => setCreate(false)}
          onCreated={r.refresh}
        />
      )}{" "}
      {create && !canCreate && kind === "cases" && (
        <CaseNotice onClose={() => setCreate(false)} onCreated={r.refresh} />
      )}{" "}
      {selected && (
        <Detail
          kind={kind}
          initial={selected}
          onClose={() => {
            setSelected(null);
            setParams({});
          }}
          onUpdate={r.refresh}
        />
      )}
    </>
  );
}
function CaseNotice({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [extras, setExtras] = useState(emptyRecordExtras);
  return (
    <Drawer
      title="Vaka bildirimi"
      subtitle="YÖNETİCİYE İLET"
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <form
        className="stack-form"
        onSubmit={async (e) => {
          e.preventDefault();
          if (busy) return;
          setBusy(true);
          setError("");
          try {
            await createRecordWithExtras(
              "/case-notices",
              { title, description },
              extras,
            );
            onCreated();
            onClose();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="info-strip">
          Bildirim yöneticinize iletilir. Resmî vaka ve SLA henüz başlamaz. Acil
          olayda mevcut müdahale kanalını hemen kullanın.
        </div>
        <Field label="Konu">
          <input
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        <Field label="Açıklama">
          <textarea
            required
            rows={5}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <RecordExtras
          value={extras}
          onChange={setExtras}
          disabled={busy}
          emailHint="Bildirime erişim yetkisi olan kişilere isteğe bağlı kısa bir e-posta gönderilir. Bu işlem resmî vaka veya görev ataması oluşturmaz."
        />
        {error && <ErrorState message={error} />}
        <Button disabled={busy}>
          Bildirimi gönder
          <ArrowRight size={15} />
        </Button>
      </form>
    </Drawer>
  );
}

function ParticipationRequests({
  focusedId,
  onClose,
  onUpdate,
}: {
  focusedId?: string | null;
  onClose: () => void;
  onUpdate: () => void;
}) {
  const { user } = useAuth();
  const r = useResource<any>(
    focusedId
      ? `/participation-requests/${encodeURIComponent(focusedId)}`
      : "/participation-requests",
  );
  const records = focusedId
    ? r.data?.id === focusedId
      ? [r.data]
      : []
    : list(r.data);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [reason, setReason] = useState("");
  async function decide(row: any, decision: string) {
    setBusy(row.id);
    setError("");
    try {
      await api(`/participation-requests/${row.id}/decide`, {
        method: "POST",
        body: { version: row.version, decision, note: reason },
      });
      r.refresh();
      onUpdate();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  return (
    <Drawer
      title="Personel tahsisi talepleri"
      subtitle="KAYNAK YÖNETİMİ"
      onClose={onClose}
      wide
    >
      <div className="info-strip">
        Personel tahsisini kabul etmek proje yönetimi veya yayın onayı yetkisi
        vermez.
      </div>
      {error && <ErrorState message={error} />}
      {r.error && <ErrorState message={r.error} onRetry={r.refresh} />}
      <Field label="Karar notu">
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="İsteğe bağlı gerekçe…"
        />
      </Field>
      {r.loading ? (
        <Loading />
      ) : records.length ? (
        records.map((x: any) => (
          <div className="allocation-request" key={x.id}>
            <div className="detail-status-row">
              <Status value={x.status} />
              <Badge>{x.project_id ? "Proje" : "Vaka"}</Badge>
            </div>
            <strong>{personName(x.user)}</strong>
            <p>{x.summary}</p>
            <small>{x.target_org_name}</small>
            {x.status === "PENDING" && user.permissions?.manage_unit && (
              <div className="detail-action-bar">
                <Button disabled={!!busy} onClick={() => decide(x, "ACCEPT")}>
                  Tahsisi kabul et
                  <Check size={14} />
                </Button>
                <Button
                  variant="secondary"
                  disabled={!!busy}
                  onClick={() => decide(x, "REJECT")}
                >
                  Reddet
                </Button>
              </div>
            )}
          </div>
        ))
      ) : (
        <EmptyState title="Personel talebi bulunmuyor" />
      )}
    </Drawer>
  );
}

function ProjectGovernance({
  row,
  onUpdate,
}: {
  row: any;
  onUpdate: () => void;
}) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState("edit");
  const [title, setTitle] = useState(row.title);
  const [description, setDescription] = useState(row.description || "");
  const [expected, setExpected] = useState(row.expected_outcome || "");
  const [reason, setReason] = useState("");
  const [selectedPerson, setSelectedPerson] = useState("");
  const [expiry, setExpiry] = useState("");
  const [permission, setPermission] = useState("read");
  const [appointment, setAppointment] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const people = useResource<any>(open ? "/people" : null);
  const grants = useResource<any>(
    open && row.permissions?.manage ? `/projects/${row.id}/authorities` : null,
  );
  const pms = useResource<any>(
    open && mode === "transfer" ? "/project-managers" : null,
  );
  const revisions = useResource<any>(
    open ? `/projects/${row.id}/revisions` : null,
  );
  const draft = ["DRAFT", "REVISION"].includes(row.status);
  async function action(path: string, body: any, method = "POST") {
    setBusy(true);
    setError("");
    try {
      await api(`/projects/${row.id}${path}`, {
        method,
        body: { version: row.version, ...body },
      });
      onUpdate();
      grants.refresh();
      revisions.refresh();
      setReason("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="detail-block">
      <button className="text-button" onClick={() => setOpen(!open)}>
        <ShieldAlert size={14} />
        {draft
          ? "Taslağı düzenle ve sürümleri gör"
          : "Proje yetkileri ve önemli değişiklikler"}
        <ChevronDown size={14} />
      </button>
      {open && (
        <div className="governance-panel">
          <div className="segmented">
            {draft && (
              <button
                className={mode === "edit" ? "active" : ""}
                onClick={() => setMode("edit")}
              >
                Taslak
              </button>
            )}
            {!draft && (
              <button
                className={mode === "edit" ? "active" : ""}
                onClick={() => setMode("edit")}
              >
                Kapsam değişikliği
              </button>
            )}
            {row.permissions?.manage && (
              <button
                className={mode === "authority" ? "active" : ""}
                onClick={() => setMode("authority")}
              >
                Yetki devri
              </button>
            )}
            {(user.permissions?.director ||
              user.roles?.some((r) => r.role === "UNIT_HEAD")) && (
              <button
                className={mode === "transfer" ? "active" : ""}
                onClick={() => setMode("transfer")}
              >
                Yönetici devri
              </button>
            )}
            <button
              className={mode === "revisions" ? "active" : ""}
              onClick={() => setMode("revisions")}
            >
              Sürümler
            </button>
          </div>
          {error && <ErrorState message={error} />}{" "}
          {mode === "edit" && (
            <>
              <Field label="Proje başlığı">
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </Field>
              <Field label="Amaç ve kapsam">
                <textarea
                  rows={4}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </Field>
              <Field label="Beklenen çıktı">
                <textarea
                  rows={2}
                  value={expected}
                  onChange={(e) => setExpected(e.target.value)}
                />
              </Field>
              {!draft && (
                <Field label="Önemli değişiklik gerekçesi">
                  <textarea
                    rows={2}
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </Field>
              )}
              <Button
                disabled={busy || !title || !description || (!draft && !reason)}
                onClick={() =>
                  action(
                    draft ? "" : "/propose-change",
                    {
                      title,
                      description,
                      expected_outcome: expected,
                      ...(!draft ? { reason } : {}),
                    },
                    draft ? "PATCH" : "POST",
                  )
                }
              >
                {draft ? "Taslağı kaydet" : "Değişikliği onaya gönder"}
              </Button>
              {!draft && (
                <p className="muted small-text">
                  Mevcut yayınlı sürüm, değişiklik onaylanana kadar korunur.
                </p>
              )}
            </>
          )}
          {mode === "authority" && (
            <>
              <PeopleSelect
                label="Yetki verilecek kişi"
                value={selectedPerson}
                onChange={setSelectedPerson}
                people={list(people.data).filter((p: any) => p.id !== user.id)}
              />
              <Field label="İşlem yetkisi">
                <select
                  value={permission}
                  onChange={(e) => setPermission(e.target.value)}
                >
                  <option value="read">Görüntüleme</option>
                  <option value="approve">Proje onayı</option>
                  <option value="tasks">Görev yönetimi</option>
                  <option value="close">Kapanış</option>
                  <option value="manage">Proje yönetimi</option>
                </select>
              </Field>
              <Field label="Yetki bitişi">
                <input
                  type="datetime-local"
                  value={expiry}
                  onChange={(e) => setExpiry(e.target.value)}
                />
              </Field>
              <Field label="Gerekçe">
                <input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </Field>
              <Button
                disabled={busy || !selectedPerson || !expiry || !reason}
                onClick={() =>
                  action("/authorities", {
                    user_id: selectedPerson,
                    permissions: [permission],
                    expires_at: new Date(expiry).toISOString(),
                    reason,
                  })
                }
              >
                Süreli yetki ver
              </Button>
              {list(grants.data).map((g: any) => (
                <div className="governance-grant" key={g.id}>
                  <span>
                    {personName(g.user)}
                    <small>
                      {g.permissions
                        .map(
                          (permission: string) =>
                            (
                              ({
                                read: "Görüntüleme",
                                approve: "Proje onayı",
                                tasks: "Görev yönetimi",
                                close: "Kapanış",
                                manage: "Proje yönetimi",
                              }) as Record<string, string>
                            )[permission] || "Proje yetkisi",
                        )
                        .join(", ")}{" "}
                      · {date(g.expires_at, true)}
                    </small>
                  </span>
                  <Badge tone={g.active ? "success" : "neutral"}>
                    {g.active ? "Etkin" : "İptal"}
                  </Badge>
                  {g.active && (
                    <button
                      className="text-button"
                      disabled={busy || !reason}
                      onClick={() =>
                        action("/authority-revoke", { grant_id: g.id, reason })
                      }
                    >
                      İptal et
                    </button>
                  )}
                </div>
              ))}
            </>
          )}
          {mode === "transfer" && (
            <>
              <Field label="Yeni proje yöneticisi">
                <select
                  value={appointment}
                  onChange={(e) => setAppointment(e.target.value)}
                >
                  <option value="">Seçiniz</option>
                  {list(pms.data)
                    .filter((p: any) => p.id !== row.appointment_id)
                    .map((p: any) => (
                      <option key={p.id} value={p.id}>
                        {personName(p.user)} · {p.governing_org_name}
                      </option>
                    ))}
                </select>
              </Field>
              <Field label="Devir gerekçesi">
                <textarea
                  rows={2}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </Field>
              <div className="info-strip">
                Proje yöneticisi değiştiğinde mevcut yetki devirleri iptal
                edilir. Yeni proje yöneticisi ve bağlı yönetim birimiyle
                yetkiler tekrar değerlendirilir.
              </div>
              <Button
                disabled={busy || !appointment || !reason}
                onClick={() =>
                  action("/transfer", { appointment_id: appointment, reason })
                }
              >
                Proje yönetimini devret
              </Button>
            </>
          )}
          {mode === "revisions" &&
            (revisions.loading ? (
              <Loading />
            ) : (
              list(revisions.data).map((v: any) => (
                <div key={v.id} className="allocation-request">
                  <div className="detail-status-row">
                    <Badge>Sürüm {v.number}</Badge>
                    <Status
                      value={
                        v.decision === "APPROVE"
                          ? "APPROVED"
                          : v.decision === "REJECT"
                            ? "REJECTED"
                            : v.decision
                      }
                    />
                  </div>
                  <strong>{v.content.title}</strong>
                  <p>{v.content.description}</p>
                  <small>
                    {v.content.change_reason ||
                      v.decision_note ||
                      date(v.created_at, true)}
                  </small>
                </div>
              ))
            ))}
        </div>
      )}
    </div>
  );
}

function CaseNoticeReview({
  focusedId,
  onClose,
  onUpdate,
}: {
  focusedId?: string | null;
  onClose: () => void;
  onUpdate: () => void;
}) {
  const { user } = useAuth();
  const r = useResource<any>(
    focusedId
      ? `/case-notices/${encodeURIComponent(focusedId)}`
      : "/case-notices",
  );
  const records = focusedId
    ? r.data?.id === focusedId
      ? [r.data]
      : []
    : list(r.data);
  const [priority, setPriority] = useState("HIGH");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function action(row: any, action: string) {
    setBusy(true);
    setError("");
    try {
      await api(`/case-notices/${row.id}/${action}`, {
        method: "POST",
        body: { version: row.version, priority, reason },
      });
      r.refresh();
      onUpdate();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Drawer
      title="Vaka bildirimleri"
      subtitle="DEĞERLENDİRME KUYRUĞU"
      onClose={onClose}
      wide
    >
      <div className="info-strip">
        Bildirim resmî vakaya dönüştürüldüğünde vaka SLA’sı başlar. Acil
        müdahale bu onayı beklemez.
      </div>
      {error && <ErrorState message={error} />}
      {r.error && <ErrorState message={r.error} onRetry={r.refresh} />}
      <Field label="Resmî vaka kritiklik seviyesi">
        <select value={priority} onChange={(e) => setPriority(e.target.value)}>
          <option value="CRITICAL">Kritik · 24 saat</option>
          <option value="HIGH">Yüksek · 7 gün</option>
          <option value="NORMAL">Normal · 1 ay</option>
        </select>
      </Field>
      <Field label="Değerlendirme gerekçesi">
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Bildirimi reddediyorsanız gerekçe girin"
        />
      </Field>
      {r.loading ? (
        <Loading />
      ) : (
        records.map((x: any) => (
          <div className="allocation-request" key={x.id}>
            <Status value={x.status} />
            <h3>{x.title}</h3>
            <p>{x.description}</p>
            <RecordAttachments resourceType="case_notice" resourceId={x.id} />
            <small>{date(x.created_at, true)}</small>
            {x.status === "PENDING" && user.permissions?.create_case && (
              <div className="detail-action-bar">
                <Button disabled={busy} onClick={() => action(x, "convert")}>
                  Resmî vaka aç
                  <ArrowRight size={14} />
                </Button>
                <Button
                  variant="secondary"
                  disabled={busy || !reason}
                  onClick={() => action(x, "dismiss")}
                >
                  Gerekçeli reddet
                </Button>
              </div>
            )}
          </div>
        ))
      )}
    </Drawer>
  );
}
