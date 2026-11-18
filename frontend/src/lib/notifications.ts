import { api, ApiError, list } from "./api";

export type NotificationFilter = "all" | "unread" | "read";
export type NotificationItem = {
  id: string;
  title: string;
  message?: string;
  read_at: string | null;
  is_read: boolean;
  created_at: string;
  url?: string | null;
};
export type NotificationsState = {
  items: NotificationItem[];
  unreadCount: number;
  count: number;
  nextOffset: number | null;
  filter: NotificationFilter;
  loading: boolean;
  loadingMore: boolean;
  loaded: boolean;
  busy: string | null;
  error: string;
};
type Request = typeof api;
type NotificationPage = {
  results: NotificationItem[];
  count: number;
  unread_count: number;
  next_offset: number | null;
};

export function notificationIsRead(item: NotificationItem) {
  return Boolean(item.read_at || item.is_read);
}

export function notificationDestination(item: NotificationItem) {
  // Notification links are canonical application routes supplied by the server.
  // Unknown/internal notifications remain readable without a fabricated target.
  const value = item.url;
  if (
    !value ||
    /[\\\s]/.test(value) ||
    !/^\/(projects|work|cases|community|announcements|events|credentials)(?:\?|$)/.test(
      value,
    )
  )
    return null;
  return value;
}

/** Owns refresh and mutation ordering so an older poll cannot undo a read. */
export class NotificationsStore {
  private state: NotificationsState = {
    items: [],
    unreadCount: 0,
    count: 0,
    nextOffset: null,
    filter: "all",
    loading: true,
    loadingMore: false,
    loaded: false,
    busy: null,
    error: "",
  };
  private listeners = new Set<() => void>();
  private generation = 0;
  private controller: AbortController | null = null;
  private active = true;

  constructor(private request: Request = api) {}

  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };
  activate = () => {
    this.active = true;
  };
  dispose = () => {
    this.active = false;
    this.cancelLoad();
  };
  private update(change: Partial<NotificationsState>) {
    if (!this.active) return;
    this.state = { ...this.state, ...change };
    for (const listener of this.listeners) listener();
  }
  private cancelLoad() {
    this.generation += 1;
    this.controller?.abort();
    this.controller = null;
  }
  private pagePath(offset: number) {
    return `/notifications?status=${this.state.filter}&limit=50&offset=${offset}`;
  }

  refresh = async (duringMutation = false) => {
    if (
      !this.active ||
      (!duringMutation && (this.state.busy || this.controller))
    )
      return;
    this.cancelLoad();
    const generation = this.generation;
    const controller = new AbortController();
    this.controller = controller;
    const desiredPages = Math.max(1, Math.ceil(this.state.items.length / 50));
    this.update({ loading: !this.state.loaded, loadingMore: false });
    try {
      let offset: number | null = 0;
      let page: NotificationPage;
      const items: NotificationItem[] = [];
      const seenIds = new Set<string>();
      let loadedPages = 0;
      // Refresh every loaded page; retaining the old tail could expose a source
      // after its access has been revoked or show a stale read state.
      do {
        page = await this.request<NotificationPage>(this.pagePath(offset), {
          signal: controller.signal,
        });
        if (!this.active || generation !== this.generation) return;
        for (const item of list<NotificationItem>(page)) {
          if (!seenIds.has(item.id)) {
            seenIds.add(item.id);
            items.push(item);
          }
        }
        loadedPages += 1;
        offset = page.next_offset ?? null;
      } while (offset !== null && offset > 0 && loadedPages < desiredPages);
      this.update({
        items,
        count: page.count,
        unreadCount: page.unread_count,
        nextOffset: offset,
        loaded: true,
        loading: false,
        error: "",
      });
    } catch (error) {
      if (!this.active || generation !== this.generation) return;
      const inaccessible =
        error instanceof ApiError && [401, 403, 404].includes(error.status);
      this.update({
        ...(inaccessible
          ? { items: [], count: 0, unreadCount: 0, nextOffset: null }
          : {}),
        loading: false,
        error:
          error instanceof Error ? error.message : "Bildirimler alınamadı.",
      });
    } finally {
      if (generation === this.generation) this.controller = null;
    }
  };

  setFilter = async (filter: NotificationFilter) => {
    if (this.state.busy || filter === this.state.filter) return;
    this.cancelLoad();
    this.update({
      filter,
      items: [],
      count: 0,
      nextOffset: null,
      loaded: false,
      loading: true,
      error: "",
    });
    await this.refresh();
  };

  loadMore = async () => {
    if (
      !this.active ||
      this.controller ||
      this.state.busy ||
      this.state.nextOffset === null
    )
      return;
    const generation = this.generation;
    const controller = new AbortController();
    this.controller = controller;
    this.update({ loadingMore: true, error: "" });
    try {
      const page = await this.request<NotificationPage>(
        this.pagePath(this.state.nextOffset),
        { signal: controller.signal },
      );
      if (!this.active || generation !== this.generation) return;
      const currentIds = new Set(this.state.items.map((item) => item.id));
      this.update({
        items: [
          ...this.state.items,
          ...list<NotificationItem>(page).filter(
            (item) => !currentIds.has(item.id),
          ),
        ],
        count: page.count,
        unreadCount: page.unread_count,
        nextOffset: page.next_offset ?? null,
        loadingMore: false,
      });
    } catch (error) {
      if (!this.active || generation !== this.generation) return;
      const inaccessible =
        error instanceof ApiError && [401, 403, 404].includes(error.status);
      this.update({
        ...(inaccessible
          ? { items: [], count: 0, unreadCount: 0, nextOffset: null }
          : {}),
        loadingMore: false,
        error:
          error instanceof Error ? error.message : "Bildirimler alınamadı.",
      });
    } finally {
      if (generation === this.generation) this.controller = null;
    }
  };

  setRead = async (
    id: string,
    read: boolean,
  ): Promise<NotificationItem | null> => {
    if (!this.active || this.state.busy) return null;
    this.cancelLoad();
    this.update({ busy: id, loadingMore: false, error: "" });
    try {
      const item = await this.request<NotificationItem>(
        `/notifications/${encodeURIComponent(id)}/read`,
        { method: "POST", body: { read } },
      );
      if (!this.active) return null;
      await this.refresh(true);
      return this.active ? item : null;
    } catch (error) {
      if (error instanceof ApiError && [403, 404].includes(error.status)) {
        const item = this.state.items.find((row) => row.id === id);
        this.update({
          items: this.state.items.filter((row) => row.id !== id),
          count: Math.max(0, this.state.count - (item ? 1 : 0)),
          unreadCount: Math.max(
            0,
            this.state.unreadCount -
              (item && !notificationIsRead(item) ? 1 : 0),
          ),
        });
      }
      await this.refresh(true);
      this.update({
        error:
          error instanceof Error ? error.message : "Bildirim güncellenemedi.",
      });
      return null;
    } finally {
      this.update({ busy: null });
    }
  };

  markAllRead = async () => {
    if (!this.active || this.state.busy || !this.state.unreadCount) return;
    this.cancelLoad();
    this.update({ busy: "all", loadingMore: false, error: "" });
    try {
      await this.request("/notifications/mark-all-read", {
        method: "POST",
        body: {},
      });
      if (this.active) await this.refresh(true);
    } catch (error) {
      await this.refresh(true);
      this.update({
        error:
          error instanceof Error
            ? error.message
            : "Bildirimler güncellenemedi.",
      });
    } finally {
      this.update({ busy: null });
    }
  };
}
