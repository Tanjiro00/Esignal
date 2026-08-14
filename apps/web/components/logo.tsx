export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height={size}
      viewBox="0 0 32 32"
      width={size}
    >
      <path
        d="M3 17h4l2.2-9 3.4 17 3.5-21 3.1 25 3.4-17 2.4 8h4"
        stroke="var(--lime-strong)"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}
