/** The small ring mark used in the top bar. Pure SVG, no external assets. */
export function BrandMark({ className = "brand-mark" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="16" cy="16" r="14" fill="none" stroke="#3de1ff" strokeWidth="1.2" opacity="0.5" />
      <circle cx="16" cy="16" r="9.5" fill="none" stroke="#3de1ff" strokeWidth="2" strokeDasharray="4 3.2" />
      <circle cx="16" cy="16" r="3.6" fill="#d9f4fc" />
    </svg>
  );
}
