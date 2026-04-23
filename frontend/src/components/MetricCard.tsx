import type { ReactNode } from "react";

interface MetricCardProps {
  eyebrow: string;
  value: string;
  detail?: string;
  footer?: string;
  accent?: "cyan" | "emerald" | "violet" | "amber";
  aside?: ReactNode;
}

const ACCENT_STYLES: Record<NonNullable<MetricCardProps["accent"]>, string> = {
  cyan: "from-cyan-400/20 via-cyan-400/5 to-transparent",
  emerald: "from-emerald-400/20 via-emerald-400/5 to-transparent",
  violet: "from-violet-400/20 via-violet-400/5 to-transparent",
  amber: "from-amber-300/20 via-amber-300/5 to-transparent",
};

export default function MetricCard({
  eyebrow,
  value,
  detail,
  footer,
  accent = "cyan",
  aside,
}: MetricCardProps) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-[#0b1524]/90 px-4 py-4 shadow-[0_18px_60px_-24px_rgba(15,23,42,0.9)]">
      <div
        className={`pointer-events-none absolute inset-0 bg-gradient-to-br ${ACCENT_STYLES[accent]}`}
      />
      <div className="relative flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">
            {eyebrow}
          </p>
          <p className="mt-3 text-2xl font-semibold text-white">{value}</p>
          {detail && <p className="mt-2 text-sm text-slate-300">{detail}</p>}
          {footer && <p className="mt-4 text-xs text-slate-500">{footer}</p>}
        </div>
        {aside && <div className="shrink-0">{aside}</div>}
      </div>
    </div>
  );
}
