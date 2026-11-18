import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  ArrowDown,
  ArrowUpRight,
  Building2,
  ChevronDown,
  ChevronRight,
  GitBranch,
  Mail,
  Network,
  Search,
  ShieldCheck,
  Users,
} from "lucide-react";
import { date, list, useResource } from "../lib/api";
import {
  Badge,
  Card,
  Drawer,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
} from "../components/ui";
import "../styles/organization.css";

type Org = {
  id: string;
  parent_id?: string | null;
  name: string;
  code: string;
  kind: string;
  manager_name?: string;
  manager_id?: string;
  manager_ids?: string[];
  managers?: Person[];
  member_count?: number;
  description?: string;
  expertise?: string[];
  contact?: string;
  is_demo?: boolean;
};
type Person = {
  id: string;
  username: string;
  display_name: string;
  email?: string;
  primary_org_id?: string;
  primary_org_name?: string;
  role_label?: string;
  profile_kind?: string;
  expertise?: string[];
  roles?: { role: string; org_id?: string; org_name?: string }[];
};
const roleLabels: Record<string, string> = {
  DIRECTOR: "Direktör",
  UNIT_HEAD: "Birim yöneticisi",
  TEAM_MANAGER: "Ekip yöneticisi",
  EMPLOYEE: "Çalışan",
  PROJECT_MANAGER: "Proje yöneticisi",
  SYSTEM_ADMIN: "Sistem yöneticisi",
};
// Kaynaktaki adlar ve organizasyon kodları değiştirilmez; bu sözlük yalnız
// Türkçe görünüm ve rehber aramasındaki karşılıkları belirler.
const organizationLabels: Record<string, string> = {
  "Cyber Security": "Siber Güvenlik",
  "Infrastructure Security": "Altyapı Güvenliği",
  "Security Assurance & Architecture": "Güvenlik Güvence ve Mimarisi",
  "Cyber Defence Center": "Siber Savunma Merkezi",
  "Identity Access Management": "Kimlik ve Erişim Yönetimi",
  "Offensive Security": "Ofansif Güvenlik",
  "Security Management": "Güvenlik Yönetimi",
  "Managed Security Services": "Yönetilen Güvenlik Hizmetleri",
  "Security Services Management": "Güvenlik Hizmetleri Yönetimi",
  "Security Services Operations": "Güvenlik Hizmetleri Operasyonları",
  "Identity Management Operations": "Kimlik Yönetimi Operasyonları",
  "Access Management Operations": "Erişim Yönetimi Operasyonları",
  "Cyber Defence Center Analysis": "Siber Savunma Merkezi Analiz Ekibi",
  "Digital Forensics Incident Response":
    "Dijital Adli İnceleme ve Olay Müdahalesi",
  "Application Security Testing": "Uygulama Güvenliği Testleri",
};
function organizationName(value = "") {
  return (
    Object.entries(organizationLabels).find(
      ([source]) => searchText(source) === searchText(value),
    )?.[1] || value
  );
}
function directorySearchQuery(value: string) {
  const query = searchText(value);
  if (!query) return value;
  const matches = Object.entries(organizationLabels).filter(([, label]) =>
    searchText(label).includes(query),
  );
  const exact = matches.find(([, label]) => searchText(label) === query);
  if (exact) return exact[0];
  if (query.length >= 3 && matches.length === 1) return matches[0][0];
  const terms: Record<string, string> = {
    guvenlik: "Security",
    guvenligi: "Security",
    guvenlikleri: "Security",
    yonetim: "Management",
    yonetimi: "Management",
    kimlik: "Identity",
    erisim: "Access",
    savunma: "Defence",
    uygulama: "Application",
    altyapi: "Infrastructure",
    ofansif: "Offensive",
    dijital: "Digital",
    adli: "Forensics",
    olay: "Incident",
    operasyon: "Operations",
    operasyonlari: "Operations",
    hizmet: "Services",
    hizmetleri: "Services",
    mimari: "Architecture",
    mimarisi: "Architecture",
    guvence: "Assurance",
  };
  return terms[query] || value;
}
function initials(name = "") {
  return name
    .trim()
    .split(/\s+/)
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toLocaleUpperCase("tr-TR");
}
function searchText(value = "") {
  return value
    .toLocaleLowerCase("tr-TR")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/ı/g, "i");
}
function kindLabel(kind: string) {
  return kind === "DIRECTORATE"
    ? "Direktörlük"
    : kind === "UNIT"
      ? "Birim"
      : kind === "TEAM"
        ? "Ekip"
        : "Organizasyon";
}
function personRole(person: Person) {
  return (
    person.role_label ||
    [
      ...new Set(
        (person.roles || []).map((role) => roleLabels[role.role] || "Çalışan"),
      ),
    ].join(" · ") ||
    "Çalışan"
  );
}
function PersonRow({
  person,
  onSelect,
}: {
  person: Person;
  onSelect: (person: Person) => void;
}) {
  return (
    <button className="atlas-org-person" onClick={() => onSelect(person)}>
      <span className="atlas-org-avatar">
        {initials(person.display_name || person.username)}
      </span>
      <span className="atlas-org-person-copy">
        <strong>{person.display_name || person.username}</strong>
        <small>
          {personRole(person)}
          {person.primary_org_name
            ? ` · ${organizationName(person.primary_org_name)}`
            : ""}
        </small>
      </span>
      {person.profile_kind === "DEMO" && (
        <span className="atlas-org-demo">Örnek</span>
      )}
      {person.profile_kind === "OFFICIAL_REFERENCE" && (
        <span
          className="atlas-org-reference"
          title="Organizasyon şemasından alınan referans kayıt; dizin bağlantısı doğrulanmış hesap değildir."
        >
          Şema referansı
        </span>
      )}
      <ChevronRight size={16} aria-hidden="true" />
    </button>
  );
}

