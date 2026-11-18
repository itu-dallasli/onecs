import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthContext } from "../lib/auth";
import LDAPLoginMappings from "./LDAPLoginMappings";

const resources = vi.hoisted(() => ({
  configuration: {
    data: {
      version: 4,
      config: {
        group_role_mappings: [
          {
            group_dn: "CN=Example-Team,OU=Groups,DC=example,DC=test",
            org_node: "team-1",
            role: "EMPLOYEE",
            includes_descendants: false,
          },
          {
            group_dn: "CN=Example-Managers,OU=Groups,DC=example,DC=test",
            org_node: "team-1",
            role: "TEAM_MANAGER",
            includes_descendants: true,
          },
        ],
      },
    },
    loading: false,
    error: "",
    refresh: vi.fn(),
  },
  organization: {
    data: {
      results: [{ id: "team-1", name: "Örnek ekip", code: "Example-Team" }],
    },
    loading: false,
    error: "",
    refresh: vi.fn(),
  },
  roles: {
    data: { business_grant_allowed: false },
    loading: false,
    error: "",
    refresh: vi.fn(),
  },
}));

vi.mock("../lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/api")>();
  return {
    ...original,
    useResource: (path: string) => {
      if (path === "/admin/settings/ldap") return resources.configuration;
      if (path === "/organization") return resources.organization;
      if (path === "/admin/roles") return resources.roles;
      throw new Error(`Beklenmeyen test kaynağı: ${path}`);
    },
  };
});

function render(role = "SYSTEM_ADMIN") {
  return renderToStaticMarkup(
    <AuthContext.Provider
      value={{
        user: {
          id: "actor",
          username: "actor",
          display_name: "Test",
          roles: [{ role }],
        },
        refresh: vi.fn(),
      }}
    >
      <LDAPLoginMappings onSaved={vi.fn()} />
    </AuthContext.Provider>,
  );
}

describe("LDAP first-login group mappings", () => {
  beforeEach(() => {
    resources.roles.data.business_grant_allowed = false;
    resources.configuration.error = "";
  });

  it("shows exact directory identities, organization and role scope", () => {
    const markup = render();
    expect(markup).toContain("CN=Example-Team,OU=Groups,DC=example,DC=test");
    expect(markup).toContain("Örnek ekip");
    expect(markup).toContain("Çalışan");
    expect(markup).toContain("Ekip yöneticisi");
    expect(markup).toContain("Kapsar");
    expect(markup).toContain("Kapsamaz");
    expect(markup).toContain(
      "CN değeri ile etkin organizasyon kodunun tam eşleşmesi",
    );
    expect(markup).toContain(
      "Bağlantı testinin başarılı olması kullanıcıya giriş yetkisi vermez",
    );
    expect(markup).toContain("Proje yöneticisi rolü proje ataması oluşturmaz");
  });

  it("lets a technical administrator manage employee mappings while protecting business roles", () => {
    const markup = render();
    const employeeButton = markup.match(
      /<button[^>]+aria-label="CN=Example-Team[^>]+düzenle"[^>]*>/,
    )?.[0];
    const managerButton = markup.match(
      /<button[^>]+aria-label="CN=Example-Managers[^>]+düzenle"[^>]*>/,
    )?.[0];
    expect(employeeButton).toBeDefined();
    expect(employeeButton).not.toContain("disabled");
    expect(managerButton).toContain('disabled=""');
    expect(markup).toContain("ilgili organizasyonda direktör yetkisi gerekir");
  });

  it("allows business mapping edits with the server-confirmed director authority", () => {
    resources.roles.data.business_grant_allowed = true;
    const markup = render();
    const managerButton = markup.match(
      /<button[^>]+aria-label="CN=Example-Managers[^>]+düzenle"[^>]*>/,
    )?.[0];
    expect(managerButton).toBeDefined();
    expect(managerButton).not.toContain("disabled");
  });

  it("does not grant mapping write access from a business role alone", () => {
    resources.roles.data.business_grant_allowed = true;
    const markup = render("DIRECTOR");
    expect(
      markup.match(
        /aria-label="[^"]+eşlemesini (?:düzenle|kaldır)" disabled=""/g,
      ),
    ).toHaveLength(4);
    expect(markup).toMatch(/disabled=""[^>]*>.*?Eşleme ekle/s);
  });

  it("keeps the server authorization error visible", () => {
    resources.configuration.error =
      "İş rolü yalnız kendi yönetim kapsamınızda verilebilir.";
    const markup = render();
    expect(markup).toContain('role="alert"');
    expect(markup).toContain(
      "İş rolü yalnız kendi yönetim kapsamınızda verilebilir.",
    );
  });
});
