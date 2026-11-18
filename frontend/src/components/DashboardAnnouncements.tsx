import { ArrowRight, BellRing, Clock3, Pin } from "lucide-react";
import { Link } from "react-router-dom";
import { date, list } from "../lib/api";
import { Badge, Card, SectionTitle } from "./ui";
import "../styles/dashboard-announcements.css";

type DashboardAnnouncement = {
  id: string;
  title: string;
  body?: string;
  all_cs?: boolean;
  pinned?: boolean;
  starts_at?: string;
  created_at?: string;
};

type Props = {
  published: unknown;
  pending: unknown;
  counts?: { published?: number; pending?: number };
};

export default function DashboardAnnouncements({
  published,
  pending,
  counts,
}: Props) {
  const groups = [
    {
      key: "published",
      title: "Yayındaki anonslar",
      description: "Size duyurulan güncel yayınlar",
      status: "PUBLISHED",
      items: list<DashboardAnnouncement>(published),
      count: counts?.published,
      empty: "Size yönelik aktif bir yayın bulunmuyor.",
      icon: BellRing,
    },
    {
      key: "pending",
      title: "Yayın kararı bekleyen",
      description: "Hazırladığınız veya yayın kararı verebildiğiniz öneriler",
      status: "DRAFT",
      items: list<DashboardAnnouncement>(pending),
      count: counts?.pending,
      empty: "Yayın kararı bekleyen bir anonsunuz bulunmuyor.",
      icon: Clock3,
    },
  ];
  return (
    <Card className="dashboard-announcements">
      <SectionTitle title="Anonslar" actions={<BellRing size={17} />} />
      {groups.map((group) => {
        const count =
          typeof group.count === "number" && Number.isInteger(group.count)
            ? Math.max(group.count, group.items.length)
            : group.items.length;
        return (
          <section
            key={group.key}
            className={`dashboard-announcement-group is-${group.key}`}
            aria-labelledby={`dashboard-announcements-${group.key}`}
          >
            <div className="dashboard-announcement-heading">
              <group.icon size={16} aria-hidden="true" />
              <h3 id={`dashboard-announcements-${group.key}`}>{group.title}</h3>
              <Badge
                tone={group.key === "pending" && count ? "warning" : "neutral"}
              >
                {count}
              </Badge>
            </div>
            <p className="dashboard-announcement-description">
              {group.description}
            </p>
            {group.items.length ? (
              <div className="dashboard-announcement-list">
                {group.items.map((announcement) => (
                  <Link
                    key={announcement.id}
                    className="dashboard-announcement-link"
                    to={`/announcements?id=${encodeURIComponent(announcement.id)}`}
                  >
                    <div className="dashboard-announcement-meta">
                      <Badge
                        tone={group.key === "published" ? "success" : "warning"}
                      >
                        {group.key === "published"
                          ? "Yayında"
                          : "Yayın kararı bekliyor"}
                      </Badge>
                      {announcement.pinned && (
                        <Pin size={12} aria-label="Sabit anons" />
                      )}
                      <span>
                        {announcement.all_cs ? "Tüm CS" : "Seçili ekipler"}
                      </span>
                    </div>
                    <strong>{announcement.title}</strong>
                    {announcement.body && <p>{announcement.body}</p>}
                    <small>
                      {date(
                        group.key === "published"
                          ? announcement.starts_at
                          : announcement.created_at,
                        true,
                      )}
                      <ArrowRight size={14} aria-hidden="true" />
                    </small>
                  </Link>
                ))}
              </div>
            ) : (
              <p className="dashboard-announcement-empty">{group.empty}</p>
            )}
            <Link
              className="dashboard-announcement-all"
              to={`/announcements?status=${group.status}`}
            >
              {count > group.items.length
                ? `${count} anonsun tümünü gör (${group.items.length} gösteriliyor)`
                : group.key === "published"
                  ? "Yayındaki anonsları aç"
                  : "Bekleyen anonsları aç"}
              <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </section>
        );
      })}
    </Card>
  );
}
