"use client";
import { useEffect, useState } from "react";
import { api, type SystemStatus } from "@/lib/api";

function Dot({ ok, warn }: { ok: boolean; warn?: boolean }) {
  return <span className={`inline-block h-2.5 w-2.5 rounded-full ${ok ? "bg-emerald-400" : warn ? "bg-amber-400" : "bg-rose-500"}`} />;
}

export default function SystemStatusCard() {
  const [s, setS] = useState<SystemStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.systemStatus().then(setS).catch((e) => setErr(e.message));
  }, []);

  if (err) return <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-200">{err}</div>;
  if (!s) return <div className="rounded-xl border border-border bg-surface p-4 text-sm text-muted">Vérification du système…</div>;

  const rows = [
    { label: "Backend + base SQLite", ok: s.database.ok, info: "connecté" },
    { label: "FFmpeg", ok: s.ffmpeg.available, info: s.ffmpeg.ffmpeg?.split(" ")[2] ?? "introuvable" },
    {
      label: "Ollama (IA locale)",
      ok: s.ollama.model_ready,
      warn: s.ollama.available,
      info: !s.ollama.available ? "non installé / arrêté — mode sans IA" : s.ollama.model_ready ? s.ollama.configured_model : `modèle ${s.ollama.configured_model} absent`,
    },
  ];
  return (
    <div className="rounded-xl border border-border bg-surface p-4" data-testid="system-status">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">État du système</h3>
      <ul className="space-y-2 text-sm">
        {rows.map((r) => (
          <li key={r.label} className="flex items-center gap-2">
            <Dot ok={r.ok} warn={r.warn} />
            <span className="flex-1">{r.label}</span>
            <span className="text-muted">{r.info}</span>
          </li>
        ))}
        <li className="flex items-center gap-2 text-muted">
          <span className="h-2.5 w-2.5" />
          <span className="flex-1">Espace disque libre</span>
          <span>{s.disk_free_gb} Go</span>
        </li>
      </ul>
    </div>
  );
}