export default function Organization() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedOrgId = searchParams.get("id") || "";
  const requestedPersonId = searchParams.get("person") || "";
  const organizations = useResource<any>("/organization");
  const linkedPerson = useResource<Person>(
    requestedPersonId
      ? `/people/${encodeURIComponent(requestedPersonId)}`
      : null,
    undefined,
    0,
  );
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [tab, setTab] = useState<"tree" | "directory">("tree");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [branchId, setBranchId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Org | null>(null);
  const [person, setPerson] = useState<Person | null>(null);
  const [peopleOffset, setPeopleOffset] = useState(0);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedQuery(query.trim());
      setPeopleOffset(0);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query]);
  const raw = organizations.data;
  const nodes = useMemo<Org[]>(
    () =>
      list(Array.isArray(raw) ? raw : raw?.nodes || raw?.organizations || raw),
    [raw],
  );
  const byId = useMemo(
    () => new Map(nodes.map((node) => [node.id, node])),
    [nodes],
  );
  const childrenOf = (id: string) =>
    nodes.filter((node) => node.parent_id === id);
  const roots = nodes.filter(
    (node) => !node.parent_id || !byId.has(node.parent_id),
  );
  const directorate = roots.find((node) => node.kind === "DIRECTORATE");
  const topNodes = directorate ? childrenOf(directorate.id) : roots;
  const branch = branchId ? byId.get(branchId) : undefined;
  const activeDetail = requestedOrgId
    ? byId.get(requestedOrgId)
    : selected
      ? byId.get(selected.id)
      : null;
  const visiblePerson = requestedPersonId
    ? linkedPerson.data?.id === requestedPersonId
      ? linkedPerson.data
      : null
    : person;
  useEffect(() => {
    if (!requestedOrgId || !byId.has(requestedOrgId)) return;
    const path = new Set<string>();
    let current = byId.get(requestedOrgId);
    while (current && !path.has(current.id)) {
      path.add(current.id);
      if (current.kind === "UNIT") {
        setBranchId(current.id);
        break;
      }
      current = current.parent_id ? byId.get(current.parent_id) : undefined;
    }
    setExpanded((previous) => new Set([...previous, ...path]));
  }, [requestedOrgId, byId]);
  const peoplePath =
    tab === "directory"
      ? `/people?search=${encodeURIComponent(directorySearchQuery(debouncedQuery))}&limit=48&offset=${peopleOffset}`
      : null;
  const directoryPeople = useResource<any>(peoplePath);
  const branchPeople = useResource<any>(
    branchId ? `/people?org_id=${branchId}&limit=200` : null,
  );
  const detailPeople = useResource<any>(
    activeDetail ? `/people?org_id=${activeDetail.id}&limit=200` : null,
  );
  const needle = searchText(query.trim());
  const nodeMatches = (node: Org) =>
    !needle ||
    searchText(
      `${node.name} ${organizationName(node.name)} ${node.code} ${node.manager_name || ""}`,
    ).includes(needle);
  function descendantMatches(node: Org, visited = new Set<string>()): boolean {
    if (visited.has(node.id)) return false;
    visited.add(node.id);
    return (
      nodeMatches(node) ||
      childrenOf(node.id).some((child) => descendantMatches(child, visited))
    );
  }
  const visibleTopNodes = topNodes.filter((node) => descendantMatches(node));
  const directoryNodes = nodes.filter(
    (node) => node.kind !== "DIRECTORATE" && nodeMatches(node),
  );
  const peopleRows = list<Person>(directoryPeople.data);
  const peopleTotal = directoryPeople.data?.count ?? peopleRows.length;
  const peopleHaveNext =
    Boolean(directoryPeople.data?.next) ||
    peopleOffset + peopleRows.length < peopleTotal;
  function nodeMembers(node: Org, members: Person[]) {
    return members.filter(
      (member) =>
        member.primary_org_id === node.id ||
        member.roles?.some((role) => role.org_id === node.id),
    );
  }
  function toggle(id: string) {
    setExpanded((previous) => {
      const next = new Set(previous);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }
  function openPerson(member: Person) {
    clearDeepLinks();
    setSelected(null);
    setPerson(member);
  }
  function clearDeepLinks() {
    if (!requestedOrgId && !requestedPersonId) return;
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.delete("id");
        next.delete("person");
        return next;
      },
      { replace: true },
    );
  }
  function openOrg(node: Org) {
    clearDeepLinks();
    setPerson(null);
    setSelected(node);
  }
  function closeDetail() {
    clearDeepLinks();
    setPerson(null);
    setSelected(null);
  }
  function selectManager(node: Org) {
    const manager = node.managers?.[0];
    if (manager) openPerson(manager);
    else openOrg(node);
  }
  function renderBranch(
    node: Org,
    depth = 0,
    ancestors: string[] = [],
  ): React.ReactNode {
    if (ancestors.includes(node.id)) return null;
    const children = childrenOf(node.id).filter((child) =>
      descendantMatches(child),
    );
    const open = expanded.has(node.id) || Boolean(needle);
    const members = nodeMembers(node, list<Person>(branchPeople.data));
    return (
      <li className="atlas-org-subtree" key={node.id}>
        <div className="atlas-org-branch-row">
          <button
            className="atlas-org-expand"
            aria-expanded={open}
            aria-controls={`org-children-${node.id}`}
            aria-label={`${organizationName(node.name)} üyelerini ve alt ekiplerini ${open ? "daralt" : "aç"}`}
            onClick={() => toggle(node.id)}
          >
            {open ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
          </button>
          <button
            className="atlas-org-branch-name"
            onClick={() => openOrg(node)}
          >
            <span className="atlas-org-small-icon">
              <Building2 size={19} />
            </span>
            <span>
              <strong>{organizationName(node.name)}</strong>
              <small>
                {node.code} · {kindLabel(node.kind)}
                {node.is_demo ? " · Örnek ekip" : ""}
              </small>
            </span>
          </button>
          <span className="atlas-org-branch-manager">
            {node.manager_name || "Yönetici tanımlanmamış"}
          </span>
          <span className="atlas-org-branch-count">
            <Users size={15} />
            {node.member_count ?? members.length}
          </span>
          <button
            className="atlas-org-inspect"
            onClick={() => openOrg(node)}
            aria-label={`${organizationName(node.name)} ayrıntılarını incele`}
          >
            <ArrowUpRight size={17} />
          </button>
        </div>
        {open && (
          <div
            className="atlas-org-branch-content"
            id={`org-children-${node.id}`}
          >
            {children.length > 0 && (
              <ul>
                {children.map((child) =>
                  renderBranch(child, depth + 1, [...ancestors, node.id]),
                )}
              </ul>
            )}
            <div className="atlas-org-branch-people">
              {members.map((member) => (
                <PersonRow
                  key={member.id}
                  person={member}
                  onSelect={openPerson}
                />
              ))}
              {!members.length && !children.length && !branchPeople.loading && (
                <p className="atlas-org-empty-note">
                  Bu ekip için görünür kişi bulunmuyor.
                </p>
              )}
            </div>
          </div>
        )}
      </li>
    );
  }
  return (
    <div className="atlas-organization-page">
      <PageHeader
        eyebrow="ORTAK YAPI, GÜÇLÜ İLETİŞİM"
        title="Organizasyon"
        description="Siber Güvenlik Direktörlüğü’nü, birimleri ve ekipleri tek bir ağaçta keşfedin."
      />
      {requestedPersonId && linkedPerson.loading && (
        <Loading label="Kişi ayrıntısı yükleniyor…" />
      )}
      {requestedPersonId && linkedPerson.error && (
        <ErrorState
          message="Kişi kaydı bulunamadı veya bu kaydı görüntüleme yetkiniz yok."
          onRetry={linkedPerson.refresh}
        />
      )}
      {requestedOrgId &&
        !requestedPersonId &&
        !organizations.loading &&
        !organizations.error &&
        !byId.has(requestedOrgId) && (
          <ErrorState message="Organizasyon kaydı bulunamadı veya bu kaydı görüntüleme yetkiniz yok." />
        )}
      <div className="atlas-org-summary" aria-label="Organizasyon özeti">
        <div>
          <span className="atlas-org-summary-icon">
            <ShieldCheck size={21} />
          </span>
          <span>
            <strong>
              {nodes.filter((node) => node.kind === "UNIT").length}
            </strong>
            <small>Yönetim birimi</small>
          </span>
        </div>
        <div>
          <span className="atlas-org-summary-icon">
            <GitBranch size={21} />
          </span>
          <span>
            <strong>
              {nodes.filter((node) => node.kind === "TEAM").length}
            </strong>
            <small>Alt ekip</small>
          </span>
        </div>
        <div>
          <span className="atlas-org-summary-icon">
            <Users size={21} />
          </span>
          <span>
            <strong>
              {directorate?.member_count ??
                roots.reduce((sum, node) => sum + (node.member_count || 0), 0)}
            </strong>
            <small>Görünür kişi</small>
          </span>
        </div>
        <p>
          Direktör <ChevronRight size={14} /> Birim yöneticisi{" "}
          <ChevronRight size={14} /> Ekip yöneticisi <ChevronRight size={14} />{" "}
          Çalışan
        </p>
      </div>
      <Card className="atlas-org-card">
        <div className="atlas-org-toolbar">
          <div className="segmented" aria-label="Organizasyon görünümü">
            <button
              className={tab === "tree" ? "active" : ""}
              onClick={() => setTab("tree")}
              aria-pressed={tab === "tree"}
            >
              <Network size={17} />
              Organizasyon ağacı
            </button>
            <button
              className={tab === "directory" ? "active" : ""}
              onClick={() => setTab("directory")}
              aria-pressed={tab === "directory"}
            >
              <Users size={17} />
              Ekip ve kişi rehberi
            </button>
          </div>
          <label className="atlas-org-search">
            <Search size={18} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={
                tab === "tree"
                  ? "Birim, yönetici veya ekip ara…"
                  : "Ekip veya kişi ara…"
              }
              aria-label="Organizasyonda ara"
            />
            {query && (
              <button onClick={() => setQuery("")} aria-label="Aramayı temizle">
                ×
              </button>
            )}
          </label>
        </div>
        {organizations.error && (
          <ErrorState
            message={organizations.error}
            onRetry={organizations.refresh}
          />
        )}
        {organizations.loading && !raw ? (
          <Loading label="Organizasyon yükleniyor…" />
        ) : nodes.length ? (
          tab === "tree" ? (
            <>
              {directorate && (
                <div className="atlas-org-director-wrap">
                  <article className="atlas-org-director">
                    <div className="atlas-org-director-label">
                      <ShieldCheck size={15} />
                      SİBER GÜVENLİK DİREKTÖRLÜĞÜ
                    </div>
                    <button
                      className="atlas-org-director-main"
                      onClick={() => selectManager(directorate)}
                    >
                      <span className="atlas-org-avatar director">
                        {initials(directorate.manager_name)}
                      </span>
                      <span>
                        <h2>
                          {directorate.manager_name || "Direktör tanımlanmamış"}
                        </h2>
                        <span>Direktör</span>
                      </span>
                      <ArrowUpRight size={19} />
                    </button>
                    <div className="atlas-org-director-footer">
                      <span>
                        <Building2 size={14} />
                        {topNodes.length} bağlı birim
                      </span>
                      <span>
                        <Users size={14} />
                        {directorate.member_count ?? "—"} kişi
                      </span>
                    </div>
                  </article>
                  <span className="atlas-org-trunk" aria-hidden="true">
                    <ArrowDown size={15} />
                  </span>
                </div>
              )}
              {visibleTopNodes.length ? (
                <div
                  className="atlas-org-chart-scroll"
                  tabIndex={0}
                  role="region"
                  aria-label="Bağlı birimler; tüm birimleri görmek için yatay kaydırabilirsiniz"
                >
                  <div
                    className="atlas-org-unit-row"
                    style={
                      {
                        "--org-unit-count": visibleTopNodes.length,
                      } as React.CSSProperties
                    }
                  >
                    {visibleTopNodes.map((node, index) => {
                      const childCount = childrenOf(node.id).length;
                      const open = branchId === node.id;
                      return (
                        <article
                          className={`atlas-org-unit-card ${open ? "is-open" : ""}`}
                          key={node.id}
                        >
                          <div
                            className="atlas-org-unit-number"
                            aria-hidden="true"
                          >
                            {String(index + 1).padStart(2, "0")}
                          </div>
                          <button
                            className="atlas-org-unit-main"
                            onClick={() => openOrg(node)}
                          >
                            <span className="atlas-org-unit-label">
                              {node.code}
                            </span>
                            <h3 title={node.name}>
                              {organizationName(node.name)}
                            </h3>
                            <span className="atlas-org-unit-learn">
                              Birimi tanı <ArrowUpRight size={15} />
                            </span>
                          </button>
                          <button
                            className="atlas-org-manager-link"
                            onClick={() => selectManager(node)}
                            aria-label={`${node.manager_name || organizationName(node.name)} yönetici bilgisi`}
                          >
                            <span className="atlas-org-avatar">
                              {initials(node.manager_name)}
                            </span>
                            <span>
                              <strong>
                                {node.manager_name || "Atama bekleniyor"}
                              </strong>
                              <small>Birim yöneticisi</small>
                            </span>
                          </button>
                          <button
                            className="atlas-org-unit-expand"
                            aria-expanded={open}
                            aria-controls={`org-branch-${node.id}`}
                            onClick={() => setBranchId(open ? null : node.id)}
                          >
                            <span>
                              <Users size={15} />
                              {node.member_count ?? 0} kişi
                              {childCount ? ` · ${childCount} alt ekip` : ""}
                            </span>
                            {open ? (
                              <ChevronDown size={18} />
                            ) : (
                              <ChevronRight size={18} />
                            )}
                          </button>
                        </article>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <EmptyState
                  title="Aramanızla eşleşen birim bulunamadı"
                  description="Birim adı, kodu veya yönetici adıyla yeniden deneyin."
                />
              )}
              <div className="atlas-org-chart-caption">
                <span>
                  <Network size={15} />
                  Birim kartındaki kişi sayısına basarak alt ekipleri ve
                  çalışanları açabilirsiniz.
                </span>
                <span>
                  Bir yönetici birden fazla birimin sorumluluğunu üstlenebilir.
                </span>
              </div>
              {branch && (
                <section
                  className="atlas-org-branch-panel"
                  id={`org-branch-${branch.id}`}
                  aria-label={`${organizationName(branch.name)} ekip ve çalışanları`}
                >
                  <div className="atlas-org-branch-heading">
                    <div>
                      <span className="atlas-org-kicker">BİRİMİN İÇİNDEN</span>
                      <h3 title={branch.name}>
                        {organizationName(branch.name)}
                      </h3>
                      <p>
                        {branch.manager_name || "Yönetici tanımlanmamış"} ·{" "}
                        {branch.member_count ?? 0} kişi
                      </p>
                    </div>
                    <button
                      className="btn btn-secondary"
                      onClick={() => setBranchId(null)}
                    >
                      Daralt <ChevronDown size={16} />
                    </button>
                  </div>
                  {branchPeople.error && (
                    <ErrorState
                      message={branchPeople.error}
                      onRetry={branchPeople.refresh}
                    />
                  )}
                  {branchPeople.loading && !branchPeople.data ? (
                    <Loading label="Ekipler ve kişiler yükleniyor…" />
                  ) : (
                    <>
                      <ul className="atlas-org-branches">
                        {childrenOf(branch.id)
                          .filter((child) => descendantMatches(child))
                          .map((child) => renderBranch(child))}
                      </ul>
                      <div className="atlas-org-direct-members">
                        <h4>Doğrudan birime bağlı kişiler</h4>
                        {nodeMembers(
                          branch,
                          list<Person>(branchPeople.data),
                        ).map((member) => (
                          <PersonRow
                            key={member.id}
                            person={member}
                            onSelect={openPerson}
                          />
                        ))}
                        {!nodeMembers(branch, list<Person>(branchPeople.data))
                          .length && (
                          <p className="atlas-org-empty-note">
                            Bu birimde doğrudan bağlı görünür kişi bulunmuyor.
                          </p>
                        )}
                      </div>
                      {(branchPeople.data?.count || 0) >
                        list(branchPeople.data).length && (
                        <p className="atlas-org-limit-note">
                          İlk {list(branchPeople.data).length} kişi
                          gösteriliyor. Diğer kişilere rehberde adlarıyla
                          arayarak ulaşabilirsiniz.
                        </p>
                      )}
                    </>
                  )}
                </section>
              )}
            </>
          ) : (
            <div className="atlas-org-directory">
              <div className="atlas-org-directory-heading">
                <h2>Ekipler</h2>
                <span>{directoryNodes.length} sonuç</span>
              </div>
              <div className="atlas-org-directory-grid">
                {directoryNodes.map((node) => (
                  <button
                    className="atlas-org-directory-card"
                    key={node.id}
                    onClick={() => openOrg(node)}
                  >
                    <div>
                      <span className="atlas-org-small-icon">
                        <Building2 size={20} />
                      </span>
                      <Badge>{kindLabel(node.kind)}</Badge>
                    </div>
                    <h3 title={node.name}>{organizationName(node.name)}</h3>
                    <span className="atlas-org-directory-code">
                      {node.code}
                    </span>
                    <p>
                      {node.description ||
                        "Ekip sorumluluklarını, yöneticisini ve üyelerini inceleyin."}
                    </p>
                    <footer>
                      <span>
                        {node.manager_name || "Yönetici tanımlanmamış"}
                      </span>
                      <ArrowUpRight size={17} />
                    </footer>
                  </button>
                ))}
              </div>
              {!directoryNodes.length && (
                <p className="atlas-org-empty-note">Eşleşen ekip bulunamadı.</p>
              )}
              <div className="atlas-org-directory-heading">
                <h2>Kişiler</h2>
                <span>
                  {directoryPeople.loading
                    ? "Aranıyor…"
                    : `${peopleTotal} sonuç`}
                </span>
              </div>
              {directoryPeople.error ? (
                <ErrorState
                  message={directoryPeople.error}
                  onRetry={directoryPeople.refresh}
                />
              ) : directoryPeople.loading && !directoryPeople.data ? (
                <Loading label="Kişiler yükleniyor…" />
              ) : peopleRows.length ? (
                <>
                  <div className="atlas-org-directory-people">
                    {peopleRows.map((member) => (
                      <PersonRow
                        key={member.id}
                        person={member}
                        onSelect={openPerson}
                      />
                    ))}
                  </div>
                  {(peopleOffset > 0 || peopleHaveNext) && (
                    <div className="atlas-org-pagination">
                      <button
                        className="btn btn-secondary"
                        disabled={peopleOffset === 0 || directoryPeople.loading}
                        onClick={() =>
                          setPeopleOffset(Math.max(0, peopleOffset - 48))
                        }
                      >
                        Önceki
                      </button>
                      <span>
                        {peopleOffset + 1}–{peopleOffset + peopleRows.length} /{" "}
                        {peopleTotal}
                      </span>
                      <button
                        className="btn btn-secondary"
                        disabled={!peopleHaveNext || directoryPeople.loading}
                        onClick={() => setPeopleOffset(peopleOffset + 48)}
                      >
                        Sonraki
                      </button>
                    </div>
                  )}
                </>
              ) : (
                <EmptyState
                  title="Eşleşen kişi bulunamadı"
                  description="Ad, kullanıcı adı veya ekip adıyla arayabilirsiniz."
                />
              )}
            </div>
          )
        ) : (
          <EmptyState
            title="Organizasyon henüz tanımlanmadı"
            description="Organizasyon kaynağı bağlandığında birimler ve ekipler burada görüntülenir."
          />
        )}
      </Card>
      <div className="context-note">
        <ShieldCheck size={16} />
        Bu rehber ekipleri tanımayı kolaylaştırır. İş, proje ve katkı
        ayrıntıları erişim yetkilerinizle korunur.
      </div>
      {activeDetail && !visiblePerson && !requestedPersonId && (
        <Drawer
          title={organizationName(activeDetail.name)}
          subtitle={`${activeDetail.code} · ${kindLabel(activeDetail.kind)}${organizationName(activeDetail.name) !== activeDetail.name ? ` · Kaynak adı: ${activeDetail.name}` : ""}`}
          onClose={closeDetail}
          wide
        >
          <div className="atlas-org-detail-hero">
            <span className="atlas-org-small-icon">
              <Building2 size={26} />
            </span>
            <div>
              <span>{kindLabel(activeDetail.kind)}</span>
              <strong>
                {activeDetail.manager_name || "Yönetici tanımlanmamış"}
              </strong>
              <small>{activeDetail.member_count ?? 0} görünür kişi</small>
            </div>
          </div>
          <div className="detail-block">
            <h3>Ne yapıyoruz?</h3>
            <p>
              {activeDetail.description || "Ekip tanıtımı henüz paylaşılmamış."}
            </p>
          </div>
          <div className="detail-block">
            <h3>Uzmanlık alanları</h3>
            <div className="expertise-tags">
              {activeDetail.expertise?.length ? (
                activeDetail.expertise.map((skill) => (
                  <span key={skill}>{skill}</span>
                ))
              ) : (
                <p className="muted">Henüz uzmanlık alanı paylaşılmamış.</p>
              )}
            </div>
          </div>
          {childrenOf(activeDetail.id).length > 0 && (
            <div className="detail-block">
              <h3>Bağlı ekipler</h3>
              {childrenOf(activeDetail.id).map((child) => (
                <button
                  key={child.id}
                  className="atlas-org-detail-child"
                  onClick={() => openOrg(child)}
                >
                  <Building2 size={17} />
                  <span>
                    <strong title={child.name}>
                      {organizationName(child.name)}
                    </strong>
                    <small>{child.manager_name || child.code}</small>
                  </span>
                  <ChevronRight size={17} />
                </button>
              ))}
            </div>
          )}
          <div className="detail-block">
            <h3>Birime bağlı kişiler</h3>
            {detailPeople.error ? (
              <ErrorState
                message={detailPeople.error}
                onRetry={detailPeople.refresh}
              />
            ) : detailPeople.loading && !detailPeople.data ? (
              <Loading label="Kişiler yükleniyor…" />
            ) : list<Person>(detailPeople.data).length ? (
              list<Person>(detailPeople.data).map((member) => (
                <PersonRow
                  key={member.id}
                  person={member}
                  onSelect={openPerson}
                />
              ))
            ) : (
              <p className="muted">Bu ekip için görünür kişi bulunmuyor.</p>
            )}
            {(detailPeople.data?.count || 0) >
              list(detailPeople.data).length && (
              <p className="atlas-org-limit-note">
                İlk {list(detailPeople.data).length} kişi gösteriliyor. Diğer
                kişilere rehberden ulaşabilirsiniz.
              </p>
            )}
          </div>
        </Drawer>
      )}
      {visiblePerson && (
        <PersonPanel person={visiblePerson} onClose={closeDetail} />
      )}
    </div>
  );
}
function PersonPanel({
  person,
  onClose,
}: {
  person: Person;
  onClose: () => void;
}) {
  const activity = useResource<any>(`/people/${person.id}/contributions`);
  return (
    <Drawer
      title={person.display_name || person.username}
      subtitle="KİŞİ AYRINTISI"
      onClose={onClose}
      wide
    >
      <div className="atlas-org-person-profile">
        <span className="atlas-org-avatar director">
          {initials(person.display_name || person.username)}
        </span>
        <h3>{personRole(person)}</h3>
        <span title={person.primary_org_name}>
          {organizationName(person.primary_org_name) ||
            "Birim bilgisi paylaşılmamış"}
        </span>
        {person.profile_kind === "DEMO" && <Badge>Örnek hesap</Badge>}
        {person.profile_kind === "OFFICIAL_REFERENCE" && (
          <div className="atlas-org-reference-note">
            <ShieldCheck size={17} />
            <span>
              Organizasyon şeması referansı. Kurumsal dizin doğrulaması bu
              kayıttan ayrı yürütülür.
            </span>
          </div>
        )}
        {person.email && (
          <a href={`mailto:${person.email}`}>
            <Mail size={16} />
            {person.email}
          </a>
        )}
      </div>
      {person.roles?.length ? (
        <div className="detail-block">
          <h3>Organizasyondaki sorumlulukları</h3>
          {person.roles.map((role, index) => (
            <div
              className="atlas-org-person-role"
              key={`${role.role}-${role.org_id || index}`}
            >
              <strong>{roleLabels[role.role] || "Çalışan"}</strong>
              <span title={role.org_name}>
                {organizationName(role.org_name) || "Tanımlı kapsam"}
              </span>
            </div>
          ))}
        </div>
      ) : null}
      <div className="detail-block">
        <h3>Gönüllü uzmanlık alanları</h3>
        <div className="expertise-tags">
          {person.expertise?.length ? (
            person.expertise.map((skill) => <span key={skill}>{skill}</span>)
          ) : (
            <p className="muted">Henüz uzmanlık bilgisi paylaşılmamış.</p>
          )}
        </div>
      </div>
      <div className="detail-block">
        <h3>Katkı geçmişi</h3>
        <p className="muted">Yalnızca erişiminiz olan kayıtlar gösterilir.</p>
        {activity.loading ? (
          <Loading />
        ) : activity.error ? (
          <div className="atlas-org-empty-note">
            Katkı ayrıntılarını görüntüleme yetkiniz bulunmuyor veya kayıt
            alınamıyor.
          </div>
        ) : list(activity.data).length ? (
          list(activity.data).map((entry: any) => (
            <div className="timeline-item" key={entry.id}>
              <i />
              <div>
                <strong>
                  {entry.title || entry.action || "İlerleme kaydı"}
                </strong>
                <p>{entry.done || entry.summary || entry.description}</p>
                <small>{date(entry.created_at, true)}</small>
              </div>
            </div>
          ))
        ) : (
          <EmptyState title="Görünür katkı kaydı yok" />
        )}
      </div>
    </Drawer>
  );
}
