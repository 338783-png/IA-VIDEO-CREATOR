"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge, Card } from "@/components/ui";
import { api, API_URL, type ExportRow } from "@/lib/api";

const PLATFORMS = [["", "Toutes"], ["tiktok", "TikTok"], ["reels", "Reels"], ["shorts", "Shorts"], ["youtube", "YouTube"]] as const;

export default function Exports() {
  const [rows, setRows] = useState<ExportRow[]>([]);
  const [platform, setPlatform] = useState("");
  const [open, setOpen] = useState<ExportRow | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api.listExports({ platform: platform || undefined, limit: 200 }).then(setRows).catch((e) => setErr(e.message)); }, [platform]);

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <h1 className="mb-1 text-2xl font-bold">Exportations</h1>
      <p className="mb-6 text-sm text-muted">Vidéos MP4 (H.264 + AAC) vérifiées automatiquement. Rien n&apos;est publié sur les réseaux : vous gardez la main.</p>
      <div className="mb-4 flex flex-wrap gap-2">
        {PLATFORMS.map(([k, l]) => <button key={k} onClick={() => setPlatform(k)} className={`rounded-lg px-3 py-1.5 text-sm ${platform === k ? "bg-accent text-white" : "bg-surface-2 text-muted"}`}>{l}</button>)}
      </div>
      {err && <p className="text-sm text-rose-400">{err}</p>}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px] [&>*]:min-w-0">
        <ul className="space-y-2" data-testid="exports-list">
          {rows.length === 0 && <Card><p className="text-sm text-muted">Aucun export.</p></Card>}
          {rows.map((e) => (
            <li key={e.id}>
              <button onClick={() => setOpen(e)} className={`flex w-full flex-wrap items-center gap-2 rounded-xl border bg-surface p-3 text-left text-sm ${open?.id === e.id ? "border-accent" : "border-border hover:border-accent"}`}>
                <Badge tone="accent">{e.platform}</Badge>
                <span className="flex-1 truncate font-medium">{e.project_name}</span>
                <Badge tone={e.ok ? "good" : "bad"}>{e.ok ? "vérifié" : "à vérifier"}</Badge>
                {!e.file_exists && <Badge tone="bad">fichier absent</Badge>}
                <span className="text-xs text-muted">{e.settings.quality} · {e.settings.fps} i/s · {e.size_bytes ? `${(e.size_bytes / 1e6).toFixed(1)} Mo` : "—"} · {new Date(e.created_at).toLocaleString("fr-FR")}</span>
              </button>
            </li>
          ))}
        </ul>
        <Card title="Lecture">
          {!open ? <p className="text-sm text-muted">Sélectionnez un export.</p> : (
            <div className="space-y-2 text-sm">
              {open.file_exists && <video key={open.id} src={api.exportFileUrl(open.id)} controls className="max-h-[60vh] w-full rounded bg-black" />}
              <div className="break-all text-xs text-muted">{open.path}</div>
              <div className="flex flex-wrap gap-1">{Object.entries(open.verification.checks ?? {}).map(([k, v]) => <Badge key={k} tone={v ? "good" : "bad"}>{k}</Badge>)}</div>
              <div className="flex flex-wrap gap-3">
                <a href={api.exportFileUrl(open.id)} className="text-violet-300 hover:underline">⬇ Télécharger le MP4</a>
                {open.subtitle_files.map((f) => <a key={f} href={`${API_URL}/api/projects/${open.project_id}/subtitles?format=${f.endsWith(".srt") ? "srt" : "vtt"}&version=${open.storyboard_version}`} className="text-violet-300 hover:underline">⬇ {f.split(".").pop()?.toUpperCase()}</a>)}
                <Link href={`/projects/${open.project_id}`} className="text-violet-300 hover:underline">Ouvrir le projet →</Link>
              </div>
            </div>
          )}
        </Card>
      </div>
    </main>
  );
}
