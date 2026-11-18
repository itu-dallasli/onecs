import {
  Fragment,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  Activity,
  BookOpen,
  Check,
  ChevronRight,
  CircleAlert,
  Clock3,
  Code2,
  Cpu,
  ExternalLink,
  FileText,
  GitBranch,
  KeyRound,
  Loader2,
  Mail,
  Network,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import { api, list, useResource } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Drawer, Loading } from "../components/ui";
import LDAPLoginMappings from "./LDAPLoginMappings";
import "../styles/settings.css";

type Row = Record<string, any>;
type Section =
  | "general"
  | "users"
  | "organization"
  | "sla"
  | "ai"
  | "integrations"
  | "api"
  | "logs"
  | "jobs"
  | "testing";
type Configuration = {
  section: string;
  version: number;
  config: Row;
  secret_fields?: string[];
  configured?: boolean;
  ready?: boolean;
  latest_test?: Row | null;
};
type FormField = {
  key: string;
  label: string;
  hint?: string;
  type?:
    "text" | "number" | "password" | "checkbox" | "email" | "url" | "select";
  options?: { value: string; label: string }[];
  defaultValue?: string | number | boolean;
  secret?: boolean;
  required?: boolean;
  group?: string;
};
const tabs: { id: Section; label: string; icon: typeof Users }[] = [
  { id: "general", label: "Genel", icon: Settings2 },
  { id: "users", label: "Kullanıcı yönetimi", icon: Users },
  { id: "organization", label: "Organizasyon ve roller", icon: GitBranch },
  { id: "sla", label: "SLA politikaları", icon: Clock3 },
  { id: "ai", label: "Yapay zekâ", icon: Cpu },
  { id: "integrations", label: "Entegrasyonlar", icon: Network },
  { id: "api", label: "API erişimi", icon: Code2 },
  { id: "logs", label: "Günlükler", icon: FileText },
  { id: "jobs", label: "İş kuyruğu", icon: Activity },
  { id: "testing", label: "Test ortamı", icon: ShieldCheck },
];
const roleLabels: Record<string, string> = {
  SYSTEM_ADMIN: "Sistem yöneticisi",
  DIRECTOR: "Direktör",
  UNIT_HEAD: "Birim yöneticisi",
  TEAM_MANAGER: "Ekip yöneticisi",
  PROJECT_MANAGER: "Proje yöneticisi",
  EMPLOYEE: "Çalışan",
  system_admin: "Sistem yöneticisi",
  director: "Direktör",
  unit_head: "Birim yöneticisi",
  team_manager: "Ekip yöneticisi",
  project_manager: "Proje yöneticisi",
  employee: "Çalışan",
};
const dateTime = (value: unknown) =>
  typeof value === "string" && value
    ? new Date(value).toLocaleString("tr-TR", {
        dateStyle: "short",
        timeStyle: "short",
      })
    : "—";
const errorText = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "İşlem tamamlanamadı. Yeniden deneyin.";
const asRows = (value: any): Row[] => list<Row>(value);
const failedCurrentTest = (configuration?: {
  version?: number;
  latest_test?: Row | null;
}) =>
  Boolean(
    configuration?.latest_test &&
    configuration.latest_test.configuration_version === configuration.version &&
    ["failure", "failed", "error"].includes(configuration.latest_test.status),
  );
const displayName = (row: Row) =>
  row.display_name ||
  row.full_name ||
  [row.first_name, row.last_name].filter(Boolean).join(" ") ||
  row.username ||
  row.name ||
  "İsimsiz kayıt";
function Notice({
  children,
  tone = "info",
}: {
  children: ReactNode;
  tone?: "info" | "error" | "success";
}) {
  return (
    <div
      className={`onecs-settings-notice ${tone}`}
      role={tone === "error" ? "alert" : "status"}
    >
      {tone === "success" ? (
        <Check size={16} />
      ) : tone === "error" ? (
        <CircleAlert size={16} />
      ) : (
        <ShieldCheck size={16} />
      )}
      <span>{children}</span>
    </div>
  );
}
function Empty({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className="onecs-settings-empty">
      <ShieldCheck size={28} />
      <strong>{title}</strong>
      {description && <p>{description}</p>}
    </div>
  );
}
function Heading({
  icon: Icon,
  title,
  description,
  actions,
}: {
  icon: typeof Users;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className="onecs-settings-heading">
      <span className="onecs-settings-title-icon">
        <Icon size={23} />
      </span>
      <div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      {actions && (
        <div className="onecs-settings-heading-actions">{actions}</div>
      )}
    </div>
  );
}
function Modal({
  title,
  description,
  children,
  onClose,
  busy = false,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  onClose: () => void;
  busy?: boolean;
}) {
  return (
    <Drawer
      title={title}
      subtitle={description}
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <div className="onecs-settings-modal-content" aria-busy={busy}>
        {children}
      </div>
    </Drawer>
  );
}

function ConfigPanel({
  section,
  title,
  description,
  fields,
  canTest = true,
  onSaved,
  onTested,
  refreshToken,
}: {
  section: string;
  title: string;
  description: string;
  fields: FormField[];
  canTest?: boolean;
  onSaved?: () => void;
  onTested?: () => void;
  refreshToken?: number;
}) {
  const { data, loading, error, refresh } = useResource<Configuration>(
    `/admin/settings/${section}`,
  );
  useEffect(() => {
    if (refreshToken !== undefined) refresh();
  }, [refreshToken, refresh]);
  const [values, setValues] = useState<Row>({}),
    [secrets, setSecrets] = useState<Row>({}),
    [dirty, setDirty] = useState(false),
    [loadedVersion, setLoadedVersion] = useState<number | null>(null),
    [testRecipient, setTestRecipient] = useState(""),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    [failure, setFailure] = useState("");
  useEffect(() => {
    if (
      data &&
      !dirty &&
      (loadedVersion === null || data.version >= loadedVersion)
    ) {
      setValues(data.config || {});
      setLoadedVersion(data.version);
      setSecrets({});
    }
  }, [data, dirty, loadedVersion]);
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setFailure("");
    setMessage("");
    try {
      const cleanedSecrets = Object.fromEntries(
        Object.entries(secrets).filter(
          ([, value]) =>
            value === null || (typeof value === "string" && value.length),
        ),
      );
      const saved = await api<Configuration>(`/admin/settings/${section}`, {
        method: "PATCH",
        body: {
          config: Object.fromEntries(
            Object.entries(values).map(([key, value]) => [
              key,
              ["input_price_per_million", "output_price_per_million"].includes(
                key,
              ) && value === ""
                ? null
                : value,
            ]),
          ),
          secrets: cleanedSecrets,
          activate: true,
          expected_version: loadedVersion,
        },
      });
      setValues(saved.config);
      setLoadedVersion(saved.version);
      onSaved?.();
      setSecrets({});
      setDirty(false);
      setMessage(
        section === "ai" && !canTest
          ? "Model ayarları kaydedildi. Bağlantı profillerini bu ayarlarla yeniden test edin."
          : "Yapılandırma kaydedildi. Bağlantı testiyle doğrulayabilirsiniz.",
      );
      refresh();
    } catch (err) {
      setFailure(errorText(err));
    } finally {
      setBusy(false);
    }
  };
  const test = async () => {
    setBusy(true);
    setFailure("");
    setMessage("");
    try {
      const result = await api<Row>(`/admin/integrations/${section}/test`, {
        method: "POST",
        body: section === "smtp" ? { recipient: testRecipient } : {},
      });
      if (
        result.success === false ||
        result.status === "failed" ||
        result.status === "failure" ||
        result.status === "error" ||
        result.status === "unconfigured"
      ) {
        setFailure(
          result.message || result.detail || "Bağlantı testi başarısız.",
        );
      } else
        setMessage(
          result.message || result.detail || "Bağlantı testi tamamlandı.",
        );
      refresh();
    } catch (err) {
      setFailure(errorText(err));
    } finally {
      refresh();
      onTested?.();
      setBusy(false);
    }
  };
  const currentTestFailure = canTest && failedCurrentTest(data);
  if (loading && !data) return <Loading />;
  if (error && !data) return <Notice tone="error">{error}</Notice>;
  return (
    <section className="onecs-settings-card onecs-settings-config">
      <div className="onecs-settings-config-title">
        <div>
          <h3>{title}</h3>
          <p>{description}</p>
        </div>
        <span
          className={`onecs-settings-pill ${currentTestFailure ? "warning" : data?.ready ? "positive" : "muted"}`}
        >
          {section === "general" || (section === "ai" && !canTest)
            ? `Sürüm ${data?.version || 1}`
            : data?.ready
              ? "Bağlantı doğrulandı"
              : currentTestFailure
                ? "Bağlantı testi başarısız"
                : data?.config?.enabled
                  ? "Etkin · test bekliyor"
                  : "Etkin değil"}
        </span>
      </div>
      {(failure || message) && (
        <Notice tone={failure ? "error" : "success"}>
          {failure || message}
        </Notice>
      )}
      {currentTestFailure && !failure && !message && (
        <Notice tone="error">
          {data?.latest_test?.message || "Bağlantı testi başarısız."}
        </Notice>
      )}
      <form onSubmit={save}>
        <div className="onecs-settings-form-grid">
          {fields.map((field, index) => (
            <Fragment key={field.key}>
              {field.group && field.group !== fields[index - 1]?.group && (
                <div className="onecs-settings-form-group-header">
                  <h4>{field.group}</h4>
                </div>
              )}
              <label
                className={`onecs-settings-field ${field.type === "checkbox" ? "toggle-field" : ""}`}
                key={field.key}
              >
                <span>{field.label}</span>
                {field.type === "checkbox" ? (
                  <div className="onecs-settings-toggle-line">
                    <input
                      type="checkbox"
                      checked={Boolean(
                        values[field.key] ?? field.defaultValue ?? false,
                      )}
                      onChange={(e) => {
                        setValues((prev) => ({
                          ...prev,
                          [field.key]: e.target.checked,
                        }));
                        setDirty(true);
                      }}
                      disabled={busy}
                    />
                    <small>{field.hint}</small>
                  </div>
                ) : field.type === "select" ? (
                  <select
                    value={String(
                      values[field.key] ?? field.defaultValue ?? "",
                    )}
                    onChange={(e) => {
                      setValues((prev) => ({
                        ...prev,
                        [field.key]: e.target.value,
                      }));
                      setDirty(true);
                    }}
                    disabled={busy}
                  >
                    {field.options?.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type={field.type || "text"}
                    value={String(
                      (field.secret ? secrets : values)[field.key] ??
                        (field.secret ? "" : (field.defaultValue ?? "")),
                    )}
                    required={field.required}
                    autoComplete={field.secret ? "new-password" : "off"}
                    placeholder={
                      field.secret && data?.secret_fields?.includes(field.key)
                        ? "Kayıtlı · değiştirmek için yeni değer girin"
                        : field.secret
                          ? "Gizli değer girin"
                          : undefined
                    }
                    min={field.type === "number" ? 0 : undefined}
                    step={field.type === "number" ? "any" : undefined}
                    onChange={(e) => {
                      const value =
                        field.type === "number"
                          ? e.target.value === ""
                            ? ""
                            : Number(e.target.value)
                          : e.target.value;
                      if (field.secret)
                        setSecrets((prev) => ({ ...prev, [field.key]: value }));
                      else
                        setValues((prev) => ({ ...prev, [field.key]: value }));
                      setDirty(true);
                    }}
                    disabled={
                      busy || (field.secret && secrets[field.key] === null)
                    }
                  />
                )}{" "}
                {field.secret && data?.secret_fields?.includes(field.key) && (
                  <button
                    type="button"
                    className="onecs-settings-secret-clear"
                    onClick={() => {
                      setSecrets((previous) => ({
                        ...previous,
                        [field.key]: previous[field.key] === null ? "" : null,
                      }));
                      setDirty(true);
                    }}
                    disabled={busy}
                  >
                    {secrets[field.key] === null
                      ? "Kaldırmayı geri al"
                      : "Kayıtlı gizli değeri kaldır"}
                  </button>
                )}
                {field.type !== "checkbox" && (
                  <small>
                    {field.secret
                      ? secrets[field.key] === null
                        ? "Gizli değer kaydettiğinizde kaldırılacak."
                        : "Boş bırakırsanız kayıtlı gizli değer korunur."
                      : field.hint}
                  </small>
                )}
              </label>
            </Fragment>
          ))}
        </div>
        {section === "smtp" && (
          <label className="onecs-settings-field onecs-settings-test-recipient">
            <span>Bağlantı testi alıcısı</span>
            <input
              type="email"
              value={testRecipient}
              onChange={(event) => setTestRecipient(event.target.value)}
              placeholder="test-alicisi@kurum.com"
            />
            <small>
              Test ortamında yalnız deployment izin listesindeki alıcılara
              iletilebilir. Bu adres yapılandırmaya kaydedilmez.
            </small>
          </label>
        )}
        <div className="onecs-settings-form-footer">
          <span>
            {data?.version
              ? `Yapılandırma sürümü ${data.version}`
              : "Henüz yapılandırılmadı"}
            {data?.latest_test?.checked_at
              ? ` · Son test ${dateTime(data.latest_test.checked_at)}`
              : ""}
          </span>
          {canTest && (
            <button
              type="button"
              className="onecs-settings-button"
              disabled={
                busy ||
                dirty ||
                !data?.configured ||
                (section === "smtp" && !testRecipient)
              }
              title={dirty ? "Önce değişiklikleri kaydedin." : undefined}
              onClick={test}
            >
              {busy ? (
                <Loader2 size={15} className="spin" />
              ) : (
                <Network size={15} />
              )}
              Bağlantıyı test et
            </button>
          )}
          <button
            type="submit"
            className="onecs-settings-button primary"
            disabled={busy || !data}
          >
            {busy ? (
              <Loader2 size={15} className="spin" />
            ) : (
              <Check size={15} />
            )}
            Kaydet
          </button>
        </div>
      </form>
    </section>
  );
}

