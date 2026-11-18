import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { AlertCircle, ChevronRight, Inbox, X } from "lucide-react";
import ProductLogo from "./ProductLogo";
import "../styles/loading.css";
export function Button({
  children,
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
}) {
  return (
    <button className={`btn btn-${variant} ${className}`} {...props}>
      {children}
    </button>
  );
}
export function PageHeader({
  title,
  description,
  eyebrow,
  actions,
}: {
  title: string;
  description?: string;
  eyebrow?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}
export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={`card ${className}`}>{children}</section>;
}
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
export function EmptyState({
  title,
  description,
  icon,
  actions,
}: {
  title: string;
  description?: string;
  icon?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="empty-state">
      {icon || <Inbox size={30} />}
      <strong>{title}</strong>
      {description && <p>{description}</p>}
      {actions}
    </div>
  );
}
export function Loading({
  label = "Çalışma alanı yükleniyor…",
}: {
  label?: string;
}) {
  return (
    <div
      className="loading onecs-loading"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <div className="onecs-loading-emblem" aria-hidden="true">
        <span className="onecs-loading-orbit" />
        <span className="onecs-loading-orbit-inner" />
        <ProductLogo className="onecs-loading-logo" decorative />
      </div>
      <div className="onecs-loading-copy">
        <span className="onecs-loading-label">{label}</span>
        <span className="onecs-loading-dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
      </div>
    </div>
  );
}
export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="error-state" role="alert">
      <AlertCircle size={19} />
      <span>{message}</span>
      {onRetry && <button onClick={onRetry}>Yeniden dene</button>}
    </div>
  );
}
export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
export function SectionTitle({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="section-title">
      <div>
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      {actions}
    </div>
  );
}
const modalStack: HTMLElement[] = [];
let unlockedBodyOverflow = "";
const priorInertState = new Map<HTMLElement, boolean>();
function modalHost() {
  let host = document.getElementById("onecs-modal-root");
  if (!host) {
    host = document.createElement("div");
    host.id = "onecs-modal-root";
    document.body.append(host);
  }
  return host;
}
function activeModal() {
  return modalStack[modalStack.length - 1];
}
function focusableElements(root: HTMLElement) {
  return Array.from(
    root.querySelectorAll<HTMLElement>(
      'button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),a[href],[tabindex="0"]',
    ),
  ).filter(
    (el) =>
      el.tabIndex >= 0 &&
      el.getClientRects().length > 0 &&
      getComputedStyle(el).visibility !== "hidden",
  );
}
export function Drawer({
  title,
  subtitle,
  children,
  onClose,
  wide = false,
  className = "",
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    const previous = document.activeElement as HTMLElement | null;
    if (modalStack.length === 0) {
      unlockedBodyOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      for (const node of Array.from(document.body.children)) {
        if (node instanceof HTMLElement && node.id !== "onecs-modal-root") {
          priorInertState.set(node, node.inert);
          node.inert = true;
        }
      }
    }
    modalStack.push(dialog);
    for (const modal of modalStack) modal.inert = modal !== dialog;
    dialog.focus({ preventScroll: true });
    const keyboard = (event: KeyboardEvent) => {
      if (activeModal() !== dialog) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        closeRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const elements = focusableElements(dialog);
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (!first) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      if (
        event.shiftKey &&
        (document.activeElement === first || document.activeElement === dialog)
      ) {
        event.preventDefault();
        last.focus();
      } else if (
        !event.shiftKey &&
        (document.activeElement === last ||
          document.activeElement === dialog ||
          !dialog.contains(document.activeElement))
      ) {
        event.preventDefault();
        first.focus();
      }
    };
    const focus = (event: FocusEvent) => {
      if (activeModal() === dialog && !dialog.contains(event.target as Node)) {
        (focusableElements(dialog)[0] || dialog).focus({ preventScroll: true });
      }
    };
    document.addEventListener("keydown", keyboard, true);
    document.addEventListener("focusin", focus);
    return () => {
      document.removeEventListener("keydown", keyboard, true);
      document.removeEventListener("focusin", focus);
      const index = modalStack.indexOf(dialog);
      if (index >= 0) modalStack.splice(index, 1);
      for (const modal of modalStack) modal.inert = modal !== activeModal();
      if (!modalStack.length) {
        document.body.style.overflow = unlockedBodyOverflow;
        for (const [node, wasInert] of priorInertState) {
          if (node.isConnected) node.inert = wasInert;
        }
        priorInertState.clear();
      }
      if (previous?.isConnected && !previous.closest("[inert]")) {
        previous.focus({ preventScroll: true });
      } else activeModal()?.focus({ preventScroll: true });
    };
  }, []);
  return createPortal(
    <div className="drawer-layer onecs-modal-layer">
      <button
        type="button"
        className="drawer-scrim"
        tabIndex={-1}
        aria-hidden="true"
        onClick={() => {
          if (activeModal() === ref.current) closeRef.current();
        }}
      />
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`drawer onecs-modal ${wide ? "drawer-wide" : ""} ${className}`}
      >
        <div className="drawer-header">
          <div>
            {subtitle && <div className="eyebrow">{subtitle}</div>}
            <h2 id={titleId}>{title}</h2>
          </div>
          <button
            type="button"
            className="icon-button modal-close"
            aria-label="Pencereyi kapat"
            onClick={() => closeRef.current()}
          >
            <X size={21} />
          </button>
        </div>
        <div className="drawer-body">{children}</div>
      </div>
    </div>,
    modalHost(),
  );
}
export function BreadcrumbAction({
  children,
  onClick,
}: {
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button className="text-button" onClick={onClick}>
      {children}
      <ChevronRight size={14} />
    </button>
  );
}
export const statusLabels: Record<string, string> = {
  revision: "Düzeltme istendi",
  verifying: "Doğrulama bekliyor",
  ready: "Hazır",
  generating: "Hazırlanıyor",
  directorate: "Direktörlük",
  unit: "Birim",
  team: "Ekip",
  draft: "Taslak",
  content_approved: "İçerik onaylandı",
  withdrawn: "Geri çekildi",
  converted: "Vakaya dönüştürüldü",
  dismissed: "Reddedildi",
  pending: "Onay bekliyor",
  submitted: "Onay bekliyor",
  revision_requested: "Düzeltme istendi",
  changes_requested: "Düzeltme istendi",
  approved: "Onaylandı",
  active: "Devam ediyor",
  planned: "Planlandı",
  in_progress: "Devam ediyor",
  open: "Açık",
  backlog: "İş havuzu",
  waiting: "Beklemede",
  blocked: "Engelli",
  verification: "Doğrulama bekliyor",
  pending_verification: "Doğrulama bekliyor",
  completed: "Tamamlandı",
  closed: "Kapandı",
  cancelled: "İptal",
  rejected: "Reddedildi",
  new: "Yeni",
  assessing: "Değerlendiriliyor",
  published: "Yayında",
  normal: "Normal",
  high: "Yüksek",
  critical: "Kritik",
  accepted: "Kabul edildi",
};
export function Status({ value }: { value?: string }) {
  const s = (value || "").toLowerCase();
  return (
    <Badge
      tone={
        ["critical", "blocked", "rejected", "overdue"].includes(s)
          ? "danger"
          : [
                "high",
                "pending",
                "submitted",
                "waiting",
                "verification",
                "pending_verification",
                "verifying",
                "generating",
              ].includes(s)
            ? "warning"
            : [
                  "completed",
                  "closed",
                  "approved",
                  "published",
                  "accepted",
                ].includes(s)
              ? "success"
              : "neutral"
      }
    >
      {statusLabels[s] || value || "—"}
    </Badge>
  );
}
