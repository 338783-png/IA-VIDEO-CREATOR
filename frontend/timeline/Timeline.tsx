"use client";
import type { SbScene } from "@/lib/api";

const COLORS = ["#7c5cff", "#2dd4bf", "#f59e0b", "#ec4899", "#38bdf8", "#84cc16"];

/** Timeline proportionnelle : une barre par scène, chevauchements des transitions visibles. */
export default function Timeline({ scenes, total, selected, onSelect }: { scenes: SbScene[]; total: number; selected?: string | null; onSelect?: (id: string) => void }) {
  if (!scenes.length || total <= 0) return null;
  const mediaColor = new Map<number, string>();
  scenes.forEach((s) => { if (!mediaColor.has(s.media_id)) mediaColor.set(s.media_id, COLORS[mediaColor.size % COLORS.length]); });
  return (
    <div data-testid="timeline">
      <div className="relative h-12 overflow-hidden rounded-lg bg-surface-2">
        {scenes.map((s) => {
          const left = ((s.timeline_start ?? 0) / total) * 100;
          const width = (s.duration / total) * 100;
          return (
            <button key={s.id} onClick={() => onSelect?.(s.id)} title={`${s.position}. ${s.source} (${s.duration.toFixed(1)} s)`}
              className={`absolute top-1 bottom-1 overflow-hidden rounded border px-1 text-left text-[10px] leading-tight ${selected === s.id ? "border-white" : "border-black/30"}`}
              style={{ left: `${left}%`, width: `${width}%`, background: mediaColor.get(s.media_id), opacity: 0.85 }}>
              {s.position}{s.transition !== "cut" ? " ⟿" : ""}
            </button>
          );
        })}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-muted"><span>0 s</span><span>{total.toFixed(1)} s</span></div>
    </div>
  );
}
