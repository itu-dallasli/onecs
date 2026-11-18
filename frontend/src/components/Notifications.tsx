import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Bell, CheckCheck, Mail, MailOpen, RefreshCw } from "lucide-react";
import { date } from "../lib/api";
import {
  notificationDestination,
  notificationIsRead,
  NotificationsStore,
} from "../lib/notifications";
import type {
  NotificationFilter,
  NotificationItem,
  NotificationsState,
} from "../lib/notifications";
import { Badge, Button, Drawer, ErrorState, Loading } from "./ui";
import "../styles/notifications.css";

export function NotificationList({
  state,
  onFilter,
  onRefresh,
  onOpen,
  onRead,
  onAllRead,
  onMore,
}: {
  state: NotificationsState;
  onFilter: (filter: NotificationFilter) => void;
  onRefresh: () => void;
  onOpen: (item: NotificationItem) => void;
  onRead: (item: NotificationItem, read: boolean) => void;
  onAllRead: () => void;
  onMore: () => void;
}) {
  return (
    <div className="onecs-notifications">
      <div className="popover-title">
        <p>
          Atamalarınızı ve önemli gelişmeleri buradan izleyin. Bir bildirimi
          açtığınızda okundu olarak işaretlenir.
        </p>
        <Badge>{state.unreadCount} okunmamış</Badge>
      </div>
      <div className="notification-toolbar">
        <div
          className="notification-filters"
          role="group"
          aria-label="Bildirim görünümü"
        >
          {(
            [
              ["all", "Tümü"],
              ["unread", "Okunmamış"],
              ["read", "Okunmuş"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              className={state.filter === value ? "selected" : ""}
              aria-pressed={state.filter === value}
              disabled={!!state.busy}
              onClick={() => onFilter(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="notification-actions">
          <Button
            variant="secondary"
            disabled={!!state.busy || state.loading}
            onClick={onRefresh}
            aria-label="Bildirimleri yenile"
          >
            <RefreshCw size={14} />
            Yenile
          </Button>
          <Button
            variant="secondary"
            disabled={!!state.busy || state.loading || !state.unreadCount}
            onClick={onAllRead}
          >
            <CheckCheck size={14} />
            Tümünü okundu işaretle
          </Button>
        </div>
      </div>
      {state.error && <ErrorState message={state.error} onRetry={onRefresh} />}
      {state.loading ? (
        <Loading label="Bildirimler yükleniyor…" />
      ) : (
        <>
          <div className="notification-list" aria-busy={!!state.busy}>
            {state.items.map((item) => {
              const read = notificationIsRead(item);
              return (
                <article
                  className={`notification-entry ${read ? "read" : "unread"}`}
                  key={item.id}
                >
                  <button
                    className={`notification-row ${read ? "" : "unread"}`}
                    disabled={!!state.busy}
                    onClick={() => onOpen(item)}
                    aria-label={`${item.title} · ${read ? "Okundu" : "Okunmadı"}`}
                  >
                    <div className="notification-heading">
                      <span
                        className="notification-read-dot"
                        aria-hidden="true"
                      />
                      <strong>{item.title}</strong>
                      <span className={`read-state ${read ? "read" : "new"}`}>
                        {read ? "Okundu" : "Okunmadı"}
                      </span>
                    </div>
                    {item.message && <span>{item.message}</span>}
                    <small>{date(item.created_at, true)}</small>
                  </button>
                  <div className="notification-entry-actions">
                    <button
                      className="notification-read-toggle"
                      disabled={!!state.busy}
                      onClick={() => onRead(item, !read)}
                      aria-label={`${item.title} bildirimini ${read ? "okunmadı" : "okundu"} işaretle`}
                    >
                      {read ? <Mail size={14} /> : <MailOpen size={14} />}
                      {state.busy === item.id
                        ? "Kaydediliyor…"
                        : read
                          ? "Okunmadı işaretle"
                          : "Okundu işaretle"}
                    </button>
                  </div>
                </article>
              );
            })}
            {!state.items.length && !state.error && (
              <p className="notification-empty">
                Bu görünümde bildiriminiz bulunmuyor.
              </p>
            )}
          </div>
          {state.items.length > 0 && (
            <div className="notification-pagination">
              <small>
                {state.count} bildirimin {state.items.length} tanesi
                gösteriliyor.
              </small>
              {state.nextOffset !== null && (
                <Button
                  variant="secondary"
                  disabled={!!state.busy || state.loadingMore}
                  onClick={onMore}
                >
                  {state.loadingMore ? "Yükleniyor…" : "Daha fazla göster"}
                </Button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function Notifications({
  ownerKey,
  onOpen,
}: {
  ownerKey: string;
  onOpen: () => void;
}) {
  const store = useMemo(() => new NotificationsStore(), [ownerKey]);
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    store.activate();
    void store.refresh();
    const timer = window.setInterval(() => void store.refresh(), 15000);
    const refresh = () => {
      if (document.visibilityState !== "hidden") void store.refresh();
    };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
      store.dispose();
    };
  }, [store]);
  useEffect(() => setOpen(false), [location.key, ownerKey]);

  return (
    <div className="topbar-popover">
      <button
        className="icon-button notification-button"
        aria-label={
          !state.loaded
            ? state.error
              ? "Bildirimler, bağlantı hatası"
              : "Bildirimler yükleniyor"
            : `Bildirimler, ${state.unreadCount} okunmamış`
        }
        aria-expanded={open}
        onClick={() => {
          setOpen(!open);
          if (!open) {
            onOpen();
            void store.refresh();
          }
        }}
      >
        <Bell size={18} />
        {state.unreadCount > 0 && (
          <span className="notification-count" aria-hidden="true">
            {state.unreadCount > 99 ? "99+" : state.unreadCount}
          </span>
        )}
      </button>
      {open && (
        <Drawer
          title="Bildirimler"
          subtitle="GÜNCEL GELİŞMELER VE ATAMALAR"
          onClose={() => setOpen(false)}
          wide
        >
          <NotificationList
            state={state}
            onFilter={(filter) => void store.setFilter(filter)}
            onRefresh={() => void store.refresh()}
            onRead={(item, read) => void store.setRead(item.id, read)}
            onAllRead={() => void store.markAllRead()}
            onMore={() => void store.loadMore()}
            onOpen={async (item) => {
              const updated = await store.setRead(item.id, true);
              const destination = updated && notificationDestination(updated);
              if (destination) {
                setOpen(false);
                navigate(destination);
              }
            }}
          />
        </Drawer>
      )}
    </div>
  );
}
