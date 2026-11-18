import { describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";
import {
  notificationDestination,
  notificationIsRead,
  NotificationsStore,
} from "./notifications";
import type { NotificationItem } from "./notifications";

function notification(id: string, read = false): NotificationItem {
  return {
    id,
    title: `Bildirim ${id}`,
    created_at: "2026-11-18T10:00:00Z",
    read_at: read ? "2026-11-18T11:00:00Z" : null,
    is_read: read,
    url: `/work?id=${id}`,
  };
}
function page(
  results: NotificationItem[],
  unread = 0,
  count = results.length,
  next: number | null = null,
) {
  return { results, unread_count: unread, count, next_offset: next };
}
function controller(request = vi.fn()) {
  return { store: new NotificationsStore(request as typeof api), request };
}

describe("notification inbox behavior", () => {
  it("uses the global unread total instead of counting the first page", async () => {
    const { store, request } = controller();
    request.mockResolvedValue(page([notification("1")], 155, 240, 50));
    await store.refresh();
    expect(request.mock.calls[0][0]).toBe(
      "/notifications?status=all&limit=50&offset=0",
    );
    expect(store.getSnapshot()).toMatchObject({
      unreadCount: 155,
      count: 240,
      nextOffset: 50,
      loading: false,
    });
  });

  it("fetches each read filter from the server and keeps the global badge", async () => {
    const { store, request } = controller();
    request
      .mockResolvedValueOnce(page([notification("new")], 61, 90, 50))
      .mockResolvedValueOnce(page([notification("old", true)], 61, 29));
    await store.refresh();
    await store.setFilter("read");
    expect(request.mock.calls[1][0]).toBe(
      "/notifications?status=read&limit=50&offset=0",
    );
    expect(store.getSnapshot()).toMatchObject({
      items: [notification("old", true)],
      unreadCount: 61,
      count: 29,
      nextOffset: null,
      filter: "read",
    });
  });

  it("loads more without duplicate rows and refreshes the authorized loaded pages", async () => {
    const { store, request } = controller();
    const first = Array.from({ length: 50 }, (_, i) => notification(String(i)));
    request
      .mockResolvedValueOnce(page(first, 51, 51, 50))
      .mockResolvedValueOnce(page([first[49], notification("last")], 51, 51))
      .mockResolvedValueOnce(page(first, 50, 50));
    await store.refresh();
    await store.loadMore();
    expect(request.mock.calls[1][0]).toBe(
      "/notifications?status=all&limit=50&offset=50",
    );
    expect(store.getSnapshot().items).toHaveLength(51);
    await store.refresh();
    expect(store.getSnapshot().items).toHaveLength(50);
    expect(
      store.getSnapshot().items.find((row) => row.id === "last"),
    ).toBeUndefined();
    expect(store.getSnapshot().nextOffset).toBeNull();
  });

  it("revalidates a second loaded page without retaining its stale contents", async () => {
    const { store, request } = controller();
    const first = Array.from({ length: 50 }, (_, i) => notification(String(i)));
    request
      .mockResolvedValueOnce(page(first, 51, 51, 50))
      .mockResolvedValueOnce(page([notification("last")], 51, 51))
      .mockResolvedValueOnce(page(first, 50, 51, 50))
      .mockResolvedValueOnce(page([notification("replacement", true)], 50, 51));
    await store.refresh();
    await store.loadMore();
    await store.refresh();
    expect(request.mock.calls[3][0]).toContain("offset=50");
    expect(store.getSnapshot().items.at(-1)?.id).toBe("replacement");
    expect(store.getSnapshot().items.some((row) => row.id === "last")).toBe(
      false,
    );
  });

  it("persists opening as read and restores server state on the next refresh", async () => {
    const { store, request } = controller();
    request
      .mockResolvedValueOnce(page([notification("1")], 1))
      .mockResolvedValueOnce(notification("1", true))
      .mockResolvedValueOnce(page([notification("1", true)]))
      .mockResolvedValueOnce(page([notification("1", true)]));
    await store.refresh();
    const opened = await store.setRead("1", true);
    expect(request.mock.calls[1]).toEqual([
      "/notifications/1/read",
      { method: "POST", body: { read: true } },
    ]);
    expect(opened && notificationDestination(opened)).toBe("/work?id=1");
    await store.refresh();
    expect(store.getSnapshot().unreadCount).toBe(0);
    expect(notificationIsRead(store.getSnapshot().items[0])).toBe(true);
  });

  it("does not repeat a row when a new notification shifts offsets during refresh", async () => {
    const { store, request } = controller();
    const first = Array.from({ length: 50 }, (_, i) => notification(String(i)));
    request
      .mockResolvedValueOnce(page(first, 51, 51, 50))
      .mockResolvedValueOnce(page([notification("last")], 51, 51))
      .mockResolvedValueOnce(page(first, 51, 51, 50))
      .mockResolvedValueOnce(page([first[49], notification("last")], 52, 52));
    await store.refresh();
    await store.loadMore();
    await store.refresh();
    const ids = store.getSnapshot().items.map((item) => item.id);
    expect(ids).toHaveLength(51);
    expect(new Set(ids).size).toBe(ids.length);
    expect(store.getSnapshot().count).toBe(52);
  });

  it("persists marking one row unread without marking any other row", async () => {
    const { store, request } = controller();
    request
      .mockResolvedValueOnce(
        page([notification("1", true), notification("2", true)]),
      )
      .mockResolvedValueOnce(notification("1"))
      .mockResolvedValueOnce(
        page([notification("1"), notification("2", true)], 1),
      );
    await store.refresh();
    await store.setRead("1", false);
    expect(request.mock.calls[1][1]).toEqual({
      method: "POST",
      body: { read: false },
    });
    expect(store.getSnapshot().unreadCount).toBe(1);
    expect(notificationIsRead(store.getSnapshot().items[1])).toBe(true);
    expect(
      request.mock.calls.some(([path]) => path.includes("mark-all-read")),
    ).toBe(false);
  });

  it("ignores a slow polling response that arrives after a read was saved", async () => {
    const { store, request } = controller();
    let finishPoll!: (value: ReturnType<typeof page>) => void;
    request
      .mockImplementationOnce(
        () => new Promise((resolve) => (finishPoll = resolve)),
      )
      .mockResolvedValueOnce(notification("1", true))
      .mockResolvedValueOnce(page([notification("1", true)]));
    const polling = store.refresh();
    const oldSignal = request.mock.calls[0][1].signal;
    await store.setRead("1", true);
    expect(oldSignal.aborted).toBe(true);
    finishPoll(page([notification("1")], 1));
    await polling;
    expect(store.getSnapshot().unreadCount).toBe(0);
    expect(notificationIsRead(store.getSnapshot().items[0])).toBe(true);
  });

  it("does not open a revoked source and removes its old title after a rejected read", async () => {
    const { store, request } = controller();
    request
      .mockResolvedValueOnce(page([notification("secret")], 1))
      .mockRejectedValueOnce(new ApiError("Kayıt bulunamadı.", 404))
      .mockResolvedValueOnce(page([]));
    await store.refresh();
    expect(await store.setRead("secret", true)).toBeNull();
    expect(store.getSnapshot()).toMatchObject({
      items: [],
      unreadCount: 0,
      error: "Kayıt bulunamadı.",
      busy: null,
    });
  });

  it("clears cached titles and counters when inbox access is denied", async () => {
    const { store, request } = controller();
    request
      .mockResolvedValueOnce(page([notification("secret")], 1))
      .mockRejectedValueOnce(new ApiError("Erişim yok.", 403));
    await store.refresh();
    await store.refresh();
    expect(store.getSnapshot()).toMatchObject({
      items: [],
      unreadCount: 0,
      count: 0,
    });
  });

  it("removes a rejected source even if the follow-up inbox refresh is offline", async () => {
    const { store, request } = controller();
    request
      .mockResolvedValueOnce(page([notification("secret")], 1))
      .mockRejectedValueOnce(new ApiError("Kayıt bulunamadı.", 404))
      .mockRejectedValueOnce(new ApiError("Sunucuya ulaşılamıyor.", 0));
    await store.refresh();
    expect(await store.setRead("secret", true)).toBeNull();
    expect(store.getSnapshot()).toMatchObject({
      items: [],
      unreadCount: 0,
      count: 0,
    });
  });

  it("marks all only through its explicit action, independently of the current filter", async () => {
    const { store, request } = controller();
    request
      .mockResolvedValueOnce(page([notification("1")], 1))
      .mockResolvedValueOnce(page([notification("2", true)], 1))
      .mockResolvedValueOnce({ updated: 1 })
      .mockResolvedValueOnce(
        page([notification("1", true), notification("2", true)]),
      );
    await store.refresh();
    await store.setFilter("read");
    expect(request.mock.calls).toHaveLength(2);
    await store.markAllRead();
    expect(request.mock.calls[2]).toEqual([
      "/notifications/mark-all-read",
      { method: "POST", body: {} },
    ]);
    expect(store.getSnapshot().unreadCount).toBe(0);
    expect(request.mock.calls[3][0]).toContain("status=read");
  });

  it("does not carry a pending previous user's inbox into a disposed session", async () => {
    const { store, request } = controller();
    let finish!: (value: ReturnType<typeof page>) => void;
    request.mockImplementationOnce(
      () => new Promise((resolve) => (finish = resolve)),
    );
    const pending = store.refresh();
    store.dispose();
    finish(page([notification("previous-user")], 1));
    await pending;
    expect(store.getSnapshot().items).toEqual([]);
  });

  it("uses only explicit local canonical targets and tolerates legacy read indicators", () => {
    expect(
      notificationDestination({ ...notification("1"), url: null }),
    ).toBeNull();
    expect(
      notificationDestination({
        ...notification("1"),
        url: "https://other.test",
      }),
    ).toBeNull();
    expect(
      notificationDestination({ ...notification("1"), url: "//other.test" }),
    ).toBeNull();
    expect(
      notificationDestination({ ...notification("1"), url: "/work\\other" }),
    ).toBeNull();
    expect(
      notificationDestination({ ...notification("1"), url: "/settings" }),
    ).toBeNull();
    expect(notificationIsRead({ ...notification("1"), is_read: true })).toBe(
      true,
    );
  });
});
