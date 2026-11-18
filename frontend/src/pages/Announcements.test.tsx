import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthContext } from "../lib/auth";
import Announcements from "./Announcements";

const resources = vi.hoisted(() => ({
  records: [] as any[],
  roles: [{ role: "UNIT_HEAD", org_id: "unit" }],
}));

vi.mock("../lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/api")>();
  return {
    ...original,
    useResource: (path: string | null) => ({
      data: path === "/announcements" ? resources.records : [],
      loading: false,
      error: "",
      refresh: vi.fn(),
    }),
  };
});

function render(url = "/announcements") {
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={[url]}>
      <AuthContext.Provider
        value={{
          user: {
            id: "actor",
            username: "actor",
            display_name: "Test Actor",
            roles: resources.roles,
          },
          refresh: vi.fn(),
        }}
      >
        <Announcements />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

describe("announcement dashboard destinations", () => {
  beforeEach(() => {
    resources.records = [
      {
        id: "draft",
        title: "Bekleyen öneri",
        body: "Öneri metni",
        owner_org_id: "unit",
        author_name: "Çalışan",
        status: "DRAFT",
        created_at: "2026-11-18T09:00:00Z",
        permissions: { publish: false, withdraw: false },
      },
      {
        id: "live",
        title: "Yayındaki duyuru",
        body: "Yayın metni",
        owner_org_id: "unit",
        author_name: "Çalışan",
        status: "PUBLISHED",
        created_at: "2026-11-18T09:00:00Z",
      },
    ];
  });

  it("opens the published filter linked from dashboard", () => {
    const markup = render("/announcements?status=PUBLISHED");
    expect(markup).toContain("Yayındaki duyuru");
    expect(markup).not.toContain("Bekleyen öneri");
  });

  it("opens pending proposals and honors server denial despite a locally matching manager role", () => {
    const markup = render("/announcements?status=DRAFT");
    expect(markup).toContain("Bekleyen öneri");
    expect(markup).not.toContain("Yayındaki duyuru");
    expect(markup).not.toContain("announcement-card-action");
  });

  it("offers publication when the server grants the action", () => {
    resources.records[0].permissions.publish = true;
    expect(render("/announcements?status=DRAFT")).toContain(
      "announcement-card-action",
    );
  });

  it("uses the complete list when a status link is malformed", () => {
    const markup = render("/announcements?status=NOT_A_STATUS");
    expect(markup).toContain("Bekleyen öneri");
    expect(markup).toContain("Yayındaki duyuru");
  });
});
