import ProductLogo from "./ProductLogo";
import "../styles/onecs-brand.css";

export default function OnecsBrand({
  className = "",
  compact = false,
}: {
  className?: string;
  compact?: boolean;
}) {
  return (
    <span
      className={`onecs-brand ${compact ? "onecs-brand-compact" : ""} ${className}`}
    >
      <ProductLogo className="onecs-brand-artwork" />
      {!compact && (
        <span className="onecs-brand-subtitle">
          Siber Güvenlik Yönetim Uygulaması
        </span>
      )}
    </span>
  );
}
