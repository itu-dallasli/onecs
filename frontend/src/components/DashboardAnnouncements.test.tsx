import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import DashboardAnnouncements from "./DashboardAnnouncements";

const published = Array.from({ length: 5 }, (_, index) => ({
  id: `announcement-${index}`,
  title: `Yayın ${index + 1}`,
  body: "Güncel ekip duyurusu",
  starts_at: "2026-11-18T09:00:00Z",
  pinned: index === 0,
  all_cs: index === 0,
}));

function render(props: Parameters<typeof DashboardAnnouncements>[0]) {
  return renderToStaticMarkup(
    <MemoryRouter>
      <DashboardAnnouncements {...props} />
    </MemoryRouter>,
  );
}

describe("dashboard announcement visibility", () => {
  it("shows every supplied published and pending item with a direct detail link", () => {
    const markup = render({
      published,
      pending: [
        { id: "pending-id", title: "Ekip önerisi", body: "Karar bekliyor" },
      ],
      counts: { published: 5, pending: 1 },
    });
    expect(markup).toContain("Yayındaki anonslar");
    expect(markup).toContain("Yayın kararı bekleyen");
    for (const item of published) {
      expect(markup).toContain(item.title);
      expect(markup).toContain(`href="/announcements?id=${item.id}"`);
    }
    expect(markup).toContain("Ekip önerisi");
    expect(markup).toContain('href="/announcements?id=pending-id"');
    expect(markup).toContain("Sabit anons");
    expect(markup).toContain("Tüm CS");
  });

  it("makes limited previews explicit and links each group to the matching status filter", () => {
    const markup = render({
      published,
      pending: [],
      counts: { published: 9, pending: 0 },
    });
    expect(markup).toContain("9 anonsun tümünü gör (5 gösteriliyor)");
    expect(markup).toContain('href="/announcements?status=PUBLISHED"');
    expect(markup).toContain('href="/announcements?status=DRAFT"');
    expect(markup).toContain("Yayın kararı bekleyen bir anonsunuz bulunmuyor.");
  });

  it("keeps both sections present when no visible announcements exist", () => {
    const markup = render({ published: [], pending: [] });
    expect(markup).toContain("Yayındaki anonslar");
    expect(markup).toContain("Size yönelik aktif bir yayın bulunmuyor.");
    expect(markup).toContain("Yayın kararı bekleyen bir anonsunuz bulunmuyor.");
    expect(markup).not.toContain("dashboard-announcement-link");
  });
});
