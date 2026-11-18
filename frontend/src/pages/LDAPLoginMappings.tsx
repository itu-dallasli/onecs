import { useState, type FormEvent } from "react";
import { CircleAlert, Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { api, list, useResource } from "../lib/api";
import { useAuth } from "../lib/auth";
import "../styles/ldap-login-mappings.css";

const roles = [
  { value: "EMPLOYEE", label: "Çalışan" },
  { value: "TEAM_MANAGER", label: "Ekip yöneticisi" },
  { value: "UNIT_HEAD", label: "Birim yöneticisi" },
  { value: "DIRECTOR", label: "Direktör" },
  { value: "PROJECT_MANAGER", label: "Proje yöneticisi" },
] as const;
type Mapping = {
  group_dn: string;
  org_node: string;
  role: (typeof roles)[number]["value"];
  includes_descendants: boolean;
};
type Configuration = {
  version: number;
  config: { group_role_mappings?: Mapping[] };
};
type Organization = { id: string; name: string; code: string };
type Editor = { index: number | null; version: number; value: Mapping };
const emptyMapping = (): Mapping => ({
  group_dn: "",
  org_node: "",
  role: "EMPLOYEE",
  includes_descendants: false,
});

export default function LDAPLoginMappings({
  onSaved,
}: {
  onSaved: () => void;
}) {
  const { user } = useAuth();
  const configuration = useResource<Configuration>("/admin/settings/ldap");
  const organization = useResource<any>("/organization");
  const roleResource = useResource<{ business_grant_allowed?: boolean }>(
    "/admin/roles",
  );
  const [editor, setEditor] = useState<Editor | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [message, setMessage] = useState("");
  const mappings = configuration.data?.config.group_role_mappings || [];
  const orgs = list<Organization>(
    organization.data?.nodes || organization.data,
  );
  const technicalAdmin = !!user.roles?.some(
    (grant) => grant.role.toUpperCase() === "SYSTEM_ADMIN",
  );
  const businessAllowed = !!roleResource.data?.business_grant_allowed;
  const canChange = (mapping: Mapping) =>
    technicalAdmin && (mapping.role === "EMPLOYEE" || businessAllowed);
  const error =
    failure || configuration.error || organization.error || roleResource.error;
  const loading =
    configuration.loading || organization.loading || roleResource.loading;

  const openEditor = (index: number | null) => {
    if (!configuration.data) return;
    setFailure("");
    setMessage("");
    setEditor({
      index,
      version: configuration.data.version,
      value: index === null ? emptyMapping() : { ...mappings[index] },
    });
  };
  const save = async (next: Mapping[], version: number) => {
    setBusy(true);
    setFailure("");
    setMessage("");
    try {
      await api<Configuration>("/admin/settings/ldap", {
        method: "PATCH",
        body: {
          config: { group_role_mappings: next },
          expected_version: version,
        },
      });
      setEditor(null);
      setMessage("İlk giriş grup eşlemeleri kaydedildi.");
      configuration.refresh();
      onSaved();
    } catch (error) {
      setFailure(
        error instanceof Error ? error.message : "Eşlemeler kaydedilemedi.",
      );
    } finally {
      setBusy(false);
    }
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!editor || !canChange(editor.value)) return;
    const value = {
      ...editor.value,
      group_dn: editor.value.group_dn.trim(),
    };
    const next = [...mappings];
    if (editor.index === null) next.push(value);
    else next[editor.index] = value;
    void save(next, editor.version);
  };
  const change = (patch: Partial<Mapping>) => {
    setEditor((current) =>
      current ? { ...current, value: { ...current.value, ...patch } } : null,
    );
  };

  return (
    <section className="onecs-settings-card onecs-settings-ldap-mappings">
      <div className="onecs-settings-config-title">
        <div>
          <h3>İlk giriş grup eşlemeleri</h3>
          <p>
            LDAP parolası doğrulanan kullanıcı, eşleşen doğrudan grup
            üyelikleriyle hesabını ve organizasyon yetkilerini alır. Bağlantı
            testinin başarılı olması kullanıcıya giriş yetkisi vermez.
          </p>
        </div>
        <button
          type="button"
          className="onecs-settings-button"
          disabled={
            busy ||
            !!editor ||
            loading ||
            !configuration.data ||
            !technicalAdmin
          }
          onClick={() => openEditor(null)}
        >
          <Plus size={15} />
          Eşleme ekle
        </button>
      </div>
      <div className="onecs-settings-ldap-mappings-body">
        <p className="onecs-settings-ldap-mappings-hint">
          Otomatik organizasyon eşleşmesi açıksa grup CN değeri ile etkin
          organizasyon kodunun tam eşleşmesi yalnız o organizasyonda Çalışan
          rolü verir. Diğer grup yetkilerini tam DN ile aşağıda tanımlayın.
          Proje yöneticisi rolü proje ataması oluşturmaz; proje kapsamı ilgili
          projeden verilir.
        </p>
        {!businessAllowed && !roleResource.loading && (
          <p className="onecs-settings-ldap-mappings-hint">
            İş yönetimi eşlemelerini değiştirmek için teknik yönetici yetkisine
            ek olarak ilgili organizasyonda direktör yetkisi gerekir.
          </p>
        )}
        {error && (
          <div className="onecs-settings-notice error" role="alert">
            <CircleAlert size={16} />
            <span>{error}</span>
          </div>
        )}
        {message && (
          <div className="onecs-settings-notice success" role="status">
            {message}
          </div>
        )}
        {loading && !configuration.data && (
          <p className="onecs-settings-loading">
            <Loader2 className="spin" size={18} /> Eşlemeler yükleniyor…
          </p>
        )}
        {editor && (
          <form
            onSubmit={submit}
            className="onecs-settings-ldap-mapping-editor"
          >
            <h4>
              {editor.index === null
                ? "Yeni grup eşlemesi"
                : "Grup eşlemesini düzenle"}
            </h4>
            <div className="onecs-settings-form-grid">
              <label className="onecs-settings-field onecs-settings-field-full">
                <span>LDAP grubunun tam DN değeri</span>
                <input
                  value={editor.value.group_dn}
                  required
                  autoComplete="off"
                  placeholder="CN=Ekip,OU=Groups,DC=example,DC=test"
                  disabled={busy}
                  onChange={(event) => change({ group_dn: event.target.value })}
                />
                <small>
                  Dizindeki grubun tam DN değerini kullanın. Grup adı öneki
                  eşleşmesi ve iç içe grup üyeliği kullanılmaz.
                </small>
              </label>
              <label className="onecs-settings-field">
                <span>Organizasyon</span>
                <select
                  value={editor.value.org_node}
                  required
                  disabled={busy}
                  onChange={(event) => change({ org_node: event.target.value })}
                >
                  <option value="">Organizasyon seçin</option>
                  {orgs.map((org) => (
                    <option key={org.id} value={org.id}>
                      {org.name} ({org.code})
                    </option>
                  ))}
                </select>
              </label>
              <label className="onecs-settings-field">
                <span>Verilecek rol</span>
                <select
                  value={editor.value.role}
                  disabled={busy}
                  onChange={(event) =>
                    change({ role: event.target.value as Mapping["role"] })
                  }
                >
                  {roles.map((role) => (
                    <option
                      key={role.value}
                      value={role.value}
                      disabled={role.value !== "EMPLOYEE" && !businessAllowed}
                    >
                      {role.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="onecs-settings-field toggle-field onecs-settings-field-full">
                <span>Alt organizasyonları kapsa</span>
                <div className="onecs-settings-toggle-line">
                  <input
                    type="checkbox"
                    checked={editor.value.includes_descendants}
                    disabled={busy}
                    onChange={(event) =>
                      change({ includes_descendants: event.target.checked })
                    }
                  />
                  <small>
                    Kapalıysa rol yalnız seçilen organizasyonda geçerlidir.
                  </small>
                </div>
              </label>
            </div>
            <div className="onecs-settings-form-footer">
              <button
                type="button"
                className="onecs-settings-button"
                disabled={busy}
                onClick={() => setEditor(null)}
              >
                Vazgeç
              </button>
              <button
                className="onecs-settings-button primary"
                disabled={
                  busy ||
                  !editor.value.group_dn.trim() ||
                  !editor.value.org_node ||
                  !canChange(editor.value)
                }
              >
                {busy && <Loader2 className="spin" size={15} />}
                Eşlemeyi kaydet
              </button>
            </div>
          </form>
        )}
      </div>
      <div className="onecs-settings-table-wrap">
        <table className="onecs-settings-table">
          <thead>
            <tr>
              <th>LDAP grubu (tam DN)</th>
              <th>Organizasyon</th>
              <th>Rol</th>
              <th>Alt organizasyonlar</th>
              <th>İşlemler</th>
            </tr>
          </thead>
          <tbody>
            {mappings.map((mapping, index) => (
              <tr
                key={`${mapping.group_dn}-${mapping.org_node}-${mapping.role}-${index}`}
              >
                <td className="onecs-settings-ldap-mapping-dn">
                  {mapping.group_dn}
                </td>
                <td>
                  {orgs.find((org) => org.id === mapping.org_node)?.name ||
                    mapping.org_node}
                </td>
                <td>
                  {roles.find((role) => role.value === mapping.role)?.label ||
                    mapping.role}
                </td>
                <td>{mapping.includes_descendants ? "Kapsar" : "Kapsamaz"}</td>
                <td>
                  <div className="onecs-settings-ldap-mapping-actions">
                    <button
                      type="button"
                      className="onecs-settings-icon-button"
                      aria-label={`${mapping.group_dn} eşlemesini düzenle`}
                      disabled={busy || !!editor || !canChange(mapping)}
                      title={
                        !canChange(mapping)
                          ? "Bu eşlemeyi değiştirmek için yeterli yetkiniz yok."
                          : "Eşlemeyi düzenle"
                      }
                      onClick={() => openEditor(index)}
                    >
                      <Pencil size={15} />
                    </button>
                    <button
                      type="button"
                      className="onecs-settings-icon-button"
                      aria-label={`${mapping.group_dn} eşlemesini kaldır`}
                      disabled={busy || !!editor || !canChange(mapping)}
                      title={
                        !canChange(mapping)
                          ? "Bu eşlemeyi değiştirmek için yeterli yetkiniz yok."
                          : "Eşlemeyi kaldır"
                      }
                      onClick={() => {
                        if (configuration.data)
                          void save(
                            mappings.filter((_, row) => row !== index),
                            configuration.data.version,
                          );
                      }}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {!mappings.length && !loading && (
              <tr>
                <td colSpan={5}>
                  Tanımlı grup eşlemesi yok. Otomatik organizasyon eşleşmesi
                  açıksa koduyla tam eşleşen gruplar kullanılmaya devam eder.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
