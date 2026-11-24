"use client";

export function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "good" | "warn" | "bad" | "accent" }) {
  const cls = {
    neutral: "bg-surface-2 text-muted border-border",
    good: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
    warn: "bg-amber-500/10 text-amber-300 border-amber-500/30",
    bad: "bg-rose-500/10 text-rose-300 border-rose-500/30",
    accent: "bg-accent/15 text-violet-200 border-accent/40",
  }[tone];
  return <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs ${cls}`}>{children}</span>;
}

export function ConfidenceBadge({ value }: { value: string }) {
  const tone = value === "élevée" ? "good" : value === "moyenne" ? "warn" : "bad";
  return <Badge tone={tone}>confiance {value}</Badge>;
}

export function Card({ title, children, className = "" }: { title?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-border bg-surface p-4 ${className}`}>
      {title && <h2 className="mb-3 font-semibold">{title}</h2>}
      {children}
    </section>
  );
}

export function ProgressBar({ value, label }: { value: number; label?: string }) {
  return (
    <div>
      <div className="h-2 overflow-hidden rounded-full bg-surface-2">
        <div className="h-full bg-accent transition-all" style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      {label && <p className="mt-1 text-xs text-muted">{label} — {Math.round(value * 100)} %</p>}
    </div>
  );
}

export function Swatch({ hex, share }: { hex: string; share?: number }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="h-6 w-6 rounded border border-border" style={{ background: hex }} />
      <code>{hex}</code>
      {share !== undefined && <span className="text-muted">{Math.round(share * 100)} %</span>}
    </div>
  );
}
