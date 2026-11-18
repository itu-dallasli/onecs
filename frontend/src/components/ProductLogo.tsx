export default function ProductLogo({
  className = "",
  decorative = false,
}: {
  className?: string;
  decorative?: boolean;
}) {
  return (
    <svg
      className={className}
      viewBox="200 105 400 160"
      width={400}
      height={160}
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : "onecs"}
      aria-hidden={decorative || undefined}
      focusable="false"
    >
      <image href="/onecs-logo.png" width={800} height={320} />
    </svg>
  );
}
