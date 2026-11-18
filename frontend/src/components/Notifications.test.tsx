import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { NotificationList } from "./Notifications";
import type { NotificationsState } from "../lib/notifications";

function render(change: Partial<NotificationsState> = {}) {
  const state: NotificationsState = {
    items: [
      {
        id: "notice-1",
        title: "Yeni atama",
        message: "Sorumlusu olduğunuz iş güncellendi.",
        read_at: null,
        is_read: false,
        created_at: "2026-11-18T10:00:00Z",
        url: "/work?id=work-1",
      },
    ],
    unreadCount: 124,
    count: 200,
    nextOffset: 50,
    filter: "all",
    loading: false,
    loadingMore: false,
    loaded: true,
    busy: null,
    error: "",
    ...change,
  };
  return renderToStaticMarkup(
    <NotificationList
      state={state}
      onFilter={vi.fn()}
      onRefresh={vi.fn()}
      onOpen={vi.fn()}
      onRead={vi.fn()}
      onAllRead={vi.fn()}
      onMore={vi.fn()}
    />,
  );
}

describe("notification list presentation", () => {
  it("shows the server unread total, paged history and separate read actions", () => {
    const markup = render();
    expect(markup).toContain("124 okunmamış");
    expect(markup).toContain("200 bildirimin 1 tanesi gösteriliyor.");
    expect(markup).toContain("Daha fazla göster");
    expect(markup).toContain("Tümünü okundu işaretle");
    expect(markup).toContain('aria-label="Yeni atama · Okunmadı"');
    expect(markup).toContain(
      'aria-label="Yeni atama bildirimini okundu işaretle"',
    );
    expect(markup).not.toContain("<button><button");
  });

  it("provides an unread action for a read row and disables mutation buttons while saving", () => {
    const markup = render({
      busy: "notice-1",
      items: [
        {
          id: "notice-1",
          title: "Yeni atama",
          read_at: "2026-11-18T10:30:00Z",
          is_read: true,
          created_at: "2026-11-18T10:00:00Z",
        },
      ],
    });
    expect(markup).toContain(
      'aria-label="Yeni atama bildirimini okunmadı işaretle"',
    );
    expect(markup).toContain("Kaydediliyor…");
    expect(markup).toContain('aria-busy="true"');
    expect(markup.match(/<button(?![^>]*disabled)[^>]*>/g)).toBeNull();
  });

  it("shows a loading state instead of a misleading empty inbox", () => {
    const markup = render({ items: [], loading: true, loaded: false });
    expect(markup).toContain("Bildirimler yükleniyor…");
    expect(markup).not.toContain("Bu görünümde bildiriminiz bulunmuyor.");
  });

  it("makes inbox failures retryable without claiming there are no notifications", () => {
    const markup = render({ items: [], error: "Sunucuya ulaşılamıyor." });
    expect(markup).toContain("Sunucuya ulaşılamıyor.");
    expect(markup).toContain("Yeniden dene");
    expect(markup).not.toContain("Bu görünümde bildiriminiz bulunmuyor.");
  });
});
