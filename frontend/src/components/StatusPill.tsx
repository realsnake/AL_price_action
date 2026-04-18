interface StatusPillProps {
  label: string;
  tone?: "green" | "amber" | "red" | "blue" | "slate";
}

const TONE_STYLES: Record<NonNullable<StatusPillProps["tone"]>, string> = {
  green: "border-emerald-400/30 bg-emerald-400/10 text-emerald-200",
  amber: "border-amber-400/30 bg-amber-400/10 text-amber-100",
  red: "border-rose-400/30 bg-rose-400/10 text-rose-100",
  blue: "border-cyan-400/30 bg-cyan-400/10 text-cyan-100",
  slate: "border-white/10 bg-white/5 text-slate-200",
};

export default function StatusPill({
  label,
  tone = "slate",
}: StatusPillProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium tracking-wide ${TONE_STYLES[tone]}`}
    >
      {label}
    </span>
  );
}
