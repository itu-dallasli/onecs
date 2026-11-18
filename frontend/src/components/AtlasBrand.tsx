export default function AtlasBrand({
  className = "",
  compact = false,
}: {
  className?: string;
  compact?: boolean;
}) {
  return (
    <span
      className={`atlas-brand ${compact ? "atlas-brand-compact" : ""} ${className}`}
    >
      <img
        className="atlas-brand-symbol"
        src="/atlas-logo.svg"
        alt=""
        aria-hidden="true"
      />
      <span className="atlas-brand-copy">
        <strong>ATLAS</strong>
        {!compact && (
          <span>
            Siber Güvenlik
            <br className="atlas-brand-subtitle-break" /> Yönetim Uygulaması
          </span>
        )}
      </span>
    </span>
  );
}
