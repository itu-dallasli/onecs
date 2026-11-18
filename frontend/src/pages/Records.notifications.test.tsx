import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthContext } from "../lib/auth";
import Records from "./Records";

const fixture = vi.hoisted(() => ({
  calls: [] as (string | null)[],
  error: "",
  responseId: "10000000-0000-0000-0000-000000000001",
  kind: "projects",
}));
const requestId = "10000000-0000-0000-0000-000000000001";
const parentId = "20000000-0000-0000-0000-000000000001";

vi.mock("../lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/api")>();
  return {
    ...original,
    useResource: (path: string | null) => {
      fixture.calls.push(path);
      const participation = path?.startsWith("/participation-requests/");
      const caseNotice = path?.startsWith("/case-notices/");
      const detail = participation || caseNotice;
      return {
        data: detail
          ? fixture.error
            ? undefined
            : caseNotice
              ? {
                  id: fixture.responseId,
                  title: "Odak vaka bildirimi",
                  description: "Yalnız hedef bildirimin açıklaması",
                  status: "PENDING",
                  created_at: "2026-11-18T10:00:00Z",
                }
              : {
                  id: fixture.responseId,
                  status: "PENDING",
                  summary: "Odak talebinin paylaşılabilir özeti",
                  user: { display_name: "Talep edilen kişi" },
                  target_org_name: "Örnek ekip",
                  project_id: fixture.kind === "projects" ? parentId : null,
                  case_id: fixture.kind === "cases" ? parentId : null,
                  project: { title: "GİZLİ PROJE AYRINTISI" },
                  case: { title: "GİZLİ VAKA AYRINTISI" },
                }
          : path === "/participation-requests"
            ? {
                results: [
                  {
                    id: "other",
                    status: "PENDING",
                    summary: "Başka talebin özeti",
                  },
                ],
              }
            : path === "/case-notices"
              ? {
                  results: [
                    {
                      id: "other-notice",
                      status: "PENDING",
                      title: "Başka vaka bildirimi",
                      description: "Başka bildirimin açıklaması",
                    },
                  ],
                }
              : { results: [] },
        loading: false,
        error: detail ? fixture.error : "",
        refresh: vi.fn(),
      };
    },
  };
});

vi.mock("../components/ui", async (importOriginal) => {
  const original = await importOriginal<typeof import("../components/ui")>();
  return {
    ...original,
    Drawer: ({ title, children }: { title: string; children: ReactNode }) => (
      <section aria-label={title}>{children}</section>
    ),
  };
});

function render(
  kind: "projects" | "cases",
  target: "requests" | "notices" = "requests",
) {
  fixture.kind = kind;
  return renderToStaticMarkup(
    <MemoryRouter
      initialEntries={[
        `/${kind}?${target}=1&${target === "requests" ? "request_id" : "notice_id"}=${requestId}`,
      ]}
    >
      <AuthContext.Provider
        value={{
          user: {
            id: "manager",
            username: "manager",
            display_name: "Test yöneticisi",
            permissions: { manage_unit: true },
          },
          refresh: vi.fn(),
        }}
      >
        <Records kind={kind} />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

describe("notification participation deep links", () => {
  beforeEach(() => {
    fixture.calls = [];
    fixture.error = "";
    fixture.responseId = requestId;
  });

  it.each(["projects", "cases"] as const)(
    "opens only the focused request on the %s page without parent details",
    (kind) => {
      const markup = render(kind);
      expect(
        fixture.calls.filter((path) =>
          path?.startsWith("/participation-requests/"),
        ),
      ).toEqual([`/participation-requests/${requestId}`]);
      expect(markup).toContain("Odak talebinin paylaşılabilir özeti");
      expect(markup).toContain("Talep edilen kişi");
      expect(markup).not.toContain("Başka talebin özeti");
      expect(markup).not.toContain("GİZLİ PROJE AYRINTISI");
      expect(markup).not.toContain("GİZLİ VAKA AYRINTISI");
      expect(fixture.calls).not.toContain(`/${kind}/${parentId}`);
    },
  );

  it("shows a localized, retryable error when the focused request is inaccessible", () => {
    fixture.error = "Talep bulunamadı veya bu talebe erişim yetkiniz yok.";
    const markup = render("projects");
    expect(markup).toContain(fixture.error);
    expect(markup).toContain('role="alert"');
    expect(markup).toContain("Yeniden dene");
    expect(markup).not.toContain("Odak talebinin paylaşılabilir özeti");
    expect(markup).not.toContain("Başka talebin özeti");
  });

  it("does not display a mismatched response as the requested notification target", () => {
    fixture.responseId = "10000000-0000-0000-0000-000000000002";
    const markup = render("cases");
    expect(markup).not.toContain("Odak talebinin paylaşılabilir özeti");
    expect(markup).not.toContain("Talep edilen kişi");
  });

  it("opens a case-notice notification directly without unrelated notices", () => {
    const markup = render("cases", "notices");
    expect(
      fixture.calls.filter((path) => path?.startsWith("/case-notices/")),
    ).toEqual([`/case-notices/${requestId}`]);
    expect(markup).toContain("Odak vaka bildirimi");
    expect(markup).toContain("Yalnız hedef bildirimin açıklaması");
    expect(markup).not.toContain("Başka talebin özeti");
    expect(markup).not.toContain("Başka vaka bildirimi");
    expect(markup).not.toContain("Başka bildirimin açıklaması");
    expect(markup).not.toContain("GİZLİ VAKA AYRINTISI");
    expect(fixture.calls).not.toContain(`/cases/${parentId}`);
  });

  it("shows a retryable error for an inaccessible case-notice notification", () => {
    fixture.error = "Vaka bildirimi bulunamadı veya erişim yetkiniz yok.";
    const markup = render("cases", "notices");
    expect(markup).toContain(fixture.error);
    expect(markup).toContain('role="alert"');
    expect(markup).toContain("Yeniden dene");
    expect(markup).not.toContain("Odak vaka bildirimi");
    expect(markup).not.toContain("Yalnız hedef bildirimin açıklaması");
  });
});
