import { Component, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import {
  Activity,
  BookOpen,
  CalendarDays,
  ChevronRight,
  CircleHelp,
  Compass,
  FileText,
  GitBranch,
  Home,
  Layers3,
  LogOut,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  MessageSquare,
  Moon,
  Network,
  Search,
  Settings as SettingsIcon,
  ShieldCheck,
  Sparkles,
  Users,
  X,
  Award,
  ArrowRight,
} from "lucide-react";
import { api, list, setCsrfToken, useResource } from "./lib/api";
import type { Person } from "./lib/types";
import { organizationLabel } from "./lib/organization";
import { AuthContext } from "./lib/auth";
import { Button, ErrorState, Field, Loading } from "./components/ui";
import OnecsBrand from "./components/OnecsBrand";
import Notifications from "./components/Notifications";
import "./styles/shell.css";
import Dashboard from "./pages/Dashboard";
import Records from "./pages/Records";
import Organization from "./pages/Organization";
import Community from "./pages/Community";
import Reports from "./pages/Reports";
import Announcements from "./pages/Announcements";
import Settings from "./pages/Settings";
const sidebarPreferenceKey = "onecs.sidebar.collapsed";
function initialSidebarCollapsed() {
  try {
    return window.localStorage.getItem(sidebarPreferenceKey) === "true";
  } catch {
    return false;
  }
}
const nav = [
  { to: "/dashboard", label: "Genel Bakış", icon: Home },
  { to: "/projects", label: "Projeler", icon: Layers3 },
  { to: "/work", label: "İşler ve Taahhütler", icon: GitBranch },
  { to: "/cases", label: "Vakalar", icon: ShieldCheck },
  { to: "/reports", label: "Raporlar", icon: FileText },
  { to: "/organization", label: "Organizasyon", icon: Network },
  { to: "/community", label: "CS’de Neler Oluyor?", icon: Compass },
  { to: "/announcements", label: "Anonslar", icon: MessageSquare },
  { to: "/events", label: "Etkinlikler", icon: CalendarDays },
  { to: "/credentials", label: "Sertifikalar", icon: Award },
];
function Brand() {
  return <OnecsBrand />;
}
const roleNames: Record<string, string> = {
  DIRECTOR: "Direktör",
  UNIT_HEAD: "Birim yöneticisi",
  TEAM_MANAGER: "Ekip yöneticisi",
  EMPLOYEE: "Çalışan",
  SYSTEM_ADMIN: "Sistem yöneticisi",
  PROJECT_MANAGER: "Proje yöneticisi",
};
const resultNames: Record<string, string> = {
  project: "Proje",
  work: "İş ve taahhüt",
  case: "Vaka",
  person: "Kişi",
  organization: "Birim / ekip",
  community: "Ekip paylaşımı",
  announcement: "Anons",
  event: "Etkinlik",
  credential: "Sertifika",
};
function recordPath(kind: string, id: string) {
  const routes: Record<string, string> = {
    project: "projects",
    work: "work",
    case: "cases",
    person: "organization",
    organization: "organization",
    community: "community",
    announcement: "announcements",
    event: "events",
    credential: "credentials",
    participation: "projects",
  };
  const route = routes[kind];
  if (!route) return null;
  return kind === "participation"
    ? `/${route}`
    : `/${route}?${kind === "person" ? "person" : "id"}=${encodeURIComponent(id)}`;
}
function Login({ onLogin }: { onLogin: (user: Person) => void }) {
  const [method, setMethod] = useState("local");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div className="login-page">
      <div className="login-intro">
        <Brand />
        <div className="login-copy">
          <div className="eyebrow">SİBER GÜVENLİK YÖNETİM PLATFORMU</div>
          <h1>
            Ortak bir bakış.
            <br />
            Güçlü bir koordinasyon.
          </h1>
          <p>
            Öncelikleri görün, ekipleri buluşturun.
            <br />
            İşlerinizi tek bir merkezden yönetin.
          </p>
          <div className="login-proof">
            <ShieldCheck size={18} />
            Yetkili erişim · İzlenebilir kararlar
          </div>
        </div>
        <small>onecs / SİBER GÜVENLİK</small>
      </div>
      <main className="login-main">
        <div className="login-form-wrap">
          <div className="mobile-brand">
            <Brand />
          </div>
          <span className="eyebrow">ÇALIŞMA ALANINIZA HOŞ GELDİNİZ</span>
          <h2>onecs’e giriş yapın</h2>
          <p>Kurumsal veya sistem hesabınızla devam edin.</p>
          <div
            className="segmented login-method"
            role="group"
            aria-label="Giriş yöntemi"
          >
            <button
              className={method === "local" ? "active" : ""}
              onClick={() => setMethod("local")}
            >
              Sistem hesabı
            </button>
            <button
              className={method === "ldap" ? "active" : ""}
              onClick={() => setMethod("ldap")}
            >
              Kurumsal / LDAP
            </button>
          </div>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError("");
              try {
                await api("/auth/csrf");
                const result = await api<any>("/auth/login", {
                  method: "POST",
                  body: { username, password, method },
                });
                const user = result.user || result;
                const me = user.id ? user : await api<Person>("/auth/me");
                if (result.csrf_token) setCsrfToken(result.csrf_token);
                onLogin(me);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <Field label="Kullanıcı adı">
              <input
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder={
                  method === "ldap"
                    ? "Kurumsal kullanıcı adınız"
                    : "Kullanıcı adınız"
                }
                required
                autoFocus
              />
            </Field>
            <Field label="Parola">
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Parolanızı girin"
                required
              />
            </Field>
            {error && <ErrorState message={error} />}
            <Button type="submit" disabled={busy} className="login-submit">
              {busy ? "Oturum açılıyor…" : "Güvenli giriş yapın"}
              <ArrowRight size={17} />
            </Button>
          </form>
          <p className="login-note">
            <ShieldCheck size={15} />
            Oturumunuz ve işlemleriniz güvenli biçimde kayıt altına alınır.
          </p>
        </div>
        <footer>
          onecs · Siber Güvenlik Direktörlüğü<span>Kontrollü erişim</span>
        </footer>
      </main>
    </div>
  );
}
function Shell({
  user,
  onLogout,
  refresh,
}: {
  user: Person;
  onLogout: () => void;
  refresh: () => void;
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const [mobile, setMobile] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    initialSidebarCollapsed,
  );
  useEffect(() => {
    try {
      window.localStorage.setItem(
        sidebarPreferenceKey,
        String(sidebarCollapsed),
      );
    } catch {
      /* Navigation remains usable when browser storage is unavailable. */
    }
  }, [sidebarCollapsed]);
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchIndex, setSearchIndex] = useState(-1);
  const [accountOpen, setAccountOpen] = useState(false);
  const [dark, setDark] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const search = useResource<any>(
    query.trim() ? `/search?q=${encodeURIComponent(query)}` : null,
    undefined,
    0,
  );
  const current = nav.find((n) => location.pathname.startsWith(n.to)) || {
    label: "Ayarlar",
  };
  useEffect(() => {
    setMobile(false);
    setSearchOpen(false);
    setAccountOpen(false);
  }, [location.pathname]);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
      if (e.key === "Escape") {
        setSearchOpen(false);
        setAccountOpen(false);
        setMobile(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  const [searchValue, setSearchValue] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setQuery(searchValue), 220);
    return () => clearTimeout(t);
  }, [searchValue]);
  const searchRows = list<any>(search.data);
  const searchPending = search.loading || query.trim() !== searchValue.trim();
  function openSearchResult(result: any) {
    if (!result) return;
    const destination =
      result.url ||
      result.href ||
      recordPath(result.resource_type || result.kind || result.type, result.id);
    if (destination) {
      navigate(destination);
      setSearchOpen(false);
      setSearchValue("");
      setQuery("");
      setSearchIndex(-1);
    }
  }
  return (
    <AuthContext.Provider value={{ user, refresh }}>
      <div
        className={`app-shell ${mobile ? "mobile-nav-open" : ""} ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}
      >
        <a className="skip-link" href="#main-content">
          İçeriğe geç
        </a>
        {mobile && (
          <button
            className="nav-scrim"
            aria-label="Menüyü kapat"
            onClick={() => setMobile(false)}
          />
        )}
        <aside
          className="app-sidebar"
          id="onecs-sidebar"
          aria-label="onecs gezinme alanı"
        >
          <NavLink
            className="sidebar-brand"
            to="/dashboard"
            aria-label="onecs ana sayfa"
          >
            <Brand />
          </NavLink>
          <div className="sidebar-section-header">
            <div className="sidebar-label">ÇALIŞMA ALANI</div>
            <button
              type="button"
              className="sidebar-collapse-toggle"
              onClick={() => setSidebarCollapsed((value) => !value)}
              aria-expanded={!sidebarCollapsed}
              aria-controls="onecs-primary-navigation"
              aria-label={
                sidebarCollapsed ? "Yan menüyü genişlet" : "Yan menüyü daralt"
              }
              title={
                sidebarCollapsed ? "Yan menüyü genişlet" : "Yan menüyü daralt"
              }
            >
              {sidebarCollapsed ? (
                <PanelLeftOpen size={18} aria-hidden="true" />
              ) : (
                <PanelLeftClose size={18} aria-hidden="true" />
              )}
            </button>
          </div>
          <nav aria-label="Ana gezinme" id="onecs-primary-navigation">
            {nav.map((item, index) => (
              <div key={item.to}>
                {index === 5 && <div className="sidebar-divider" />}
                <NavLink
                  to={item.to}
                  title={item.label}
                  aria-label={item.label}
                  className={({ isActive }) =>
                    `nav-item ${isActive ? "is-active" : ""}`
                  }
                >
                  <item.icon size={18} />
                  <span className="nav-item-label">{item.label}</span>
                </NavLink>
              </div>
            ))}
            {user.permissions?.system_admin && (
              <>
                <div className="sidebar-divider" />
                <NavLink
                  to="/settings"
                  title="Ayarlar"
                  aria-label="Ayarlar"
                  className={({ isActive }) =>
                    `nav-item ${isActive ? "is-active" : ""}`
                  }
                >
                  <SettingsIcon size={18} />
                  <span className="nav-item-label">Ayarlar</span>
                </NavLink>
              </>
            )}
          </nav>
          <div className="sidebar-bottom" title="onecs · Güvenli çalışma alanı">
            <div className="environment-dot" />
            <span className="sidebar-status-label">Güvenli çalışma alanı</span>
            <span className="version">v0.1</span>
          </div>
        </aside>
        <div className="workspace-wrap">
          <header className="app-topbar">
            <button
              className="icon-button mobile-menu"
              aria-label="Menüyü aç"
              aria-expanded={mobile}
              aria-controls="onecs-sidebar"
              onClick={() => setMobile(true)}
            >
              <Menu size={20} />
            </button>
            <div className="breadcrumb">
              <Home size={15} />
              <ChevronRight size={14} />
              <span>{current.label}</span>
            </div>
            <div className="topbar-right">
              <div className="global-search">
                <Search size={16} />
                <input
                  ref={inputRef}
                  value={searchValue}
                  onFocus={() => setSearchOpen(true)}
                  onChange={(e) => {
                    setSearchValue(e.target.value);
                    setSearchOpen(true);
                    setSearchIndex(-1);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "ArrowDown") {
                      e.preventDefault();
                      setSearchOpen(true);
                      setSearchIndex((index) =>
                        Math.min(index + 1, searchRows.length - 1),
                      );
                    } else if (e.key === "ArrowUp") {
                      e.preventDefault();
                      setSearchIndex((index) => Math.max(0, index - 1));
                    } else if (
                      e.key === "Enter" &&
                      searchRows.length &&
                      !searchPending &&
                      !search.error
                    ) {
                      e.preventDefault();
                      openSearchResult(
                        searchRows[
                          Math.min(
                            searchRows.length - 1,
                            Math.max(0, searchIndex),
                          )
                        ],
                      );
                    }
                  }}
                  placeholder="onecs’te ara…"
                  aria-label="onecs genelinde tam metin ara"
                  aria-expanded={searchOpen && !!query}
                  aria-controls="onecs-search-results"
                  aria-autocomplete="list"
                  aria-activedescendant={
                    searchOpen &&
                    searchIndex >= 0 &&
                    searchIndex < searchRows.length
                      ? `onecs-search-result-${searchIndex}`
                      : undefined
                  }
                  role="combobox"
                />
                <kbd>⌘ K</kbd>
                {searchOpen && query && (
                  <div
                    className="search-results"
                    id="onecs-search-results"
                    role="listbox"
                    aria-label="Arama sonuçları"
                  >
                    {searchPending ? (
                      <p>Aranıyor…</p>
                    ) : search.error ? (
                      <p role="alert">{search.error}</p>
                    ) : list(search.data).length ? (
                      list(search.data).map((r: any, index: number) => (
                        <button
                          key={`${r.resource_type || r.kind || r.type}:${r.id}`}
                          id={`onecs-search-result-${index}`}
                          role="option"
                          aria-selected={index === searchIndex}
                          onClick={() => openSearchResult(r)}
                        >
                          <span className="eyebrow">
                            {resultNames[r.resource_type || r.kind || r.type] ||
                              "Kayıt"}
                          </span>
                          <strong>{r.title || r.display_name}</strong>
                          <span>
                            {organizationLabel(r.subtitle) || r.description}
                          </span>
                        </button>
                      ))
                    ) : (
                      <p>Bu kapsamda sonuç bulunamadı.</p>
                    )}
                  </div>
                )}
              </div>
              <button
                className="icon-button theme-button"
                aria-label={dark ? "Açık temaya geç" : "Koyu temaya geç"}
                onClick={() => {
                  const n = !dark;
                  setDark(n);
                  document.documentElement.dataset.theme = n ? "dark" : "light";
                }}
              >
                <Moon size={17} />
              </button>
              <Notifications
                key={user.id}
                ownerKey={user.id}
                onOpen={() => {
                  setAccountOpen(false);
                  setSearchOpen(false);
                }}
              />
              <div className="topbar-popover">
                <button
                  className="account-button"
                  aria-label="Hesap menüsü"
                  onClick={() => setAccountOpen(!accountOpen)}
                >
                  {user.display_name
                    ?.split(" ")
                    .map((n) => n[0])
                    .slice(0, 2)
                    .join("") || "AT"}
                </button>
                {accountOpen && (
                  <div className="popover-panel account-panel">
                    <strong>{user.display_name || user.username}</strong>
                    <p>
                      {organizationLabel(user.primary_org?.name) ||
                        "Siber Güvenlik Direktörlüğü"}
                    </p>
                    <div className="account-roles">
                      {Array.from(
                        new Set(
                          user.roles?.map(
                            (r) => roleNames[r.role] || "Yetkili kullanıcı",
                          ) || [],
                        ),
                      ).map((role) => (
                        <span key={role}>{role}</span>
                      ))}
                    </div>
                    <button onClick={onLogout}>
                      <LogOut size={16} />
                      Çıkış yap
                    </button>
                  </div>
                )}
              </div>
            </div>
          </header>
          {user.test_mode &&
            (user.test_mode.god_mode ||
              (user.test_mode.effective_user_id &&
                user.test_mode.effective_user_id !==
                  user.test_mode.real_actor_id)) && (
              <div className="test-mode-banner">
                <ShieldCheck size={16} />
                <span>
                  <strong>
                    {user.test_mode.god_mode
                      ? "Test ortamı · Tam erişim"
                      : "Kullanıcı görünümü deneniyor"}
                  </strong>{" "}
                  · İşlemler gerçek ve etkin kullanıcıyla kayıtlıdır.
                </span>
                <Button
                  variant="secondary"
                  onClick={async () => {
                    await api("/test-mode", {
                      method: "POST",
                      body: { mode: "stop" },
                    });
                    refresh();
                  }}
                >
                  Test modundan çık
                </Button>
              </div>
            )}
          <main id="main-content" className="workspace-content">
            <Routes key={location.pathname}>
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/projects" element={<Records kind="projects" />} />
              <Route path="/work" element={<Records kind="work" />} />
              <Route path="/cases" element={<Records kind="cases" />} />
              <Route path="/organization" element={<Organization />} />
              <Route
                path="/community"
                element={<Community kind="community" />}
              />
              <Route path="/announcements" element={<Announcements />} />
              <Route path="/events" element={<Community kind="events" />} />
              <Route
                path="/credentials"
                element={<Community kind="credentials" />}
              />
              <Route path="/reports" element={<Reports />} />
              <Route
                path="/settings/*"
                element={
                  user.permissions?.system_admin ? (
                    <Settings />
                  ) : (
                    <Navigate to="/dashboard" replace />
                  )
                }
              />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </main>
          <footer className="workspace-footer">
            <span>onecs · Siber Güvenlik Direktörlüğü</span>
            <span>
              <ShieldCheck size={12} />
              Yetkiniz kapsamındaki kayıtları görüyorsunuz
            </span>
          </footer>
        </div>
      </div>
    </AuthContext.Provider>
  );
}
function OnecsApp() {
  const [user, setUser] = useState<Person | null>(null);
  const [loading, setLoading] = useState(true);
  const [initialError, setInitialError] = useState("");
  async function refresh() {
    try {
      const result = await api<any>("/auth/me");
      setUser(result.user || result);
      setInitialError("");
    } catch (e) {
      if (![401, 403].includes((e as any).status))
        setInitialError((e as Error).message);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void refresh();
    const h = () => setUser(null);
    window.addEventListener("onecs:session-expired", h);
    return () => window.removeEventListener("onecs:session-expired", h);
  }, []);
  if (loading)
    return (
      <div className="boot-screen">
        <Loading label="Güvenli çalışma alanı hazırlanıyor…" />
      </div>
    );
  return user ? (
    <Shell
      user={user}
      refresh={refresh}
      onLogout={async () => {
        try {
          await api("/auth/logout", { method: "POST" });
        } finally {
          setUser(null);
        }
      }}
    />
  ) : (
    <>
      {initialError && (
        <div className="initial-error">
          <ErrorState message={initialError} onRetry={refresh} />
        </div>
      )}
      <Login onLogin={setUser} />
    </>
  );
}

class AppErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (this.state.failed)
      return (
        <div className="recovery-screen">
          <Brand />
          <h1>Çalışma alanı görüntülenemedi</h1>
          <p>
            Kaydedilmiş verileriniz sunucuda korunur. Çalışma alanını yeniden
            yükleyerek devam edebilirsiniz.
          </p>
          <Button onClick={() => window.location.reload()}>
            <ArrowRight size={15} />
            Yeniden yükle
          </Button>
        </div>
      );
    return this.props.children;
  }
}
export default function App() {
  return (
    <AppErrorBoundary>
      <OnecsApp />
    </AppErrorBoundary>
  );
}
