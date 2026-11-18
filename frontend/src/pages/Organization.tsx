import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import WorkAssignmentForm from "../components/WorkAssignmentForm";
import {
  ArrowDown,
  ArrowUpRight,
  Building2,
  ChevronDown,
  ChevronRight,
  GitBranch,
  Clock3,
  Layers3,
  Plus,
  AlertTriangle,
  Mail,
  Network,
  Search,
  ShieldCheck,
  Users,
  UserRound,
} from "lucide-react";
import { date, list, useResource } from "../lib/api";
import {
  Badge,
  Button,
  Status,
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
    <button className="onecs-org-person" onClick={() => onSelect(person)}>
      <span className="onecs-org-avatar">
        {initials(person.display_name || person.username)}
      </span>
      <span className="onecs-org-person-copy">
        <strong>{person.display_name || person.username}</strong>
        <small>
          {personRole(person)}
          {person.primary_org_name
            ? ` · ${organizationName(person.primary_org_name)}`
            : ""}
        </small>
      </span>
      {person.profile_kind === "DEMO" && (
        <span className="onecs-org-demo">Örnek</span>
      )}
      {person.profile_kind === "OFFICIAL_REFERENCE" && (
        <span
          className="onecs-org-reference"
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
      <li className="onecs-org-subtree" key={node.id}>
        <div className="onecs-org-branch-row">
          <button
            className="onecs-org-expand"
            aria-expanded={open}
            aria-controls={`org-children-${node.id}`}
            aria-label={`${organizationName(node.name)} üyelerini ve alt ekiplerini ${open ? "daralt" : "aç"}`}
            onClick={() => toggle(node.id)}
          >
            {open ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
          </button>
          <button
            className="onecs-org-branch-name"
            onClick={() => openOrg(node)}
          >
            <span className="onecs-org-small-icon">
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
          <span className="onecs-org-branch-manager">
            {node.manager_name || "Yönetici tanımlanmamış"}
          </span>
          <span className="onecs-org-branch-count">
            <Users size={15} />
            {node.member_count ?? members.length}
          </span>
          <button
            className="onecs-org-inspect"
            onClick={() => openOrg(node)}
            aria-label={`${organizationName(node.name)} ayrıntılarını incele`}
          >
            <ArrowUpRight size={17} />
          </button>
        </div>
        {open && (
          <div
            className="onecs-org-branch-content"
            id={`org-children-${node.id}`}
          >
            {children.length > 0 && (
              <ul>
                {children.map((child) =>
                  renderBranch(child, depth + 1, [...ancestors, node.id]),
                )}
              </ul>
            )}
            <div className="onecs-org-branch-people">
              {members.map((member) => (
                <PersonRow
                  key={member.id}
                  person={member}
                  onSelect={openPerson}
                />
              ))}
              {!members.length && !children.length && !branchPeople.loading && (
                <p className="onecs-org-empty-note">
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
    <div className="onecs-organization-page">
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
      <div className="onecs-org-summary" aria-label="Organizasyon özeti">
        <div>
          <span className="onecs-org-summary-icon">
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
          <span className="onecs-org-summary-icon">
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
          <span className="onecs-org-summary-icon">
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
      <Card className="onecs-org-card">
        <div className="onecs-org-toolbar">
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
          <label className="onecs-org-search">
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
                <div className="onecs-org-director-wrap">
                  <article className="onecs-org-director">
                    <div className="onecs-org-director-label">
                      <ShieldCheck size={15} />
                      SİBER GÜVENLİK DİREKTÖRLÜĞÜ
                    </div>
                    <button
                      className="onecs-org-director-main"
                      onClick={() => selectManager(directorate)}
                    >
                      <span className="onecs-org-avatar director">
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
                    <div className="onecs-org-director-footer">
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
                  <span className="onecs-org-trunk" aria-hidden="true">
                    <ArrowDown size={15} />
                  </span>
                </div>
              )}
              {visibleTopNodes.length ? (
                <div
                  className="onecs-org-chart-scroll"
                  tabIndex={0}
                  role="region"
                  aria-label="Bağlı birimler; tüm birimleri görmek için yatay kaydırabilirsiniz"
                >
                  <div
                    className="onecs-org-unit-row"
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
                          className={`onecs-org-unit-card ${open ? "is-open" : ""}`}
                          key={node.id}
                        >
                          <div
                            className="onecs-org-unit-number"
                            aria-hidden="true"
                          >
                            {String(index + 1).padStart(2, "0")}
                          </div>
                          <button
                            className="onecs-org-unit-main"
                            onClick={() => openOrg(node)}
                          >
                            <span className="onecs-org-unit-label">
                              {node.code}
                            </span>
                            <h3 title={node.name}>
                              {organizationName(node.name)}
                            </h3>
                            <span className="onecs-org-unit-learn">
                              Birimi tanı <ArrowUpRight size={15} />
                            </span>
                          </button>
                          <button
                            className="onecs-org-manager-link"
                            onClick={() => selectManager(node)}
                            aria-label={`${node.manager_name || organizationName(node.name)} yönetici bilgisi`}
                          >
                            <span className="onecs-org-avatar">
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
                            className="onecs-org-unit-expand"
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
                  description="Bu ağaçta birim, ekip ve yönetici adları aranır. Kişi adı arıyorsanız aynı aramayla rehbere geçebilirsiniz."
                  actions={
                    <Button
                      variant="secondary"
                      onClick={() => setTab("directory")}
                    >
                      <Users size={16} />
                      Kişi rehberinde ara
                    </Button>
                  }
                />
              )}
              <div className="onecs-org-chart-caption">
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
                  className="onecs-org-branch-panel"
                  id={`org-branch-${branch.id}`}
                  aria-label={`${organizationName(branch.name)} ekip ve çalışanları`}
                >
                  <div className="onecs-org-branch-heading">
                    <div>
                      <span className="onecs-org-kicker">BİRİMİN İÇİNDEN</span>
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
                      <ul className="onecs-org-branches">
                        {childrenOf(branch.id)
                          .filter((child) => descendantMatches(child))
                          .map((child) => renderBranch(child))}
                      </ul>
                      <div className="onecs-org-direct-members">
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
                          <p className="onecs-org-empty-note">
                            Bu birimde doğrudan bağlı görünür kişi bulunmuyor.
                          </p>
                        )}
                      </div>
                      {(branchPeople.data?.count || 0) >
                        list(branchPeople.data).length && (
                        <p className="onecs-org-limit-note">
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
            <div className="onecs-org-directory">
              <div className="onecs-org-directory-heading">
                <h2>Ekipler</h2>
                <span>{directoryNodes.length} sonuç</span>
              </div>
              <div className="onecs-org-directory-grid">
                {directoryNodes.map((node) => (
                  <button
                    className="onecs-org-directory-card"
                    key={node.id}
                    onClick={() => openOrg(node)}
                  >
                    <div>
                      <span className="onecs-org-small-icon">
                        <Building2 size={20} />
                      </span>
                      <Badge>{kindLabel(node.kind)}</Badge>
                    </div>
                    <h3 title={node.name}>{organizationName(node.name)}</h3>
                    <span className="onecs-org-directory-code">
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
                <p className="onecs-org-empty-note">Eşleşen ekip bulunamadı.</p>
              )}
              <div className="onecs-org-directory-heading">
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
                  <div className="onecs-org-directory-people">
                    {peopleRows.map((member) => (
                      <PersonRow
                        key={member.id}
                        person={member}
                        onSelect={openPerson}
                      />
                    ))}
                  </div>
                  {(peopleOffset > 0 || peopleHaveNext) && (
                    <div className="onecs-org-pagination">
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
          <div className="onecs-org-detail-hero">
            <span className="onecs-org-small-icon">
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
                  className="onecs-org-detail-child"
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
              <p className="onecs-org-limit-note">
                İlk {list(detailPeople.data).length} kişi gösteriliyor. Diğer
                kişilere rehberden ulaşabilirsiniz.
              </p>
            )}
          </div>
        </Drawer>
      )}
      {visiblePerson && (
        <PersonPanel
          key={visiblePerson.id}
          person={visiblePerson}
          onClose={closeDetail}
        />
      )}
    </div>
  );
}
type PersonWorkloadTab =
  "overview" | "work" | "projects" | "cases" | "contributions";
const contextLabels: Record<string, string> = {
  UNIT_WORK: "Birim işi",
  PROJECT_TASK: "Proje görevi",
  CASE_ACTION: "Vaka aksiyonu",
};
const projectRoleLabels: Record<string, string> = {
  PROJECT_MANAGER: "Proje yöneticisi",
  LEAD: "Proje lideri",
  MEMBER: "Proje katılımcısı",
  CONTRIBUTOR: "Katkı sağlayan",
};
function workloadDue(record: any) {
  return record.sla?.current_due_at || record.due_at;
}
function workloadRoute(kind: "work" | "project" | "case", id: string) {
  return `${kind === "project" ? "/projects" : kind === "case" ? "/cases" : "/work"}?id=${encodeURIComponent(id)}`;
}
function PersonWorkloadRecords({
  records,
  kind,
  personId,
  onNavigate,
}: {
  records: any[];
  kind: "work" | "project" | "case";
  personId: string;
  onNavigate: () => void;
}) {
  if (!records.length)
    return (
      <EmptyState
        title={
          kind === "work"
            ? "Görünür iş bulunmuyor"
            : kind === "project"
              ? "Görünür proje bulunmuyor"
              : "Görünür vaka bulunmuyor"
        }
        description="Yalnızca kişinin ilişkili olduğu ve erişim yetkiniz bulunan kayıtlar gösterilir."
      />
    );
  return (
    <div className="onecs-person-records">
      {records.map((record) => {
        const due = workloadDue(record);
        const late = Boolean(
          record.sla?.is_overdue ||
          (due &&
            new Date(due).getTime() < Date.now() &&
            !["COMPLETED", "CLOSED", "CANCELLED"].includes(record.status)),
        );
        const role =
          kind === "project"
            ? projectRoleLabels[record.membership_role] || "Proje katılımcısı"
            : kind === "case"
              ? record.coordinator?.id === personId
                ? "Vaka koordinatörü"
                : list(record.members).some(
                      (member: any) => member.id === personId,
                    )
                  ? "Vaka üyesi"
                  : "Vaka aksiyonu / katkısı"
              : "Atanan sorumlu";
        const progress = Math.max(
          0,
          Math.min(100, Number(record.progress) || 0),
        );
        return (
          <article className="onecs-person-record" key={record.id}>
            <div className="onecs-person-record-top">
              <span className="onecs-person-record-context">
                {kind === "work" ? contextLabels[record.context] || "İş" : role}
              </span>
              <Status value={record.status} />
            </div>
            <Link
              className="onecs-person-record-title"
              to={workloadRoute(kind, record.id)}
              onClick={onNavigate}
            >
              {record.title}
              <ArrowUpRight size={17} />
            </Link>
            {record.visibility === "SUMMARY" ? (
              <p className="onecs-person-summary-access">
                Yönetim özeti · teknik ayrıntılar erişim kapsamınız dışındadır.
              </p>
            ) : (
              (record.expected_outcome || record.description) && (
                <p>{record.expected_outcome || record.description}</p>
              )
            )}
            <div className="onecs-person-record-meta">
              <span>
                <UserRound size={14} />
                {role}
              </span>
              {due ? (
                <span className={late ? "is-overdue" : ""}>
                  <Clock3 size={14} />
                  {date(due, true)}
                  {late ? " · Gecikti" : ""}
                </span>
              ) : (
                <span>
                  <Clock3 size={14} />
                  Termin tanımlanmadı
                </span>
              )}
              {record.priority && <Status value={record.priority} />}
            </div>
            {kind === "project" && (
              <div className="onecs-person-record-progress">
                <div>
                  <span style={{ width: `${progress}%` }} />
                </div>
                <strong>%{progress}</strong>
              </div>
            )}
          </article>
        );
      })}
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
  const workload = useResource<any>(`/people/${person.id}/workload`);
  const [tab, setTab] = useState<PersonWorkloadTab>("overview");
  const [assigning, setAssigning] = useState(false);
  const [assignmentDone, setAssignmentDone] = useState("");
  const ready = Boolean(
    workload.data?.person?.id === person.id &&
    workload.data?.permissions?.can_view_workload &&
    !workload.error,
  );
  const data = ready ? workload.data : null;
  const summary = data?.summary;
  const works = list(data?.works);
  const projects = list(data?.projects);
  const cases = list(data?.cases);
  const contributions = list(data?.contributions);
  const currentPerson: Person = data?.person || person;
  const assignable = Boolean(
    ready &&
    data.permissions?.can_assign_work &&
    data.assignment?.allowed_target?.person_id === person.id,
  );
  if (assigning && assignable)
    return (
      <WorkAssignmentForm
        defaultTarget={{
          ...currentPerson,
          primary_org_name: organizationName(currentPerson.primary_org_name),
        }}
        onClose={() => setAssigning(false)}
        onCreated={(work) => {
          setAssignmentDone(work?.title || "Yeni iş");
          workload.refresh();
        }}
      />
    );
  return (
    <Drawer
      title={currentPerson.display_name || currentPerson.username}
      subtitle="KİŞİ VE İŞ GÖRÜNÜMÜ"
      onClose={onClose}
      wide
    >
      <div className="onecs-person-header">
        <span className="onecs-org-avatar director">
          {initials(currentPerson.display_name || currentPerson.username)}
        </span>
        <div>
          <h3>{personRole(currentPerson)}</h3>
          <span title={currentPerson.primary_org_name}>
            {organizationName(currentPerson.primary_org_name) ||
              "Birim bilgisi paylaşılmamış"}
          </span>
          {currentPerson.email && (
            <a href={`mailto:${currentPerson.email}`}>
              <Mail size={14} />
              {currentPerson.email}
            </a>
          )}
        </div>
        {assignable && (
          <Button onClick={() => setAssigning(true)}>
            <Plus size={16} />
            İş ata
          </Button>
        )}
      </div>
      {currentPerson.profile_kind === "DEMO" && <Badge>Örnek hesap</Badge>}
      {currentPerson.profile_kind === "OFFICIAL_REFERENCE" && (
        <div className="onecs-org-reference-note">
          <ShieldCheck size={17} />
          <span>
            Organizasyon şeması referansı. Kurumsal dizin doğrulaması bu
            kayıttan ayrı yürütülür.
          </span>
        </div>
      )}
      {assignmentDone && (
        <div className="onecs-person-assigned" role="status">
          <ShieldCheck size={18} />
          <span>
            <strong>{assignmentDone}</strong> kaydedildi. Uygulama bildirimi
            oluşturuldu; e-posta teslimi bağlantı durumuna göre izlenir.
          </span>
        </div>
      )}
      {workload.loading && !data ? (
        <Loading label="Kişinin yetkiniz kapsamındaki işleri yükleniyor…" />
      ) : workload.error ? (
        <div className="onecs-person-workload-denied">
          <ShieldCheck size={23} />
          <strong>İş ayrıntıları sınırlı erişimde</strong>
          <p>
            Kişinin iş yükünü kendisi ve güncel organizasyon yöneticileri
            görebilir. Ekip rehberi bilgilerini aşağıda inceleyebilirsiniz.
          </p>
          <button className="text-button" onClick={workload.refresh}>
            Yeniden dene
          </button>
        </div>
      ) : null}
      {ready && (
        <>
          <div className="onecs-person-workload-kpis">
            <div>
              <span>Açık iş</span>
              <strong>{summary?.open_work ?? 0}</strong>
              <small>{summary?.work_total ?? 0} toplam kayıt</small>
            </div>
            <div className={summary?.overdue_work ? "has-risk" : ""}>
              <span>Geciken iş</span>
              <strong>{summary?.overdue_work ?? 0}</strong>
              <small>{summary?.critical_work ?? 0} kritik açık iş</small>
            </div>
            <div>
              <span>Proje</span>
              <strong>{summary?.projects ?? 0}</strong>
              <small>Yetkiniz kapsamındaki</small>
            </div>
            <div>
              <span>Vaka</span>
              <strong>{summary?.cases ?? 0}</strong>
              <small>İlişkili olduğu</small>
            </div>
          </div>
          {summary?.overdue_work > 0 && (
            <div className="onecs-person-overdue-note">
              <AlertTriangle size={17} />
              {summary.overdue_work} işin termini geçmiş. İşler sekmesinden
              sorumlulukları ve sonraki adımları inceleyebilirsiniz.
            </div>
          )}
          <div
            className="onecs-person-tabs"
            aria-label="Kişi ayrıntısı bölümleri"
          >
            {(
              [
                ["overview", "Genel bakış"],
                ["work", `İşler (${summary?.work_total ?? 0})`],
                ["projects", `Projeler (${summary?.projects ?? 0})`],
                ["cases", `Vakalar (${summary?.cases ?? 0})`],
                ["contributions", "Katkı geçmişi"],
              ] as [PersonWorkloadTab, string][]
            ).map(([value, label]) => (
              <button
                key={value}
                aria-pressed={tab === value}
                className={tab === value ? "active" : ""}
                onClick={() => setTab(value)}
              >
                {label}
              </button>
            ))}
          </div>
        </>
      )}
      {(!ready || tab === "overview") && (
        <>
          <div className="detail-block">
            <h3>Organizasyondaki sorumlulukları</h3>
            {currentPerson.roles?.length ? (
              currentPerson.roles.map((role, index) => (
                <div
                  className="onecs-org-person-role"
                  key={`${role.role}-${role.org_id || index}`}
                >
                  <strong>{roleLabels[role.role] || "Çalışan"}</strong>
                  <span title={role.org_name}>
                    {organizationName(role.org_name) || "Tanımlı kapsam"}
                  </span>
                </div>
              ))
            ) : (
              <p className="muted">Sorumluluk bilgisi paylaşılmamış.</p>
            )}
          </div>
          <div className="detail-block">
            <h3>Gönüllü uzmanlık alanları</h3>
            <div className="expertise-tags">
              {currentPerson.expertise?.length ? (
                currentPerson.expertise.map((skill) => (
                  <span key={skill}>{skill}</span>
                ))
              ) : (
                <p className="muted">Henüz uzmanlık bilgisi paylaşılmamış.</p>
              )}
            </div>
          </div>
          {ready && (
            <>
              <div className="onecs-person-context-totals">
                <span>
                  <GitBranch size={16} />
                  {summary?.by_context?.UNIT_WORK ?? 0} birim işi
                </span>
                <span>
                  <Layers3 size={16} />
                  {summary?.by_context?.PROJECT_TASK ?? 0} proje görevi
                </span>
                <span>
                  <ShieldCheck size={16} />
                  {summary?.by_context?.CASE_ACTION ?? 0} vaka aksiyonu
                </span>
              </div>
              <div className="onecs-person-section-head">
                <h3>Üzerindeki işler</h3>
                <button className="text-button" onClick={() => setTab("work")}>
                  Tümünü gör <ChevronRight size={14} />
                </button>
              </div>
              <PersonWorkloadRecords
                records={works.slice(0, 3)}
                kind="work"
                personId={person.id}
                onNavigate={onClose}
              />
            </>
          )}
        </>
      )}
      {ready && tab === "work" && (
        <>
          <PersonWorkloadRecords
            records={works}
            kind="work"
            personId={person.id}
            onNavigate={onClose}
          />
          {summary.work_total > works.length && (
            <p className="onecs-org-limit-note">
              İlk {works.length} / {summary.work_total} kayıt gösteriliyor.
            </p>
          )}
        </>
      )}
      {ready && tab === "projects" && (
        <>
          <PersonWorkloadRecords
            records={projects}
            kind="project"
            personId={person.id}
            onNavigate={onClose}
          />
          {summary.projects > projects.length && (
            <p className="onecs-org-limit-note">
              İlk {projects.length} / {summary.projects} proje gösteriliyor.
            </p>
          )}
        </>
      )}
      {ready && tab === "cases" && (
        <>
          <PersonWorkloadRecords
            records={cases}
            kind="case"
            personId={person.id}
            onNavigate={onClose}
          />
          {summary.cases > cases.length && (
            <p className="onecs-org-limit-note">
              İlk {cases.length} / {summary.cases} vaka gösteriliyor.
            </p>
          )}
        </>
      )}
      {ready && tab === "contributions" && (
        <div className="detail-block">
          <h3>Katkı geçmişi</h3>
          <p className="muted">
            Yalnızca erişiminiz olan kaynaklardaki katkılar gösterilir.
          </p>
          {contributions.length ? (
            contributions.map((entry: any) => (
              <div
                className="timeline-item onecs-person-contribution"
                key={entry.id}
              >
                <i />
                <div>
                  <div className="onecs-person-contribution-head">
                    <strong>
                      {entry.visibility === "SUMMARY"
                        ? "Proje katkısı · Yönetim özeti"
                        : "İlerleme kaydı"}
                    </strong>
                    <small>{date(entry.created_at, true)}</small>
                  </div>
                  <p>{entry.done || "Açıklama paylaşılmamış."}</p>
                  {entry.next_step && (
                    <p>
                      <strong>Sonraki adım:</strong> {entry.next_step}
                    </p>
                  )}
                  {entry.blocker && (
                    <p>
                      <strong>Engel:</strong> {entry.blocker}
                    </p>
                  )}
                  {entry.context_id &&
                    ["work", "project", "case"].includes(
                      entry.context_type,
                    ) && (
                      <Link
                        to={workloadRoute(entry.context_type, entry.context_id)}
                        onClick={onClose}
                        className="text-button"
                      >
                        Kaydı aç <ArrowUpRight size={14} />
                      </Link>
                    )}
                </div>
              </div>
            ))
          ) : (
            <EmptyState title="Görünür katkı kaydı yok" />
          )}
          {summary.contributions > contributions.length && (
            <p className="onecs-org-limit-note">
              İlk {contributions.length} / {summary.contributions} katkı
              gösteriliyor.
            </p>
          )}
        </div>
      )}
    </Drawer>
  );
}
