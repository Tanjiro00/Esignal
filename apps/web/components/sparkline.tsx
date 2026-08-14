import clsx from "clsx";

export function Sparkline({
  values,
  className,
  negative = false,
}: {
  values: number[];
  className?: string;
  negative?: boolean;
}) {
  if (values.length < 2) {
    return <span className="text-[10px] text-[var(--faint)]">No history</span>;
  }
  const width = 92;
  const height = 34;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 1);
  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / range) * (height - 4) - 2;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg
      aria-label={`${negative ? "Declining" : "Rising"} trend`}
      className={clsx("overflow-visible", className)}
      height={height}
      role="img"
      viewBox={`0 0 ${width} ${height}`}
      width={width}
    >
      <line
        stroke="var(--line)"
        strokeDasharray="2 3"
        x1="0"
        x2={width}
        y1={height - 2}
        y2={height - 2}
      />
      <polyline
        fill="none"
        points={points}
        stroke={negative ? "var(--coral)" : "var(--lime-strong)"}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.6"
      />
    </svg>
  );
}
