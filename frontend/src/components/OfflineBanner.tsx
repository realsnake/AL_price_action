import type { WorkspaceMode } from "../types";

interface OfflineBannerProps {
  mode: WorkspaceMode;
  title: string;
  detail: string;
  lastSyncedAt?: string | null;
}

function toneClasses(mode: WorkspaceMode): string {
  switch (mode) {
    case "offline":
      return "border-amber-300/25 bg-amber-300/10 text-amber-50";
    case "api_down":
      return "border-rose-400/25 bg-rose-400/10 text-rose-50";
    case "degraded":
      return "border-cyan-300/25 bg-cyan-300/10 text-cyan-50";
    case "standby":
      return "border-slate-300/20 bg-white/5 text-slate-100";
    default:
      return "border-white/10 bg-white/5 text-slate-100";
  }
}

export default function OfflineBanner({
  mode,
  title,
  detail,
  lastSyncedAt,
}: OfflineBannerProps) {
  return (
    <div
      className={`rounded-2xl border px-4 py-3 shadow-[0_18px_60px_-30px_rgba(15,23,42,0.95)] ${toneClasses(mode)}`}
    >
      <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-sm font-semibold">{title}</p>
          <p className="mt-1 text-sm opacity-80">{detail}</p>
        </div>
        {lastSyncedAt && (
          <p className="text-xs uppercase tracking-[0.24em] opacity-60">
            Last good sync {lastSyncedAt}
          </p>
        )}
      </div>
    </div>
  );
}