function UserEditor({
  user,
  roles,
  orgs,
  businessGrantAllowed,
  initialSource = "local",
  onClose,
  onSaved,
}: {
  user: Row | null;
  roles: Row[];
  orgs: Row[];
  businessGrantAllowed: boolean;
  initialSource?: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<Row>({
    username: user?.username || "",
    display_name: user ? displayName(user) : "",
    email: user?.email || "",
    primary_org: user?.primary_org || "",
    is_active: user?.is_active ?? true,
    password: "",
    identity_source: user?.identity_source || initialSource,
  });
  const [grantDirty, setGrantDirty] = useState(false);
  const [grants, setGrants] = useState<Row[]>(
    user?.roles?.filter((role: Row) => role.active !== false).length
      ? user.roles
          .filter((role: Row) => role.active !== false)
          .map((role: Row) => ({ ...role }))
      : [
          {
            role: "EMPLOYEE",
            org_node: "",
            includes_descendants: false,
            active: true,
          },
        ],
  );
  const [busy, setBusy] = useState(false),
    [failure, setFailure] = useState("");
  const set = (key: string, value: unknown) =>
    setForm((prev) => ({ ...prev, [key]: value }));
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setFailure("");
    try {
      const body: Row = {
        ...form,
        ...(!user || grantDirty
          ? {
              roles: grants.map((grant) => ({
                ...grant,
                org_node: grant.org_node || null,
              })),
            }
          : {}),
        primary_org: form.primary_org || null,
        ...(user ? { expected_access_version: user.access_version } : {}),
      };
      if (!body.password || body.identity_source === "ldap")
        delete body.password;
      await api(`/admin/users${user ? `/${user.id}` : ""}`, {
        method: user ? "PATCH" : "POST",
        body,
      });
      onSaved();
    } catch (err) {
      setFailure(errorText(err));
    } finally {
      setBusy(false);
    }
  };
  const availableRoles: Row[] = roles.length
    ? roles
    : Object.keys(roleLabels)
        .filter((code) => code === code.toUpperCase())
        .map((code) => ({ code, label: roleLabels[code] }));
  const roleEditable = (code: string) =>
    businessGrantAllowed || ["EMPLOYEE", "SYSTEM_ADMIN"].includes(code);
  const updateGrant = (index: number, key: string, value: unknown) => {
    setGrantDirty(true);
    setGrants((previous) =>
      previous.map((grant, i) =>
        i === index ? { ...grant, [key]: value } : grant,
      ),
    );
  };
  return (
    <Modal
      title={
        user
          ? "Kullanıcıyı düzenle"
          : form.identity_source === "ldap"
            ? "LDAP kullanıcısı ekle"
            : "Sistem kullanıcısı ekle"
      }
      description="Kimlik, organizasyon kapsamı ve rol atamasını birlikte yönetin."
      onClose={onClose}
      busy={busy}
    >
      <form onSubmit={save}>
        {failure && <Notice tone="error">{failure}</Notice>}
        {form.identity_source === "ldap" && (
          <Notice>
            Hesap, yapılandırılmış dizinde kalıcı kimliğiyle doğrulanır. LDAP
            parolası onecs’te saklanmaz; rol ataması ayrıca uygulanır.
          </Notice>
        )}
        <div className="onecs-settings-form-grid">
          {!user && (
            <label className="onecs-settings-field">
              <span>Kimlik kaynağı</span>
              <select
                value={form.identity_source}
                onChange={(event) => set("identity_source", event.target.value)}
                disabled={busy}
              >
                <option value="local">Sistem hesabı</option>
                <option value="ldap">LDAP / Active Directory</option>
              </select>
            </label>
          )}
          <label className="onecs-settings-field">
            <span>Kullanıcı adı</span>
            <input
              value={form.username}
              onChange={(e) => set("username", e.target.value)}
              required
              disabled={!!user || busy}
              maxLength={150}
              autoComplete="off"
            />
          </label>
          <label className="onecs-settings-field">
            <span>Ad soyad</span>
            <input
              value={form.display_name}
              onChange={(e) => set("display_name", e.target.value)}
              required
              disabled={busy}
              maxLength={180}
            />
          </label>
          <label className="onecs-settings-field">
            <span>E-posta</span>
            <input
              type="email"
              value={form.email}
              onChange={(e) => set("email", e.target.value)}
              disabled={busy}
            />
          </label>
          {form.identity_source !== "ldap" && (
            <label className="onecs-settings-field">
              <span>{user ? "Yeni parola (isteğe bağlı)" : "İlk parola"}</span>
              <input
                type="password"
                value={form.password}
                onChange={(e) => set("password", e.target.value)}
                required={!user}
                minLength={12}
                autoComplete="new-password"
                disabled={busy}
              />
              <small>
                {user
                  ? "Boş bırakırsanız mevcut parola korunur."
                  : "En az 12 karakter kullanın."}
              </small>
            </label>
          )}
          <label className="onecs-settings-field">
            <span>Ana organizasyon birimi</span>
            <select
              value={form.primary_org}
              onChange={(e) => set("primary_org", e.target.value)}
              disabled={busy}
            >
              <option value="">Organizasyon seçin</option>
              {orgs.map((org) => (
                <option key={org.id} value={org.id}>
                  {org.code ? `${org.code} · ` : ""}
                  {org.name}
                </option>
              ))}
            </select>
          </label>
          <label className="onecs-settings-field toggle-field">
            <span>Erişim durumu</span>
            <div className="onecs-settings-toggle-line">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => set("is_active", e.target.checked)}
                disabled={busy}
              />
              <small>Aktif kullanıcı giriş yapabilir.</small>
            </div>
          </label>
        </div>
        <div className="onecs-settings-grants-heading">
          <strong>Rol ve kapsam atamaları</strong>
          <button
            type="button"
            className="onecs-settings-button small"
            disabled={busy}
            onClick={() => {
              setGrantDirty(true);
              setGrants((previous) => [
                ...previous,
                {
                  role: "EMPLOYEE",
                  org_node: form.primary_org || "",
                  includes_descendants: false,
                  active: true,
                },
              ]);
            }}
          >
            <Plus size={13} />
            Rol ekle
          </button>
        </div>
        {!businessGrantAllowed && (
          <p className="onecs-settings-footnote">
            İş yönetimi rolleri, ayrıca yetkili bir iş yöneticisi tarafından
            atanır. Teknik yönetici mevcut iş rolünü yükseltemez.
          </p>
        )}
        <div className="onecs-settings-grants">
          {grants.map((grant, index) => (
            <div className="onecs-settings-grant" key={grant.id || index}>
              <label className="onecs-settings-field">
                <span>Rol</span>
                <select
                  value={grant.role}
                  onChange={(e) => updateGrant(index, "role", e.target.value)}
                  disabled={busy || !roleEditable(grant.role)}
                >
                  {availableRoles
                    .filter(
                      (role) =>
                        roleEditable(role.code || role.role || role.value) ||
                        grant.role === (role.code || role.role || role.value),
                    )
                    .map((role) => (
                      <option
                        key={role.code || role.role || role.value}
                        value={role.code || role.role || role.value}
                      >
                        {roleLabels[role.code || role.role || role.value] ||
                          role.label ||
                          role.name ||
                          role.code ||
                          role.role ||
                          role.value}
                      </option>
                    ))}
                </select>
              </label>
              <label className="onecs-settings-field">
                <span>Kapsam</span>
                <select
                  value={grant.org_node || ""}
                  onChange={(e) =>
                    updateGrant(index, "org_node", e.target.value)
                  }
                  disabled={busy || !roleEditable(grant.role)}
                >
                  <option value="">Global / kapsam yok</option>
                  {orgs.map((org) => (
                    <option key={org.id} value={org.id}>
                      {org.code || org.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="onecs-settings-field toggle-field">
                <span>Alt birimler</span>
                <div className="onecs-settings-toggle-line">
                  <input
                    type="checkbox"
                    checked={!!grant.includes_descendants}
                    onChange={(e) =>
                      updateGrant(
                        index,
                        "includes_descendants",
                        e.target.checked,
                      )
                    }
                    disabled={busy || !roleEditable(grant.role)}
                  />
                  <small>Dahil</small>
                </div>
              </label>
              <button
                className="onecs-settings-icon-button"
                type="button"
                disabled={busy || !roleEditable(grant.role)}
                aria-label={`${index + 1}. rolü kaldır`}
                onClick={() => {
                  setGrantDirty(true);
                  setGrants((previous) =>
                    previous.filter((_, i) => i !== index),
                  );
                }}
              >
                <X size={16} />
              </button>
            </div>
          ))}
        </div>
        <footer className="onecs-settings-modal-footer">
          <button
            type="button"
            className="onecs-settings-button"
            onClick={onClose}
            disabled={busy}
          >
            Vazgeç
          </button>
          <button
            type="submit"
            className="onecs-settings-button primary"
            disabled={busy}
          >
            {busy ? (
              <Loader2 className="spin" size={16} />
            ) : (
              <Check size={16} />
            )}
            Kaydı kaydet
          </button>
        </footer>
      </form>
    </Modal>
  );
}

function UsersPanel() {
  const { user: actor } = useAuth();
  const [query, setQuery] = useState(""),
    [source, setSource] = useState("all"),
    [archived, setArchived] = useState(false),
    [editor, setEditor] = useState<Row | null | undefined>();
  const { data, loading, error, refresh } = useResource<any>(
    `/admin/users?search=${encodeURIComponent(query)}&source=${source}&archived=${archived}`,
  );
  const { data: roleData } = useResource<any>("/admin/roles");
  const { data: orgData } = useResource<any>("/organization");
  const users = asRows(data),
    roles = asRows(roleData?.roles || roleData),
    orgs = asRows(orgData?.nodes || orgData);
  return (
    <>
      <Heading
        icon={Users}
        title="Kullanıcı yönetimi"
        description="Sistem hesaplarını, kurumsal kimlikleri ve organizasyon kapsamlarını yönetin."
      />
      <Notice>
        Kontrollü erişim. İş rolleri, organizasyon kapsamı ve proje / vaka
        üyeliği birlikte değerlendirilir.
      </Notice>
      <section className="onecs-settings-card">
        <div
          className="onecs-settings-subtabs"
          role="tablist"
          aria-label="Kullanıcı kaynağı"
        >
          {[
            { value: "all", label: "Tüm kullanıcılar" },
            { value: "local", label: "Sistem kullanıcıları" },
            { value: "ldap", label: "LDAP kullanıcıları" },
          ].map((item) => (
            <button
              key={item.value}
              className={source === item.value ? "active" : ""}
              role="tab"
              aria-selected={source === item.value}
              onClick={() => setSource(item.value)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="onecs-settings-toolbar">
          <div className="onecs-settings-search">
            <Search size={17} />
            <input
              aria-label="Kullanıcı ara"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Ad, kullanıcı adı veya e-posta ara…"
            />
            {query && (
              <button onClick={() => setQuery("")} aria-label="Aramayı temizle">
                <X size={15} />
              </button>
            )}
          </div>
          <label className="onecs-settings-archive-toggle">
            <input
              type="checkbox"
              checked={archived}
              onChange={(e) => setArchived(e.target.checked)}
            />
            Devre dışı hesaplar dahil
          </label>
          <button
            className="onecs-settings-button primary"
            onClick={() => setEditor(null)}
          >
            <Plus size={16} />
            {source === "ldap"
              ? "LDAP kullanıcısı ekle"
              : "Sistem kullanıcısı ekle"}
          </button>
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="onecs-settings-table-wrap">
          <table className="onecs-settings-table">
            <thead>
              <tr>
                <th>Kullanıcı</th>
                <th>E-posta / Kaynak</th>
                <th>Rol ve kapsam</th>
                <th>Durum</th>
                <th className="right">İşlemler</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>
                    <strong>{displayName(user)}</strong>
                    <small>{user.username}</small>
                  </td>
                  <td>
                    {user.email || "—"}
                    <small>
                      {(user.identity_source || user.source) === "ldap"
                        ? "LDAP / Active Directory"
                        : "Sistem hesabı"}
                    </small>
                  </td>
                  <td>
                    <span className="onecs-settings-role">
                      <ShieldCheck size={13} />
                      {roleLabels[user.role] ||
                        user.role ||
                        asRows(user.roles)
                          .filter((role) => role.active !== false)
                          .map(
                            (role) =>
                              roleLabels[role.role] || role.name || role.code,
                          )
                          .join(", ") ||
                        "Rol atanmadı"}
                    </span>
                    <small>
                      {user.primary_org_name ||
                        user.org_name ||
                        user.organization_name ||
                        user.org_code ||
                        "Kapsam ayrıntısını düzenle"}
                    </small>
                  </td>
                  <td>
                    <span
                      className={`onecs-settings-pill ${user.is_active !== false ? "positive" : "muted"}`}
                    >
                      {user.is_active !== false ? "Aktif" : "Devre dışı"}
                    </span>
                  </td>
                  <td className="right">
                    <button
                      className="onecs-settings-icon-button"
                      disabled={
                        user.id === actor.id ||
                        (!roleData?.business_grant_allowed &&
                          asRows(user.roles).some(
                            (role) =>
                              role.active !== false &&
                              [
                                "DIRECTOR",
                                "UNIT_HEAD",
                                "TEAM_MANAGER",
                                "PROJECT_MANAGER",
                              ].includes(role.role),
                          ))
                      }
                      title={
                        user.id === actor.id
                          ? "Kendi erişim kapsamınız bu ekrandan düzenlenemez."
                          : undefined
                      }
                      onClick={() => setEditor(user)}
                      aria-label={`${displayName(user)} kullanıcısını düzenle`}
                    >
                      <Pencil size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {loading && !users.length ? (
          <Loading />
        ) : !users.length ? (
          <Empty
            title={
              query
                ? "Aramanızla eşleşen kullanıcı yok."
                : "Bu kaynakta kullanıcı bulunmuyor."
            }
            description="Sistem kullanıcısı ekleyebilir veya LDAP bağlantınızı yapılandırabilirsiniz."
          />
        ) : null}
        <footer className="onecs-settings-pagination">
          <span>{data?.count ?? users.length} kullanıcı</span>
          <button
            className="onecs-settings-button small"
            onClick={refresh}
            disabled={loading}
          >
            <RefreshCw size={13} />
            Yenile
          </button>
        </footer>
      </section>
      <p className="onecs-settings-footnote">
        Kullanıcı hesabının kapatılması, geçmiş katkı ve denetim kayıtlarını
        silmez.
      </p>
      {editor !== undefined && (
        <UserEditor
          user={editor}
          roles={roles}
          orgs={orgs}
          businessGrantAllowed={!!roleData?.business_grant_allowed}
          initialSource={source === "ldap" ? "ldap" : "local"}
          onClose={() => setEditor(undefined)}
          onSaved={() => {
            setEditor(undefined);
            refresh();
          }}
        />
      )}
    </>
  );
}

function OrganizationPanel() {
  const { data, loading, error } = useResource<any>("/organization");
  const { data: roleData } = useResource<any>("/admin/roles");
  const nodes = asRows(data?.nodes || data),
    roles = asRows(roleData?.roles || roleData);
  return (
    <>
      <Heading
        icon={GitBranch}
        title="Organizasyon ve roller"
        description="Organizasyon kapsamlarını ve rol sınırlarını birlikte görün."
      />
      <Notice>
        Proje yönetimi proje yöneticisi atamasına bağlıdır. Bir birim
        yöneticisi, başka bir proje yöneticisinin projelerinde yalnızca
        organizasyon rolüyle yönetim yetkisi kazanmaz.
      </Notice>
      <div className="onecs-settings-two-columns">
        <section className="onecs-settings-card">
          <div className="onecs-settings-config-title">
            <h3>Organizasyon birimleri</h3>
            <span className="onecs-settings-pill muted">
              {nodes.length} birim
            </span>
          </div>
          {error && <Notice tone="error">{error}</Notice>}
          {loading ? (
            <Loading />
          ) : (
            <div className="onecs-settings-org-list">
              {nodes.map((node) => (
                <div key={node.id}>
                  <span className="onecs-settings-title-icon small">
                    <GitBranch size={16} />
                  </span>
                  <div>
                    <strong>{node.code || node.name}</strong>
                    <small>
                      {node.code ? node.name : node.type} ·{" "}
                      {node.kind || node.type || "Birim"}
                    </small>
                  </div>
                  {node.parent_name && (
                    <span className="onecs-settings-muted">
                      {node.parent_name}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
        <section className="onecs-settings-card">
          <div className="onecs-settings-config-title">
            <h3>Rol kataloğu</h3>
            <ShieldCheck size={18} />
          </div>
          <div className="onecs-settings-role-list">
            {(roles.length
              ? roles
              : Object.entries(roleLabels)
                  .filter(([key]) => key === key.toUpperCase())
                  .map(([code, label]) => ({ code, label }))
            ).map((role: Row) => (
              <div key={role.code || role.value || role.id}>
                <strong>
                  {roleLabels[role.code || role.value] ||
                    role.label ||
                    role.name ||
                    role.code ||
                    role.value}
                </strong>
                <p>
                  {role.description ||
                    (
                      {
                        SYSTEM_ADMIN:
                          "Teknik yapılandırma, kullanıcı ve denetim yönetimi.",
                        DIRECTOR: "Direktörlük görünümü, karar ve eskalasyon.",
                        UNIT_HEAD:
                          "Kendi unitindeki yönetim, atama ve resmî vaka açma.",
                        TEAM_MANAGER: "Kendi ekibinde iş ve taahhüt yönetimi.",
                        PROJECT_MANAGER:
                          "Atandığı projede başvuru, görev ve yayın yönetimi.",
                        EMPLOYEE:
                          "Kendi işleri, proje başvurusu ve yetkili katkılar.",
                      } as Record<string, string>
                    )[role.code || role.value] ||
                    "Açık kapsam ve kaynak ilişkisine göre yetkilendirilir."}
                </p>
              </div>
            ))}
          </div>
        </section>
      </div>
    </>
  );
}

const generalFields: FormField[] = [
  {
    key: "application_name",
    label: "Uygulama adı",
    type: "select",
    defaultValue: "onecs",
    options: [{ value: "onecs", label: "onecs" }],
  },
  {
    key: "timezone",
    label: "Saat dilimi",
    type: "select",
    defaultValue: "Europe/Istanbul",
    options: [{ value: "Europe/Istanbul", label: "Europe/Istanbul (UTC+3)" }],
  },
  { key: "support_email", label: "Destek e-posta adresi", type: "email" },
];
const aiFields: FormField[] = [
  {
    key: "enabled",
    label: "AI özelliklerini etkinleştir",
    type: "checkbox",
    hint: "Rapor taslakları yalnız yetkili kaynaklardan oluşturulur.",
    group: "Model ve üretim",
  },
  {
    key: "model",
    label: "Model adı",
    hint: "Tüm bağlantı profilleri bu model kimliğini kullanır.",
    group: "Model ve üretim",
  },
  {
    key: "temperature",
    label: "Üretim sıcaklığı (temperature)",
    type: "number",
    defaultValue: 0,
    hint: "Düşük değer daha tutarlı yönetim özetleri sağlar.",
    group: "Model ve üretim",
  },
  {
    key: "timeout_seconds",
    label: "İstek zaman aşımı (saniye)",
    type: "number",
    defaultValue: 180,
    hint: "Sağlayıcı yanıtı için en fazla 180 saniye.",
    group: "Model ve üretim",
  },
  {
    key: "max_input_tokens",
    label: "İstek başına giriş tokenı",
    type: "number",
    defaultValue: 6000,
    group: "Token sınırları",
  },
  {
    key: "max_output_tokens",
    label: "İstek başına çıkış tokenı",
    type: "number",
    defaultValue: 4096,
    group: "Token sınırları",
  },
  {
    key: "daily_token_limit",
    label: "Günlük toplam token sınırı",
    type: "number",
    defaultValue: 100000,
    group: "Token sınırları",
  },
  {
    key: "daily_user_token_limit",
    label: "Kişi başı günlük token sınırı",
    type: "number",
    defaultValue: 20000,
    group: "Token sınırları",
  },
  {
    key: "input_price_per_million",
    label: "1 milyon giriş tokenı fiyatı (USD)",
    type: "number",
    hint: "Boş değer için maliyet bilinmiyor olarak kalır.",
    group: "Fiyatlandırma",
  },
  {
    key: "output_price_per_million",
    label: "1 milyon çıkış tokenı fiyatı (USD)",
    type: "number",
    hint: "Kullanım anındaki fiyat sürümü tarihsel kayıtla korunur.",
    group: "Fiyatlandırma",
  },
];
const ldapFields: FormField[] = [
  {
    key: "enabled",
    label: "Kurumsal LDAP girişini etkinleştir",
    type: "checkbox",
    hint: "Kaydedilen ayarları gerçek bağlantı testiyle doğrulayın.",
    group: "Bağlantı ve güvenlik",
  },
  {
    key: "url",
    label: "LDAP sunucusu",
    hint: "ldap://sunucu:389 veya ldaps://sunucu:636",
    group: "Bağlantı ve güvenlik",
  },
  {
    key: "start_tls",
    label: "StartTLS kullan",
    type: "checkbox",
    defaultValue: true,
    hint: "LDAP 389 bağlantısı TLS ile yükseltilir; sertifika doğrulaması zorunludur.",
    group: "Bağlantı ve güvenlik",
  },
  {
    key: "timeout_seconds",
    label: "Bağlantı zaman aşımı (saniye)",
    type: "number",
    defaultValue: 10,
    group: "Bağlantı ve güvenlik",
  },
  {
    key: "bind_dn",
    label: "Servis hesabı",
    hint: "Dizinde arama yapacak sınırlı yetkili hesap.",
    group: "Kimlik doğrulama",
  },
  {
    key: "bind_password",
    label: "Servis hesabı parolası",
    type: "password",
    secret: true,
    group: "Kimlik doğrulama",
  },
  {
    key: "base_dn",
    label: "Ana arama kökü (Base DN)",
    hint: "Dizin keşfiyle sunucudaki arama köklerini görebilirsiniz.",
    group: "Dizin ve arama",
  },
  {
    key: "user_search_base",
    label: "Kullanıcı arama kökü",
    hint: "Boşsa ana arama kökü kullanılır.",
    group: "Dizin ve arama",
  },
  {
    key: "group_search_base",
    label: "Grup arama kökü",
    hint: "Boşsa ana arama kökü kullanılır.",
    group: "Dizin ve arama",
  },
  {
    key: "user_filter",
    label: "Kullanıcı arama filtresi",
    hint: "Giriş için {username}; dizin araması için {query} desteklenir.",
    group: "Dizin ve arama",
  },
  {
    key: "group_filter",
    label: "Grup arama filtresi",
    hint: "İlk giriş yetkileri, kullanıcının doğrudan grup üyelikleri ve aşağıdaki eşlemelerden belirlenir.",
    group: "Dizin ve arama",
  },
  {
    key: "auto_provision_enabled",
    label: "LDAP ile ilk girişte hesabı otomatik oluştur",
    type: "checkbox",
    defaultValue: true,
    hint: "Kullanıcının parolası doğrulandıktan ve yetkili bir grup eşleşmesinden sonra hesap oluşturulur.",
    group: "İlk giriş ve grup yetkileri",
  },
  {
    key: "match_organization_groups",
    label: "Organizasyon koduyla aynı adlı LDAP grubundan ekip üyeliği",
    type: "checkbox",
    defaultValue: true,
    hint: "Grubun CN değeri organizasyon koduyla tam eşleşirse yalnız o organizasyonda Çalışan rolü verilir. Ad önekleri ve alt gruplar eşleştirilmez.",
    group: "İlk giriş ve grup yetkileri",
  },
  {
    key: "username_attribute",
    label: "Kullanıcı adı alanı",
    defaultValue: "sAMAccountName",
    group: "Profil alanları",
  },
  {
    key: "display_name_attribute",
    label: "Görünen ad alanı",
    defaultValue: "displayName",
    group: "Profil alanları",
  },
  {
    key: "email_attribute",
    label: "E-posta alanı",
    defaultValue: "mail",
    group: "Profil alanları",
  },
  {
    key: "membership_attribute",
    label: "Grup üyeliği alanı",
    defaultValue: "memberOf",
    group: "Profil alanları",
  },
  {
    key: "department_attribute",
    label: "Departman alanı",
    defaultValue: "department",
    group: "Profil alanları",
  },
  {
    key: "title_attribute",
    label: "Unvan alanı",
    defaultValue: "title",
    group: "Profil alanları",
  },
  {
    key: "manager_attribute",
    label: "Yönetici alanı",
    defaultValue: "manager",
    group: "Profil alanları",
  },
];

const smtpFields: FormField[] = [
  {
    key: "enabled",
    label: "E-posta bildirimleri",
    type: "checkbox",
    hint: "Atama ve SLA bildirimleri kalıcı kuyruktan iletilir.",
  },
  { key: "host", label: "SMTP sunucusu" },
  { key: "port", label: "Port", type: "number", defaultValue: 587 },
  { key: "username", label: "Kullanıcı adı" },
  { key: "password", label: "SMTP parolası", type: "password", secret: true },
  { key: "from_email", label: "Gönderen e-posta", type: "email" },
  {
    key: "use_tls",
    label: "STARTTLS",
    type: "checkbox",
    defaultValue: true,
    hint: "Bağlantı sertifikası doğrulanır.",
  },
  {
    key: "use_ssl",
    label: "Doğrudan TLS",
    type: "checkbox",
    hint: "STARTTLS ile birlikte etkinleştirmeyin.",
  },
  {
    key: "timeout_seconds",
    label: "Bağlantı zaman aşımı (saniye)",
    type: "number",
    defaultValue: 10,
  },
];
const teamsFields: FormField[] = [
  {
    key: "enabled",
    label: "Teams bildirimleri",
    type: "checkbox",
    hint: "Yalnız onaylı hedefe gönderilir. Hassas kayıt içeriği bildirimde yer almaz.",
  },
  {
    key: "webhook_url",
    label: "Teams webhook adresi",
    type: "password",
    secret: true,
  },
];

type AIProfile = Configuration & {
  id: string;
  name: string;
  active: boolean;
  is_default: boolean;
  effective_config?: Row;
  settings_version?: number;
};
function AIProfileEditor({
  profile,
  slot,
  onClose,
  onSaved,
}: {
  profile: AIProfile | null;
  slot: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(profile?.name || `Bağlantı ${slot}`),
    [endpoint, setEndpoint] = useState(profile?.config.base_url || ""),
    [enabled, setEnabled] = useState(profile?.config.enabled ?? true),
    [apiKey, setApiKey] = useState(""),
    [removeKey, setRemoveKey] = useState(false),
    [busy, setBusy] = useState(false),
    [failure, setFailure] = useState("");
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setFailure("");
    try {
      await api(`/admin/ai/profiles${profile ? `/${profile.id}` : ""}`, {
        method: profile ? "PATCH" : "POST",
        body: {
          name,
          config: {
            enabled,
            provider: "openai-compatible",
            base_url: endpoint,
          },
          secrets: removeKey
            ? { api_key: null }
            : apiKey
              ? { api_key: apiKey }
              : {},
          ...(profile ? { expected_version: profile.version } : {}),
        },
      });
      setApiKey("");
      onSaved();
    } catch (error) {
      setFailure(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title={profile ? "Bağlantı profilini düzenle" : "AI bağlantısı ekle"}
      description="Bağlantılar ayrı API anahtarları kullanır. Model ve üretim ayarları ortak alandan yönetilir."
      onClose={onClose}
      busy={busy}
    >
      <form onSubmit={save}>
        {failure && <Notice tone="error">{failure}</Notice>}
        <div className="onecs-settings-form-grid">
          <label className="onecs-settings-field">
            <span>Bağlantı adı</span>
            <input
              required
              maxLength={100}
              value={name}
              onChange={(event) => setName(event.target.value)}
              disabled={busy}
            />
          </label>
          <label className="onecs-settings-field">
            <span>Sağlayıcı</span>
            <select disabled>
              <option>OpenAI uyumlu API</option>
            </select>
          </label>
          <label className="onecs-settings-field onecs-settings-field-full">
            <span>API adresi</span>
            <input
              type="url"
              required
              value={endpoint}
              onChange={(event) => setEndpoint(event.target.value)}
              placeholder="https://model.example.com/v1"
              disabled={busy}
            />
            <small>
              Sağlayıcınızın verdiği temel adresi veya chat/completions uç
              noktasını girin.
            </small>
          </label>
          <label className="onecs-settings-field onecs-settings-field-full">
            <span>API anahtarı</span>
            <input
              type="password"
              autoComplete="new-password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder={
                profile?.secret_fields?.includes("api_key")
                  ? "Kayıtlı · değiştirmek için yeni anahtar girin"
                  : "API anahtarını girin"
              }
              disabled={busy || removeKey}
            />
            <small>
              Boş bırakırsanız kayıtlı anahtar korunur. Anahtar geri okunmaz.
            </small>
            {profile?.secret_fields?.includes("api_key") && (
              <button
                type="button"
                className="onecs-settings-secret-clear"
                disabled={busy}
                onClick={() => setRemoveKey((value) => !value)}
              >
                {removeKey
                  ? "Anahtar kaldırmayı geri al"
                  : "Kayıtlı API anahtarını kaldır"}
              </button>
            )}
          </label>
          <label className="onecs-settings-field toggle-field">
            <span>Bağlantı durumu</span>
            <div className="onecs-settings-toggle-line">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(event) => setEnabled(event.target.checked)}
                disabled={busy}
              />
              <small>Bu profil kullanılabilir.</small>
            </div>
          </label>
        </div>
        <footer className="onecs-settings-modal-footer">
          <button
            type="button"
            className="onecs-settings-button"
            onClick={onClose}
            disabled={busy}
          >
            Vazgeç
          </button>
          <button className="onecs-settings-button primary" disabled={busy}>
            {busy ? "Kaydediliyor…" : "Profili kaydet"}
          </button>
        </footer>
      </form>
    </Modal>
  );
}
export function AIConnections({
  profiles,
  loading,
  error,
  refresh,
  onDefaultSelected,
}: {
  profiles: AIProfile[];
  loading: boolean;
  error: string;
  refresh: () => void;
  onDefaultSelected?: () => void;
}) {
  const [editor, setEditor] = useState<{
      profile: AIProfile | null;
      slot: number;
    } | null>(null),
    [busy, setBusy] = useState(""),
    [failure, setFailure] = useState(""),
    [message, setMessage] = useState("");
  const action = async (profile: AIProfile, kind: "test" | "default") => {
    setBusy(profile.id);
    setFailure("");
    setMessage("");
    try {
      const response = await api<Row>(
        `/admin/ai/profiles/${profile.id}/${kind}`,
        { method: "POST", body: { expected_version: profile.version } },
      );
      if (kind === "test" && response.status !== "success")
        setFailure(response.message || "Bağlantı testi başarısız.");
      else
        setMessage(
          kind === "default"
            ? `${profile.name} varsayılan bağlantı olarak seçildi.`
            : response.message || "Gerçek model bağlantısı doğrulandı.",
        );
      if (kind === "default") onDefaultSelected?.();
    } catch (error) {
      setFailure(errorText(error));
    } finally {
      refresh();
      setBusy("");
    }
  };
  const slots: (AIProfile | null)[] = [
    ...profiles,
    ...Array.from({ length: Math.max(0, 2 - profiles.length) }, () => null),
  ];
  return (
    <>
      <div className="onecs-settings-section-intro">
        <div>
          <h3>Bağlantı profilleri</h3>
          <p>
            İki bağlantıyı ayrı ayrı doğrulayın ve raporlarda kullanılacak
            varsayılanı seçin.
          </p>
        </div>
        <span className="onecs-settings-pill muted">
          API anahtarları ayrı saklanır
        </span>
      </div>
      {(error || failure || message) && (
        <Notice tone={error || failure ? "error" : "success"}>
          {error || failure || message}
        </Notice>
      )}
      {loading && !profiles.length ? (
        <Loading />
      ) : (
        <div className="onecs-settings-ai-connections">
          {slots.map((profile, index) => (
            <section
              className={`onecs-settings-card onecs-settings-ai-profile ${profile?.is_default ? "is-default" : ""}`}
              key={profile?.id || `slot-${index}`}
            >
              <div className="onecs-settings-ai-profile-top">
                <span className="onecs-settings-title-icon">
                  <Network size={21} />
                </span>
                <div>
                  <h3>{profile?.name || `Bağlantı ${index + 1}`}</h3>
                  <p>
                    {profile?.is_default
                      ? "Raporlar için varsayılan bağlantı"
                      : profile
                        ? "Alternatif bağlantı profili"
                        : "Henüz yapılandırılmadı"}
                  </p>
                </div>
                {profile?.is_default && (
                  <span className="onecs-settings-pill default">
                    <Check size={12} />
                    Varsayılan
                  </span>
                )}
              </div>
              {profile ? (
                <>
                  <div className="onecs-settings-ai-endpoint">
                    <span>API adresi</span>
                    <code>{profile.config.base_url || "Adres girilmedi"}</code>
                  </div>
                  <div className="onecs-settings-ai-profile-meta">
                    <span
                      className={`onecs-settings-pill ${failedCurrentTest(profile) ? "warning" : profile.ready ? "positive" : "muted"}`}
                    >
                      {profile.ready
                        ? "Bağlantı doğrulandı"
                        : failedCurrentTest(profile)
                          ? "Test başarısız"
                          : profile.config.enabled
                            ? "Test bekliyor"
                            : "Devre dışı"}
                    </span>
                    <span>
                      {profile.secret_fields?.includes("api_key")
                        ? "Anahtar kayıtlı"
                        : "Anahtar tanımlı değil"}
                    </span>
                  </div>
                  {profile.latest_test && (
                    <p className="onecs-settings-ai-last-test">
                      Son test: {dateTime(profile.latest_test.checked_at)} ·{" "}
                      {profile.latest_test.status === "success"
                        ? "Başarılı"
                        : profile.latest_test.status === "unconfigured"
                          ? "Yapılandırılmadı"
                          : ["failure", "failed", "error"].includes(
                                profile.latest_test.status,
                              )
                            ? "Başarısız"
                            : "Sonuç bilinmiyor"}
                    </p>
                  )}
                  {profile.latest_test &&
                    profile.latest_test.status !== "success" && (
                      <Notice
                        tone={
                          profile.latest_test.status === "unconfigured"
                            ? "info"
                            : "error"
                        }
                      >
                        {profile.latest_test.message ||
                          "Bağlantı doğrulanamadı. Profili yeniden test edin."}
                      </Notice>
                    )}
                  <div className="onecs-settings-ai-profile-actions">
                    <button
                      className="onecs-settings-button"
                      onClick={() => setEditor({ profile, slot: index + 1 })}
                      disabled={!!busy}
                    >
                      <Pencil size={14} />
                      Düzenle
                    </button>
                    <button
                      className="onecs-settings-button"
                      onClick={() => action(profile, "test")}
                      disabled={!!busy || !profile.config.enabled}
                    >
                      {busy === profile.id ? (
                        <Loader2 size={14} className="spin" />
                      ) : (
                        <Network size={14} />
                      )}
                      Test et
                    </button>
                    <button
                      className="onecs-settings-button primary"
                      onClick={() => action(profile, "default")}
                      disabled={!!busy || profile.is_default || !profile.ready}
                      title={
                        !profile.ready
                          ? "Önce bu bağlantıyı güncel model ayarlarıyla test edin."
                          : undefined
                      }
                    >
                      {profile.is_default ? "Varsayılan" : "Varsayılan yap"}
                    </button>
                  </div>
                </>
              ) : (
                <div className="onecs-settings-ai-empty">
                  <p>
                    Bağımsız bir API adresi ve anahtarla ikinci bağlantınızı
                    hazırlayın.
                  </p>
                  <button
                    className="onecs-settings-button"
                    onClick={() =>
                      setEditor({ profile: null, slot: index + 1 })
                    }
                  >
                    <Plus size={15} />
                    Bağlantıyı yapılandır
                  </button>
                </div>
              )}
            </section>
          ))}
        </div>
      )}
      {editor && (
        <AIProfileEditor
          profile={editor.profile}
          slot={editor.slot}
          onClose={() => setEditor(null)}
          onSaved={() => {
            setEditor(null);
            refresh();
          }}
        />
      )}
    </>
  );
}

function AIPanel() {
  const [from, setFrom] = useState(""),
    [to, setTo] = useState(""),
    [model, setModel] = useState(""),
    [profileId, setProfileId] = useState(""),
    [sharedRefresh, setSharedRefresh] = useState(0);
  const profilesResource = useResource<any>("/admin/ai/profiles");
  const profiles = list<AIProfile>(profilesResource.data);
  const { data, loading, error } = useResource<Row>(
    `/admin/ai/usage?from=${from}&to=${to}&model=${encodeURIComponent(model)}&profile_id=${encodeURIComponent(profileId)}`,
  );
  const totals = data?.totals || {};
  return (
    <>
      <Heading
        icon={Cpu}
        title="Yapay zekâ"
        description="Model bağlantısını, token sınırlarını ve tarih bazlı kullanımınızı yönetin."
      />
      <AIConnections
        profiles={profiles}
        loading={profilesResource.loading}
        error={profilesResource.error}
        refresh={profilesResource.refresh}
        onDefaultSelected={() => setSharedRefresh((value) => value + 1)}
      />
      <ConfigPanel
        section="ai"
        title="Ortak model ayarları"
        description="Model, üretim sınırları ve fiyatlar tüm bağlantı profillerinde ortak kullanılır. Model değişikliğinden sonra bağlantıları yeniden test edin."
        fields={aiFields}
        canTest={false}
        onSaved={profilesResource.refresh}
        refreshToken={sharedRefresh}
      />
      <section className="onecs-settings-card">
        <div className="onecs-settings-config-title">
          <div>
            <h3>Kullanım ve tahmini maliyet</h3>
            <p>
              Sağlayıcı token bilgisi yoksa ölçüm bilinmiyor olarak gösterilir.
            </p>
          </div>
        </div>
        <div className="onecs-settings-filters">
          <label className="onecs-settings-field">
            <span>Bağlantı</span>
            <select
              value={profileId}
              onChange={(event) => setProfileId(event.target.value)}
            >
              <option value="">Tüm bağlantılar</option>
              {profiles.map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.name}
                </option>
              ))}
            </select>
          </label>
          <label className="onecs-settings-field">
            <span>Başlangıç</span>
            <input
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
            />
          </label>
          <label className="onecs-settings-field">
            <span>Bitiş</span>
            <input
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
            />
          </label>
          <label className="onecs-settings-field">
            <span>Model</span>
            <input
              value={model}
              placeholder="Tüm modeller"
              onChange={(e) => setModel(e.target.value)}
            />
          </label>
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="onecs-settings-metrics">
          <div>
            <span>Giriş tokenı</span>
            <strong>
              {totals.input_tokens == null
                ? "—"
                : Number(totals.input_tokens).toLocaleString("tr-TR")}
            </strong>
          </div>
          <div>
            <span>Çıkış tokenı</span>
            <strong>
              {totals.output_tokens == null
                ? "—"
                : Number(totals.output_tokens).toLocaleString("tr-TR")}
            </strong>
          </div>
          <div>
            <span>Tahmini maliyet</span>
            <strong>
              {totals.estimated_cost == null
                ? "—"
                : `$${Number(totals.estimated_cost).toFixed(4)}`}
            </strong>
          </div>
          <div>
            <span>Çağrı sayısı</span>
            <strong>{totals.calls ?? totals.count ?? "—"}</strong>
          </div>
        </div>
        {loading ? (
          <Loading />
        ) : (
          <div className="onecs-settings-table-wrap">
            <table className="onecs-settings-table">
              <thead>
                <tr>
                  <th>Tarih</th>
                  <th>Bağlantı / model</th>
                  <th>Token</th>
                  <th>Durum</th>
                </tr>
              </thead>
              <tbody>
                {asRows(data?.results).map((row) => (
                  <tr key={row.id}>
                    <td>{dateTime(row.created_at)}</td>
                    <td>
                      <strong>
                        {row.profile_name ||
                          profiles.find(
                            (profile) => profile.id === row.profile_id,
                          )?.name ||
                          "Önceki yapılandırma"}
                      </strong>
                      <small>{row.model}</small>
                      <small>
                        {row.operation === "connection_test"
                          ? "Bağlantı testi"
                          : row.operation === "weekly"
                            ? "Haftalık rapor"
                            : row.operation ||
                              row.purpose ||
                              row.job_type ||
                              "Rapor özeti"}
                      </small>
                    </td>
                    <td>
                      {row.input_tokens == null || row.output_tokens == null
                        ? "Bilinmiyor"
                        : `${row.input_tokens} / ${row.output_tokens}`}
                    </td>
                    <td>
                      <span
                        className={`onecs-settings-pill ${row.status === "success" ? "positive" : "muted"}`}
                      >
                        {(
                          {
                            success: "Başarılı",
                            unknown: "Sonuç bilinmiyor",
                            failure: "Başarısız",
                            pending: "Bekliyor",
                            reserved: "Ayrıldı",
                          } as Record<string, string>
                        )[row.status] ||
                          row.status ||
                          "—"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!asRows(data?.results).length && (
              <Empty
                title="Bu aralıkta AI kullanımı bulunmuyor."
                description="İlk rapor üretiminden sonra model, token ve maliyet ölçümleri burada listelenir."
              />
            )}
          </div>
        )}
      </section>
    </>
  );
}
type DirectoryEntry = {
  subject: string;
  dn: string;
  username?: string;
  display_name?: string;
  email?: string;
  department?: string;
  title?: string;
  manager_dn?: string;
  groups?: string[];
  role_hint?: string;
  directory_enabled?: boolean;
};
type DirectoryBatch = {
  batch_id: string;
  results: DirectoryEntry[];
  configuration_version: number;
  kind: string;
  base_dn: string;
  truncated?: boolean;
};
function LDAPDirectoryPanel() {
  const configuration = useResource<Configuration>("/admin/settings/ldap");
  const { data: orgData } = useResource<any>("/organization");
  const { data: roleData } = useResource<any>("/admin/roles");
  const [kind, setKind] = useState<"users" | "groups">("users"),
    [query, setQuery] = useState(""),
    [baseDN, setBaseDN] = useState(""),
    [baseOptions, setBaseOptions] = useState<string[]>([]),
    [batch, setBatch] = useState<DirectoryBatch | null>(null),
    [selectedSubject, setSelectedSubject] = useState(""),
    [org, setOrg] = useState(""),
    [role, setRole] = useState("EMPLOYEE"),
    [searching, setSearching] = useState(false),
    [busy, setBusy] = useState(false),
    [failure, setFailure] = useState(""),
    [message, setMessage] = useState("");
  const config = configuration.data?.config;
  const searchable = !!(configuration.data?.ready && config?.enabled);
  const entry = batch?.results.find((item) => item.subject === selectedSubject);
  const orgs = asRows(orgData);
  const roles = asRows(roleData?.roles).filter(
    (item) =>
      (item.value || item.code) !== "SYSTEM_ADMIN" &&
      (roleData?.business_grant_allowed || !item.business_role),
  );
  useEffect(() => {
    if (config) {
      setBaseDN(
        (kind === "users"
          ? config.user_search_base
          : config.group_search_base) ||
          config.base_dn ||
          "",
      );
      setBatch(null);
      setSelectedSubject("");
    }
  }, [configuration.data?.version, kind]);
  useEffect(() => {
    if (!searchable || query.trim().length < 2) {
      setBatch(null);
      setSelectedSubject("");
      setSearching(false);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setSearching(true);
      setFailure("");
      setSelectedSubject("");
      api<DirectoryBatch>("/admin/ldap/search", {
        method: "POST",
        signal: controller.signal,
        body: {
          kind,
          query: query.trim(),
          ...(baseDN ? { base_dn: baseDN } : {}),
        },
      })
        .then((result) => {
          if (!controller.signal.aborted) setBatch(result);
        })
        .catch((error) => {
          if (!controller.signal.aborted) {
            setFailure(errorText(error));
            setBatch(null);
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) setSearching(false);
        });
    }, 300);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query, kind, baseDN, searchable]);
  const discover = async () => {
    setBusy(true);
    setFailure("");
    setMessage("");
    try {
      const result = await api<Row>("/admin/ldap/discover", {
        method: "POST",
        body: {},
      });
      const options = Array.isArray(result.base_dns) ? result.base_dns : [];
      setBaseOptions(options);
      if (result.default_base_dn) setBaseDN(result.default_base_dn);
      setMessage(
        options.length
          ? `${options.length} arama kökü sunucudan bulundu.`
          : "Dizin yanıt verdi; arama kökünü yapılandırmadan seçin.",
      );
    } catch (error) {
      setFailure(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  const importEntry = async () => {
    if (!entry || !batch) return;
    setBusy(true);
    setFailure("");
    setMessage("");
    try {
      const result = await api<Row>("/admin/ldap/import", {
        method: "POST",
        body: {
          batch_id: batch.batch_id,
          entries: [{ subject: entry.subject, org_node: org, role }],
          expected_config_version: batch.configuration_version,
        },
      });
      setMessage(
        `${result.count || 1} kullanıcı açık organizasyon ve rol seçimiyle içeri aktarıldı.`,
      );
      setSelectedSubject("");
    } catch (error) {
      setFailure(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="onecs-settings-card onecs-settings-directory">
      <div className="onecs-settings-config-title">
        <div>
          <h3>Dizinden kullanıcı ve grup bul</h3>
          <p>
            Canlı dizin sonucunu inceleyin; organizasyon ve rolü açıkça seçerek
            kullanıcıyı onecs’e alın.
          </p>
        </div>
        <button
          className="onecs-settings-button"
          onClick={discover}
          disabled={busy || !config?.enabled}
        >
          <Network size={15} />
          Dizini keşfet
        </button>
      </div>
      <div className="onecs-settings-directory-body">
        {(failure || message || configuration.error) && (
          <Notice tone={failure || configuration.error ? "error" : "success"}>
            {failure || configuration.error || message}
          </Notice>
        )}
        {!searchable && (
          <Notice>
            Önce LDAP ayarlarını kaydedip gerçek bağlantı testini tamamlayın.
            Arama, doğrulanan yapılandırmayı kullanır.
          </Notice>
        )}
        <div
          className="onecs-settings-subtabs"
          role="tablist"
          aria-label="Dizin arama türü"
        >
          <button
            role="tab"
            aria-selected={kind === "users"}
            className={kind === "users" ? "active" : ""}
            onClick={() => setKind("users")}
          >
            Kullanıcılar
          </button>
          <button
            role="tab"
            aria-selected={kind === "groups"}
            className={kind === "groups" ? "active" : ""}
            onClick={() => setKind("groups")}
          >
            Gruplar
          </button>
        </div>
        <div className="onecs-settings-directory-search">
          <label className="onecs-settings-field">
            <span>Arama kökü</span>
            <select
              value={baseDN}
              disabled={!searchable || busy}
              onChange={(event) => setBaseDN(event.target.value)}
            >
              {[...new Set([baseDN, ...baseOptions].filter(Boolean))].map(
                (value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ),
              )}
              {!baseDN && !baseOptions.length && (
                <option value="">Yapılandırılmış kökü kullan</option>
              )}
            </select>
          </label>
          <label className="onecs-settings-field">
            <span>
              {kind === "users" ? "Ad, kullanıcı adı veya e-posta" : "Grup adı"}
            </span>
            <div className="onecs-settings-search">
              <Search size={16} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                disabled={!searchable || busy}
                placeholder="En az 2 karakterle arayın…"
                aria-label="Canlı dizinde ara"
              />
              {searching && <Loader2 size={15} className="spin" />}
            </div>
          </label>
        </div>
        <label className="onecs-settings-field">
          <span>
            {kind === "users"
              ? "Dizinden kullanıcı seçin"
              : "Dizinden grup seçin"}
          </span>
          <select
            value={selectedSubject}
            onChange={(event) => {
              setSelectedSubject(event.target.value);
              setRole("EMPLOYEE");
              setOrg("");
            }}
            disabled={!batch?.results.length || busy || searching}
          >
            <option value="">
              {searching
                ? "Dizin aranıyor…"
                : batch
                  ? `${batch.results.length} sonuç · profil seçin`
                  : "Arama sonuçları burada listelenir"}
            </option>
            {batch?.results.map((item) => (
              <option key={item.subject} value={item.subject}>
                {item.display_name || item.username || item.dn}
                {item.username ? ` · ${item.username}` : ""}
              </option>
            ))}
          </select>
        </label>
        {entry && (
          <div className="onecs-settings-directory-preview">
            <div className="onecs-settings-directory-profile">
              <div className="onecs-settings-directory-avatar">
                <Users size={25} />
              </div>
              <div>
                <h4>{entry.display_name || entry.username || "Dizin kaydı"}</h4>
                <p>{entry.username || "Grup kaydı"}</p>
              </div>
              <span
                className={`onecs-settings-pill ${entry.directory_enabled === false ? "warning" : "muted"}`}
              >
                {entry.directory_enabled === false
                  ? "Dizinde devre dışı"
                  : "LDAP profili"}
              </span>
              <dl>
                <div>
                  <dt>E-posta</dt>
                  <dd>{entry.email || "Dizinde belirtilmedi"}</dd>
                </div>
                <div>
                  <dt>Departman</dt>
                  <dd>{entry.department || "Dizinde belirtilmedi"}</dd>
                </div>
                <div>
                  <dt>Unvan</dt>
                  <dd>{entry.title || "Dizinde belirtilmedi"}</dd>
                </div>
                {entry.role_hint && (
                  <div>
                    <dt>Dizindeki görev bilgisi</dt>
                    <dd>{roleLabels[entry.role_hint] || entry.role_hint}</dd>
                  </div>
                )}
                <div>
                  <dt>Yönetici</dt>
                  <dd>{entry.manager_dn || "Dizinde belirtilmedi"}</dd>
                </div>
                <div className="full">
                  <dt>Dizin kimliği</dt>
                  <dd>{entry.dn}</dd>
                </div>
                {!!entry.groups?.length && (
                  <div className="full">
                    <dt>Grup üyelikleri</dt>
                    <dd>{entry.groups?.join(" · ")}</dd>
                  </div>
                )}
              </dl>
            </div>
            {kind === "users" ? (
              <div className="onecs-settings-directory-review">
                <h4>onecs yetkisini gözden geçir</h4>
                <p>
                  Departman, unvan veya grup üyeliği otomatik yönetici yetkisi
                  vermez. Seçim denetim kaydına yazılır.
                </p>
                <label className="onecs-settings-field">
                  <span>Organizasyon birimi</span>
                  <select
                    required
                    value={org}
                    onChange={(event) => setOrg(event.target.value)}
                    disabled={busy}
                  >
                    <option value="">Birim seçin</option>
                    {orgs.map((node) => (
                      <option key={node.id} value={node.id}>
                        {node.code} · {node.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="onecs-settings-field">
                  <span>onecs rolü</span>
                  <select
                    value={role}
                    onChange={(event) => setRole(event.target.value)}
                    disabled={busy}
                  >
                    {roles.map((item) => (
                      <option
                        key={item.value || item.code}
                        value={item.value || item.code}
                      >
                        {roleLabels[item.value || item.code] || item.label}
                      </option>
                    ))}
                  </select>
                </label>
                {!roleData?.business_grant_allowed && (
                  <small>
                    İş yönetimi rolleri için ayrıca direktör yetkisi gerekir.
                  </small>
                )}
                <button
                  className="onecs-settings-button primary"
                  disabled={
                    busy || !org || !role || entry.directory_enabled === false
                  }
                  onClick={importEntry}
                >
                  {busy ? (
                    <Loader2 size={15} className="spin" />
                  ) : (
                    <Plus size={15} />
                  )}
                  Kullanıcıyı içeri aktar
                </button>
              </div>
            ) : (
              <div className="onecs-settings-directory-review">
                <h4>Grup görünümü</h4>
                <p>
                  Grubun tam DN değerini ilk giriş grup eşlemelerinde
                  kullanabilirsiniz. Bu arama tek başına hesap veya rol
                  oluşturmaz.
                </p>
              </div>
            )}
          </div>
        )}
        {batch?.truncated && (
          <Notice>
            İlk 100 sonuç gösteriliyor. Daha dar bir arama ifadesiyle doğru
            kişiyi seçin.
          </Notice>
        )}
        {batch && !batch.results.length && !searching && (
          <Empty
            title="Dizinde eşleşen kayıt bulunamadı."
            description="Arama ifadesini, kök DN ve filtreyi kontrol edin."
          />
        )}
      </div>
    </section>
  );
}

function IntegrationsPanel() {
  const [ldapRevision, setLdapRevision] = useState(0);
  const [selected, setSelected] = useState<"ldap" | "smtp" | "teams">("ldap");
  return (
    <>
      <Heading
        icon={Network}
        title="Entegrasyonlar"
        description="Kimlik ve iletişim bağlantılarını aynı çalışma alanından yönetin."
      />
      <div className="onecs-settings-integration-switch">
        {[
          {
            id: "ldap" as const,
            label: "LDAP / Active Directory",
            icon: KeyRound,
          },
          { id: "smtp" as const, label: "E-posta / SMTP", icon: Mail },
          { id: "teams" as const, label: "Microsoft Teams", icon: Network },
        ].map((item) => (
          <button
            key={item.id}
            className={selected === item.id ? "active" : ""}
            onClick={() => setSelected(item.id)}
          >
            <item.icon size={20} />
            <span>{item.label}</span>
            <ChevronRight size={15} />
          </button>
        ))}
      </div>
      {selected === "ldap" ? (
        <>
          <ConfigPanel
            key={`ldap-${ldapRevision}`}
            section="ldap"
            title="Kurumsal kimlik bağlantısı"
            description="Sistem kullanıcıları LDAP bağlantısından bağımsız çalışmaya devam eder."
            fields={ldapFields}
            onSaved={() => setLdapRevision((value) => value + 1)}
            onTested={() => setLdapRevision((value) => value + 1)}
          />
          <LDAPLoginMappings
            key={`ldap-mappings-${ldapRevision}`}
            onSaved={() => setLdapRevision((value) => value + 1)}
          />
          <LDAPDirectoryPanel key={ldapRevision} />
        </>
      ) : selected === "smtp" ? (
        <ConfigPanel
          key="smtp"
          section="smtp"
          title="E-posta bildirim bağlantısı"
          description="Atanan kullanıcıların doğrulanmış e-posta adreslerine bildirim gönderilir."
          fields={smtpFields}
        />
      ) : (
        <ConfigPanel
          key="teams"
          section="teams"
          title="Teams bildirim bağlantısı"
          description="Anons ve etkinlikler, seçili hedef görünürlüğüyle Teams'e aktarılır."
          fields={teamsFields}
        />
      )}
    </>
  );
}

const priorityLabels: Record<string, string> = {
  CRITICAL: "Kritik",
  HIGH: "Yüksek",
  NORMAL: "Normal",
};
const slaUnitLabels: Record<string, string> = {
  HOURS: "geçen saat",
  DAYS: "takvim günü",
  MONTHS: "takvim ayı",
};
const contextLabels: Record<string, string> = {
  ALL: "Unit işleri ve vakalar",
  UNIT_WORK: "Unit işleri",
  CASE: "Vakalar",
};
function SLAPanel() {
  const { data, loading, error, refresh } = useResource<any>("/sla-policies");
  const [editing, setEditing] = useState<Row | null>(null),
    [busy, setBusy] = useState(false),
    [failure, setFailure] = useState("");
  const policies = asRows(data);
  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!editing) return;
    setBusy(true);
    setFailure("");
    try {
      await api(`/sla-policies/${editing.id}`, {
        method: "PATCH",
        body: {
          version: editing.version,
          amount: editing.amount,
          unit: editing.unit,
          warning_percent: editing.warning_percent,
          reason: editing.reason,
        },
      });
      setEditing(null);
      refresh();
    } catch (err) {
      setFailure(errorText(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Heading
        icon={Clock3}
        title="SLA politikaları"
        description="Unit işleri ve resmî vakalar için sürümlü iç tamamlama hedeflerini yönetin."
      />
      <Notice>
        Politika değişikliği mevcut işlerin hedef tarihini değiştirmez. Yeniden
        atama ve yeniden açma süreyi sıfırlamaz; tarihsel ihlal korunur.
      </Notice>
      <section className="onecs-settings-card">
        <div className="onecs-settings-config-title">
          <div>
            <h3>Yayınlanmış hedefler</h3>
            <p>
              İlk yanıt ve müdahale hedeflerinden ayrı, 7/24 takvim esaslı
              tamamlama süreleridir.
            </p>
          </div>
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        {loading ? (
          <Loading />
        ) : (
          <>
            <div className="onecs-settings-table-wrap">
              <table className="onecs-settings-table">
                <thead>
                  <tr>
                    <th>Politika</th>
                    <th>Kapsam</th>
                    <th>Öncelik</th>
                    <th>Hedef / Uyarı</th>
                    <th>Sürüm</th>
                    <th className="right">İşlem</th>
                  </tr>
                </thead>
                <tbody>
                  {policies.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <strong>
                          {priorityLabels[row.priority] || row.priority}{" "}
                          tamamlama hedefi
                        </strong>
                      </td>
                      <td>{contextLabels[row.context] || row.context}</td>
                      <td>
                        <span
                          className={`onecs-settings-pill ${row.priority === "CRITICAL" ? "warning" : "muted"}`}
                        >
                          {priorityLabels[row.priority] || row.priority}
                        </span>
                      </td>
                      <td>
                        {row.amount} {slaUnitLabels[row.unit] || row.unit}
                        <small>
                          Süre %{row.warning_percent} dolduğunda uyarı
                        </small>
                      </td>
                      <td>{row.version}</td>
                      <td className="right">
                        <button
                          className="onecs-settings-icon-button"
                          onClick={() => {
                            setFailure("");
                            setEditing({ ...row, reason: "" });
                          }}
                          aria-label={`${priorityLabels[row.priority] || row.priority} politikasını düzenle`}
                        >
                          <Pencil size={15} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!policies.length && (
              <Empty
                title="Yayınlanmış politika bulunmuyor."
                description="Başlangıç politikaları: Kritik 24 saat, yüksek 7 gün, normal 1 takvim ayı. Kaynak yapılandırmasını kontrol edin."
              />
            )}
          </>
        )}
        <div className="onecs-settings-sla-note">
          <Clock3 size={17} />
          <p>
            <strong>Takvim ayı hesabı:</strong> 31 Ocak + 1 ay, Şubat'ın son
            gününe taşınır. Bekleme ve kapanış doğrulaması sırasında sayaç
            işlemeye devam eder.
          </p>
        </div>
      </section>
      {editing && (
        <Modal
          title="SLA politikasını güncelle"
          description="Değişiklik yeni politika sürümü oluşturur. Mevcut taahhütler önceki hedeflerini korur."
          onClose={() => setEditing(null)}
          busy={busy}
        >
          <form onSubmit={save}>
            {failure && <Notice tone="error">{failure}</Notice>}
            <div className="onecs-settings-form-grid">
              <label className="onecs-settings-field">
                <span>Hedef miktarı</span>
                <input
                  type="number"
                  min="1"
                  max="3650"
                  required
                  value={editing.amount}
                  onChange={(event) =>
                    setEditing({
                      ...editing,
                      amount: Number(event.target.value),
                    })
                  }
                />
              </label>
              <label className="onecs-settings-field">
                <span>Zaman birimi</span>
                <select
                  value={editing.unit}
                  onChange={(event) =>
                    setEditing({ ...editing, unit: event.target.value })
                  }
                >
                  <option value="HOURS">Geçen saat</option>
                  <option value="DAYS">Takvim günü</option>
                  <option value="MONTHS">Takvim ayı</option>
                </select>
              </label>
              <label className="onecs-settings-field">
                <span>Uyarı eşiği (%)</span>
                <input
                  type="number"
                  min="1"
                  max="99"
                  required
                  value={editing.warning_percent}
                  onChange={(event) =>
                    setEditing({
                      ...editing,
                      warning_percent: Number(event.target.value),
                    })
                  }
                />
                <small>
                  İhlal bildirimi ayrıca hedef süresi dolduğunda üretilir.
                </small>
              </label>
              <label className="onecs-settings-field">
                <span>Güncelleme gerekçesi</span>
                <input
                  required
                  maxLength={1000}
                  value={editing.reason}
                  onChange={(event) =>
                    setEditing({ ...editing, reason: event.target.value })
                  }
                />
              </label>
            </div>
            <footer className="onecs-settings-modal-footer">
              <button
                type="button"
                className="onecs-settings-button"
                onClick={() => setEditing(null)}
                disabled={busy}
              >
                Vazgeç
              </button>
              <button className="onecs-settings-button primary" disabled={busy}>
                Yeni sürümü kaydet
              </button>
            </footer>
          </form>
        </Modal>
      )}
    </>
  );
}

function LogsPanel() {
  const [level, setLevel] = useState(""),
    [query, setQuery] = useState("");
  const { data, loading, error, refresh } = useResource<any>(
    `/admin/audit?action=${encodeURIComponent(query)}`,
  );
  const rows = asRows(data);
  return (
    <>
      <Heading
        icon={FileText}
        title="Günlükler ve denetim izi"
        description="Kullanıcı işlemlerinin ve güvenlik kararlarının denetim izini takip edin."
        actions={
          <button className="onecs-settings-button" onClick={refresh}>
            <RefreshCw size={15} />
            Yenile
          </button>
        }
      />
      <div className="onecs-settings-toolbar onecs-settings-card">
        <div className="onecs-settings-search">
          <Search size={17} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="İşlem, kullanıcı veya kayıt ara…"
            aria-label="Günlüklerde ara"
          />
        </div>
        <select
          aria-label="Günlük seviyesi"
          value={level}
          onChange={(e) => setLevel(e.target.value)}
        >
          <option value="">Tüm seviyeler</option>
          <option value="info">Info · denetim olayları</option>
        </select>
      </div>
      <section className="onecs-settings-card">
        {error && <Notice tone="error">{error}</Notice>}
        {loading ? (
          <Loading />
        ) : (
          <>
            <div className="onecs-settings-table-wrap">
              <table className="onecs-settings-table">
                <thead>
                  <tr>
                    <th>Tarih</th>
                    <th>Aktör</th>
                    <th>İşlem</th>
                    <th>Kaynak</th>
                    <th>Seviye</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id}>
                      <td className="nowrap">
                        {dateTime(row.created_at || row.timestamp)}
                      </td>
                      <td>
                        {row.actor_name ||
                          (typeof row.actor === "string"
                            ? row.actor
                            : row.actor?.display_name || row.actor?.username) ||
                          row.actor_id ||
                          "Sistem"}
                      </td>
                      <td>
                        <strong>
                          {row.action || row.event_type || row.message}
                        </strong>
                        {row.reason && <small>{row.reason}</small>}
                      </td>
                      <td>
                        {row.object_type ||
                          row.resource_type ||
                          row.entity_type ||
                          "—"}
                        <small>
                          {row.object_id ||
                            row.resource_id ||
                            row.entity_id ||
                            ""}
                        </small>
                      </td>
                      <td>
                        <span
                          className={`onecs-settings-pill ${["error", "warning"].includes(row.level) ? "warning" : "muted"}`}
                        >
                          {row.level || "info"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!rows.length && (
              <Empty title="Bu filtrelerle günlük bulunamadı." />
            )}
          </>
        )}
        <p className="onecs-settings-footnote padded">
          Bu görünüm denetim metaverisini gösterir. Teknik debug / warning /
          error log akışı ayrıca yapılandırılır. Parola, token ve hassas ham AI
          içeriği gösterilmez.
        </p>
      </section>
    </>
  );
}
const jobStatusLabels: Record<string, string> = {
  PENDING: "Bekliyor",
  RUNNING: "Çalışıyor",
  COMPLETED: "Tamamlandı",
  FAILED: "Başarısız",
  RETRY: "Yeniden denenecek",
  CANCELLED: "İptal edildi",
  SENDING: "Gönderiliyor",
  SENT: "Gönderildi",
  UNKNOWN: "Teslim sonucu belirsiz",
  WAITING_CONFIGURATION: "Yapılandırma bekliyor",
  BLOCKED: "Engellendi",
};
function JobsPanel() {
  const [status, setStatus] = useState(""),
    [kind, setKind] = useState("");
  const { data, loading, error, refresh } = useResource<any>(
    `/admin/jobs?status=${status}&kind=${kind}`,
  );
  const [retryTarget, setRetryTarget] = useState<Row | null>(null),
    [acknowledge, setAcknowledge] = useState(false),
    [reason, setReason] = useState(""),
    [busy, setBusy] = useState(false),
    [failure, setFailure] = useState("");
  const retry = async (event: FormEvent) => {
    event.preventDefault();
    if (!retryTarget) return;
    setBusy(true);
    setFailure("");
    try {
      await api(`/admin/jobs/${retryTarget.id}/retry`, {
        method: "POST",
        body: {
          kind: retryTarget.kind,
          version: retryTarget.version,
          reason,
          acknowledge_unknown: acknowledge,
        },
      });
      setRetryTarget(null);
      refresh();
    } catch (err) {
      setFailure(errorText(err));
    } finally {
      setBusy(false);
    }
  };
  const canRetry = (row: Row) =>
    row.kind === "job"
      ? row.status === "FAILED"
      : ["FAILED", "UNKNOWN", "WAITING_CONFIGURATION", "BLOCKED"].includes(
          row.status,
        );
  const rows = asRows(data);
  return (
    <>
      <Heading
        icon={Activity}
        title="Kalıcı iş kuyruğu"
        description="Rapor üretimi, bildirim ve SLA işlemleri kesinti sonrasında kayıtlı aşamadan devam eder."
        actions={
          <button className="onecs-settings-button" onClick={refresh}>
            <RefreshCw size={15} />
            Yenile
          </button>
        }
      />
      <div className="onecs-settings-toolbar onecs-settings-card">
        <label className="onecs-settings-field">
          <span>İş türü</span>
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value)}
          >
            <option value="">Tümü</option>
            <option value="job">Arka plan işleri</option>
            <option value="outbox">Bildirim kuyruğu</option>
          </select>
        </label>
        <label className="onecs-settings-field">
          <span>Durum</span>
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="">Tüm durumlar</option>
            {Object.entries(jobStatusLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <section className="onecs-settings-card">
        {error && <Notice tone="error">{error}</Notice>}
        {loading ? (
          <Loading />
        ) : (
          <>
            <div className="onecs-settings-table-wrap">
              <table className="onecs-settings-table">
                <thead>
                  <tr>
                    <th>İş</th>
                    <th>Durum</th>
                    <th>Deneme</th>
                    <th>Son güncelleme</th>
                    <th className="right">İşlem</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={`${row.kind}:${row.id}`}>
                      <td>
                        <strong>
                          {row.task_kind || row.job_type || row.type}
                        </strong>
                        <small>
                          {row.kind === "outbox"
                            ? "Bildirim kuyruğu"
                            : "Arka plan işi"}{" "}
                          · {row.id}
                        </small>
                        {row.last_error && (
                          <small className="onecs-settings-error-text">
                            {row.last_error}
                          </small>
                        )}
                      </td>
                      <td>
                        <span
                          className={`onecs-settings-pill ${["COMPLETED", "SENT"].includes(row.status) ? "positive" : ["FAILED", "UNKNOWN", "BLOCKED"].includes(row.status) ? "warning" : "muted"}`}
                        >
                          {jobStatusLabels[row.status] || row.status}
                        </span>
                        {row.next_attempt_at && (
                          <small>
                            Sonraki deneme {dateTime(row.next_attempt_at)}
                          </small>
                        )}
                      </td>
                      <td>{row.attempts ?? 0}</td>
                      <td>{dateTime(row.updated_at || row.created_at)}</td>
                      <td className="right">
                        {canRetry(row) ? (
                          <button
                            className="onecs-settings-button small"
                            onClick={() => {
                              setRetryTarget(row);
                              setAcknowledge(false);
                              setReason("");
                              setFailure("");
                            }}
                          >
                            <RefreshCw size={13} />
                            Yeniden dene
                          </button>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!rows.length && (
              <Empty
                title="Bu filtrelerde iş bulunmuyor."
                description="Rapor ve bildirim işlemlerinin kalıcı durumları burada görünür."
              />
            )}
          </>
        )}
      </section>
      {retryTarget && (
        <Modal
          title="İşi yeniden denemeye al"
          description="Deneme, yetkili işlem olarak denetim kaydına yazılır."
          onClose={() => setRetryTarget(null)}
          busy={busy}
        >
          <form onSubmit={retry}>
            {failure && <Notice tone="error">{failure}</Notice>}
            {retryTarget.status === "UNKNOWN" && (
              <Notice>
                Önceki SMTP isteğinin teslim sonucu belirsiz. Sunucu iletiyi
                daha önce kabul etmiş olabilir; yeniden deneme aynı bildirimin
                ikinci kez ulaşmasına yol açabilir.
              </Notice>
            )}
            <label className="onecs-settings-field">
              <span>Yeniden deneme gerekçesi</span>
              <input
                required
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                maxLength={500}
                placeholder="Örn. SMTP bağlantısı düzeltildi."
              />
            </label>
            {retryTarget.status === "UNKNOWN" && (
              <label className="onecs-settings-acknowledgment">
                <input
                  type="checkbox"
                  required
                  checked={acknowledge}
                  onChange={(event) => setAcknowledge(event.target.checked)}
                />
                Olası mükerrer bildirimi değerlendirerek bu teslimatı yeniden
                denemeye alıyorum.
              </label>
            )}
            <footer className="onecs-settings-modal-footer">
              <button
                type="button"
                className="onecs-settings-button"
                onClick={() => setRetryTarget(null)}
                disabled={busy}
              >
                Vazgeç
              </button>
              <button
                className="onecs-settings-button primary"
                disabled={
                  busy || (retryTarget.status === "UNKNOWN" && !acknowledge)
                }
              >
                {busy ? "Kuyruğa alınıyor…" : "Yeniden denemeye al"}
              </button>
            </footer>
          </form>
        </Modal>
      )}
    </>
  );
}

const apiScopes = [
  { value: "dashboard:read", label: "Dashboard" },
  { value: "organization:read", label: "Organizasyon" },
  { value: "people:read", label: "Kişiler" },
  { value: "projects:read", label: "Projeler" },
  { value: "work:read", label: "İşler" },
  { value: "cases:read", label: "Vakalar" },
  { value: "credentials:read", label: "Sertifikalar" },
  { value: "community:read", label: "CS paylaşımları" },
  { value: "events:read", label: "Etkinlikler" },
];
function APIPanel() {
  const { data, loading, error, refresh } = useResource<any>("/api-clients");
  const { data: orgData } = useResource<any>("/organization");
  const clients = asRows(data),
    orgs = asRows(orgData?.nodes || orgData);
  const [creating, setCreating] = useState(false),
    [name, setName] = useState(""),
    [org, setOrg] = useState(""),
    [scopes, setScopes] = useState<string[]>(["dashboard:read"]),
    [busy, setBusy] = useState(""),
    [failure, setFailure] = useState(""),
    [token, setToken] = useState<Row | null>(null),
    [copied, setCopied] = useState(false);
  const create = async (event: FormEvent) => {
    event.preventDefault();
    setBusy("create");
    setFailure("");
    try {
      const result = await api<Row>("/api-clients", {
        method: "POST",
        body: { name, scopes, org_node_id: org || null },
      });
      setCreating(false);
      setName("");
      setScopes(["dashboard:read"]);
      setToken(result);
      setCopied(false);
      refresh();
    } catch (err) {
      setFailure(errorText(err));
    } finally {
      setBusy("");
    }
  };
  const clientAction = async (client: Row, action: "token" | "revoke") => {
    setBusy(client.id);
    setFailure("");
    try {
      const result = await api<Row>(`/api-clients/${client.id}/${action}`, {
        method: "POST",
        body: { version: client.version },
      });
      if (action === "token") {
        setToken({ ...result, name: client.name });
        setCopied(false);
      }
      refresh();
    } catch (err) {
      setFailure(errorText(err));
    } finally {
      setBusy("");
    }
  };
  return (
    <>
      <Heading
        icon={Code2}
        title="API erişimi"
        description="onecs özetlerine kapsamlı ve denetlenebilir salt okunur erişim sağlayın."
        actions={
          <button
            className="onecs-settings-button primary"
            onClick={() => {
              setFailure("");
              setCreating(true);
            }}
          >
            <Plus size={15} />
            İstemci oluştur
          </button>
        }
      />
      <Notice>
        Dış API erişimi kısa ömürlü JWT ve istemci kapsamıyla sınırlandırılır.
        İstemci yalnız sizin güncel iş erişiminizin izin verdiği kayıtları
        okuyabilir.
      </Notice>
      {failure && !creating && <Notice tone="error">{failure}</Notice>}
      <section className="onecs-settings-card">
        <div className="onecs-settings-config-title">
          <div>
            <h3>Entegrasyon istemcileri</h3>
            <p>
              Tokenlar 15 dakika geçerlidir. İptal işlemi bu istemcinin geçerli
              tokenlarını da sonlandırır.
            </p>
          </div>
          <button className="onecs-settings-button small" onClick={refresh}>
            <RefreshCw size={13} />
            Yenile
          </button>
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        {loading ? (
          <Loading />
        ) : (
          <>
            <div className="onecs-settings-table-wrap">
              <table className="onecs-settings-table">
                <thead>
                  <tr>
                    <th>İstemci</th>
                    <th>İzinler</th>
                    <th>Durum</th>
                    <th className="right">İşlem</th>
                  </tr>
                </thead>
                <tbody>
                  {clients.map((client) => (
                    <tr key={client.id}>
                      <td>
                        <strong>{client.name}</strong>
                        <small>
                          {orgs.find((org) => org.id === client.org_node_id)
                            ?.code || "Kullanıcının yetkili kapsamı"}
                        </small>
                      </td>
                      <td>
                        <div className="onecs-settings-scope-tags">
                          {(client.scopes || []).map((scope: string) => (
                            <span
                              key={scope}
                              className="onecs-settings-pill muted"
                            >
                              {apiScopes.find((item) => item.value === scope)
                                ?.label || scope}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td>
                        <span
                          className={`onecs-settings-pill ${client.active ? "positive" : "muted"}`}
                        >
                          {client.active ? "Aktif" : "İptal edildi"}
                        </span>
                      </td>
                      <td className="right">
                        {client.active && (
                          <div className="onecs-settings-row-actions">
                            <button
                              className="onecs-settings-button small"
                              onClick={() => clientAction(client, "token")}
                              disabled={busy === client.id}
                            >
                              <KeyRound size={13} />
                              Token üret
                            </button>
                            <button
                              className="onecs-settings-button small danger"
                              onClick={() => clientAction(client, "revoke")}
                              disabled={busy === client.id}
                            >
                              İptal et
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!clients.length && (
              <Empty
                title="Henüz API istemcisi yok."
                description="Salt okunur kapsamları seçerek ilk entegrasyon istemcinizi oluşturun."
              />
            )}
          </>
        )}
      </section>
      <section className="onecs-settings-card">
        <div className="onecs-settings-config-title">
          <div>
            <h3>Geliştirici belgeleri</h3>
            <p>OpenAPI şeması, uç noktalar ve örnek yanıtlar.</p>
          </div>
          <Code2 size={21} />
        </div>
        <div className="onecs-settings-api-links">
          <a href="/api/v1/docs/" target="_blank" rel="noreferrer">
            <span className="onecs-settings-title-icon">
              <BookOpen size={22} />
            </span>
            <div>
              <strong>Swagger UI</strong>
              <p>API sözleşmesini ve parametreleri inceleyin.</p>
            </div>
            <ExternalLink size={16} />
          </a>
          <a href="/api/v1/schema/" target="_blank" rel="noreferrer">
            <span className="onecs-settings-title-icon">
              <Code2 size={22} />
            </span>
            <div>
              <strong>OpenAPI şeması</strong>
              <p>Makine tarafından okunabilir API tanımı.</p>
            </div>
            <ExternalLink size={16} />
          </a>
        </div>
      </section>
      {creating && (
        <Modal
          title="API istemcisi oluştur"
          description="İstemci yetkileri, sizin kaynak erişiminizle birlikte değerlendirilir."
          onClose={() => setCreating(false)}
          busy={!!busy}
        >
          <form onSubmit={create}>
            {failure && <Notice tone="error">{failure}</Notice>}
            <div className="onecs-settings-form-grid">
              <label className="onecs-settings-field">
                <span>İstemci adı</span>
                <input
                  required
                  maxLength={180}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Örn. Yönetim raporu entegrasyonu"
                />
              </label>
              <label className="onecs-settings-field">
                <span>Organizasyon sınırı</span>
                <select value={org} onChange={(e) => setOrg(e.target.value)}>
                  <option value="">Kendi yetkili kapsamım</option>
                  {orgs.map((node) => (
                    <option key={node.id} value={node.id}>
                      {node.code || node.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <fieldset className="onecs-settings-scopes-fieldset">
              <legend>Salt okunur izinler</legend>
              {apiScopes.map((scope) => (
                <label key={scope.value}>
                  <input
                    type="checkbox"
                    checked={scopes.includes(scope.value)}
                    onChange={(event) =>
                      setScopes((previous) =>
                        event.target.checked
                          ? [...previous, scope.value]
                          : previous.filter((value) => value !== scope.value),
                      )
                    }
                  />
                  {scope.label}
                </label>
              ))}
            </fieldset>
            <footer className="onecs-settings-modal-footer">
              <button
                type="button"
                className="onecs-settings-button"
                onClick={() => setCreating(false)}
                disabled={!!busy}
              >
                Vazgeç
              </button>
              <button
                className="onecs-settings-button primary"
                disabled={!!busy || !scopes.length}
              >
                İstemciyi oluştur
              </button>
            </footer>
          </form>
        </Modal>
      )}
      {token && (
        <Modal
          title="Erişim tokenı hazır"
          description={`${token.name || "İstemci"} · ${Math.floor((token.expires_in || 900) / 60)} dakika geçerli`}
          onClose={() => setToken(null)}
        >
          <div className="onecs-settings-token-content">
            <Notice>
              Bu tokenı güvenli bir yerde saklayın. Pencere kapatıldıktan sonra
              değer tekrar gösterilmez; yeni token üretebilirsiniz.
            </Notice>
            <label className="onecs-settings-field">
              <span>Bearer token</span>
              <textarea
                readOnly
                rows={5}
                value={token.token}
                onFocus={(event) => event.target.select()}
                spellCheck={false}
              />
            </label>
            <footer className="onecs-settings-modal-footer">
              <button
                className="onecs-settings-button"
                onClick={() => setToken(null)}
              >
                Kapat
              </button>
              <button
                className="onecs-settings-button primary"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(token.token);
                    setCopied(true);
                  } catch {
                    setCopied(false);
                    setFailure("Tokenı alandan seçip manuel kopyalayın.");
                  }
                }}
              >
                {copied ? <Check size={15} /> : <KeyRound size={15} />}{" "}
                {copied ? "Kopyalandı" : "Tokenı kopyala"}
              </button>
            </footer>
          </div>
        </Modal>
      )}
    </>
  );
}

function TestModePanel() {
  const auth = useAuth();
  const { data, loading, error, refresh } = useResource<Row>("/test-mode");
  const { data: peopleData } = useResource<any>("/people");
  const [selectedUser, setSelectedUser] = useState(""),
    [busy, setBusy] = useState(false),
    [failure, setFailure] = useState("");
  const change = async (mode: "god" | "simulate" | "stop") => {
    setBusy(true);
    setFailure("");
    try {
      await api("/test-mode", {
        method: "POST",
        body: {
          mode,
          ...(mode === "simulate" ? { user_id: selectedUser } : {}),
        },
      });
      refresh();
      auth.refresh();
    } catch (err) {
      setFailure(errorText(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Heading
        icon={ShieldCheck}
        title="Test ortamı ve kullanıcı görünümü"
        description="Sentetik verilerle rol sınırlarını ve akışları kontrollü biçimde deneyin."
      />
      {(error || failure) && <Notice tone="error">{failure || error}</Notice>}
      {loading && !data ? (
        <Loading />
      ) : (
        <section className="onecs-settings-card">
          <div className="onecs-settings-config-title">
            <div>
              <h3>Sunucu tarafından uygulanan test sınırı</h3>
              <p>
                Ortam: <strong>{data?.environment || "Bilinmiyor"}</strong> ·
                Gerçek aktör ve denenen kullanıcı ayrı kaydedilir.
              </p>
            </div>
            <span
              className={`onecs-settings-pill ${data?.available ? "positive" : "muted"}`}
            >
              {data?.available ? "Sentetik test etkin" : "Bu ortamda kapalı"}
            </span>
          </div>
          <div className="onecs-settings-test-content">
            {!data?.available ? (
              <Notice>
                God Mode ve kullanıcı denemesi yalnız test / demo ortamında
                deployment izniyle açılır. Bu güvenlik sınırı ayarlar ekranından
                kaldırılamaz.
              </Notice>
            ) : (
              <Notice>
                Kullanıcı görünümünü denerken God Mode devre dışı kalır.
                Sonuçlar, seçilen kişinin gerçek yetki sınırlarını kullanır.
              </Notice>
            )}
            <div className="onecs-settings-two-columns">
              <section className="onecs-settings-test-option">
                <span className="onecs-settings-title-icon">
                  <Users size={22} />
                </span>
                <h3>Kullanıcı görünümünü dene</h3>
                <p>
                  Çalışan veya yönetici hesabının erişebildiği ekranları ve
                  kayıtları kontrol edin.
                </p>
                <label className="onecs-settings-field">
                  <span>Denecek kullanıcı</span>
                  <select
                    value={selectedUser}
                    onChange={(event) => setSelectedUser(event.target.value)}
                    disabled={!data?.available || busy}
                  >
                    <option value="">Kullanıcı seçin</option>
                    {asRows(peopleData).map((person) => (
                      <option key={person.id} value={person.id}>
                        {displayName(person)}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  className="onecs-settings-button"
                  onClick={() => change("simulate")}
                  disabled={!data?.available || busy || !selectedUser}
                >
                  Görünümü başlat
                </button>
              </section>
              <section className="onecs-settings-test-option">
                <span className="onecs-settings-title-icon">
                  <ShieldCheck size={22} />
                </span>
                <h3>God Mode</h3>
                <p>
                  Sentetik testlerde kaynak erişim sınırlarını aşarak test
                  verisini inceleyin. Her işlem gerçek yöneticiyle denetlenir.
                </p>
                <span
                  className={`onecs-settings-pill ${data?.god_mode ? "warning" : "muted"}`}
                >
                  {data?.god_mode ? "God Mode etkin" : "God Mode kapalı"}
                </span>
                <button
                  className="onecs-settings-button"
                  onClick={() => change("god")}
                  disabled={!data?.available || busy || !!data?.god_mode}
                >
                  Test yetkisini etkinleştir
                </button>
              </section>
            </div>
            {(data?.god_mode || data?.effective_user_id) && (
              <div className="onecs-settings-form-footer">
                <button
                  className="onecs-settings-button primary"
                  onClick={() => change("stop")}
                  disabled={busy}
                >
                  Test görünümünü sonlandır
                </button>
              </div>
            )}
          </div>
        </section>
      )}
    </>
  );
}

export default function Settings() {
  const [active, setActive] = useState<Section>("users");
  const content = useMemo(() => {
    switch (active) {
      case "general":
        return (
          <>
            <Heading
              icon={Settings2}
              title="Genel yapılandırma"
              description="Çalışma alanı ve yönetim politikasının ortak ayarları."
            />
            <ConfigPanel
              section="general"
              title="onecs çalışma alanı"
              description="Organizasyon adı, rapor dönemi ve temel politika seçenekleri."
              fields={generalFields}
              canTest={false}
            />
          </>
        );
      case "users":
        return <UsersPanel />;
      case "organization":
        return <OrganizationPanel />;
      case "sla":
        return <SLAPanel />;
      case "ai":
        return <AIPanel />;
      case "integrations":
        return <IntegrationsPanel />;
      case "api":
        return <APIPanel />;
      case "logs":
        return <LogsPanel />;
      case "jobs":
        return <JobsPanel />;
      case "testing":
        return <TestModePanel />;
    }
  }, [active]);
  return (
    <div className="onecs-settings">
      <header className="onecs-settings-page-header">
        <div>
          <div className="onecs-settings-eyebrow">ÇALIŞMA ALANI YÖNETİMİ</div>
          <h1>Ayarlar</h1>
          <p>
            Kullanıcıları, modelleri ve bağlantıları tek çalışma alanından
            yönetin.
          </p>
        </div>
        <a
          className="onecs-settings-button"
          href="/api/v1/docs/"
          target="_blank"
          rel="noreferrer"
        >
          <BookOpen size={16} />
          API rehberi
        </a>
      </header>
      <nav className="onecs-settings-tabs" aria-label="Ayarlar bölümleri">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActive(tab.id)}
            className={active === tab.id ? "active" : ""}
            aria-current={active === tab.id ? "page" : undefined}
          >
            <tab.icon size={15} />
            {tab.label}
          </button>
        ))}
      </nav>
      <div className="onecs-settings-content" key={active}>
        {content}
      </div>
    </div>
  );
}
