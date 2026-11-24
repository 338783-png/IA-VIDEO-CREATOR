"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import UploadZone from "@/components/UploadZone";
import { Badge, Card } from "@/components/ui";
import { api, type Media, type ProjectCard } from "@/lib/api";

const KINDS = [["", "Tous"], ["video", "Vidéos"], ["audio", "Audio"], ["image", "Images"], ["script", "Scripts"], ["reference", "Références"]] as const;

export default function Library() {
  const [media, setMedia] = useState<Media[]>([]);
  const [projects, setProjects] = useState<ProjectCard[]>([]);
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<Media | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = () => api.listMedia().then(setMedia).catch((e) => setErr(e.message));
  useEffect(() => { load(); api.listProjects().then(setProjects).catch(() => {}); }, []);
  const pname = useMemo(() => new Map(projects.map((p) => [p.id, p.name])), [projects]);
  const shown = media.filter((m) => (!kind || m.kind === kind) && m.original_name.toLowerCase().includes(q.toLowerCase()));

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <h1 className="mb-1 text-2xl font-bold">Bibliothèque de médias</h1>
      <p className="mb-6 text-sm text-muted">Tous vos fichiers importés. Les originaux sont conservés en lecture seule et ne sont jamais modifiés.</p>
      {err && <p className="mb-4 text-sm text-rose-400">{err}</p>}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {KINDS.map(([k, l]) => (
          <button key={k} onClick={() => setKind(k)} className={`rounded-lg px-3 py-1.5 text-sm ${kind === k ? "bg-accent text-white" : "bg-surface-2 text-muted hover:text-foreground"}`}>{l}</button>
        ))}
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher…" className="ml-auto rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-sm" />
      </div>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_300px] [&>*]:min-w-0">
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4" data-testid="library-grid">
          {shown.length === 0 && <li className="text-sm text-muted">Aucun média.</li>}
          {shown.map((m) => (
            <li key={m.id}>
              <button onClick={() => setOpen(m)} className="block w-full overflow-hidden rounded-xl border border-border bg-surface text-left hover:border-accent">
                <div className="relative grid aspect-video place-items-center overflow-hidden bg-black">
                  {m.category === "video" || m.category === "image" ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={api.thumbnailUrl(m.id)} alt="" className="absolute inset-0 h-full w-full object-cover" />
                  ) : <span className="text-3xl text-muted">{m.category === "audio" ? "♪" : "¶"}</span>}
                </div>
                <div className="p-2 text-xs">
                  <div className="truncate text-sm font-medium">{m.original_name}</div>
                  <div className="mt-1 flex flex-wrap gap-1"><Badge>{m.kind}</Badge>
                    {m.probe.duration ? <Badge>{m.probe.duration.toFixed(1)} s</Badge> : null}
                    <Badge>{(m.size_bytes / 1e6).toFixed(1)} Mo</Badge></div>
                  <div className="mt-1 truncate text-muted">{m.project_id ? pname.get(m.project_id) ?? `projet ${m.project_id}` : "sans projet"}</div>
                </div>
              </button>
            </li>
          ))}
        </ul>
        <aside className="space-y-4">
          <Card title="Aperçu">
            {!open ? <p className="text-sm text-muted">Cliquez sur un média.</p> : (
              <div className="space-y-2 text-sm">
                {open.category === "video" && <video key={open.id} src={api.mediaUrl(open.id)} controls className="w-full rounded bg-black" />}
                {open.category === "image" && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={api.mediaUrl(open.id)} alt={open.original_name} className="w-full rounded" />
                )}
                {open.category === "audio" && <audio key={open.id} src={api.mediaUrl(open.id)} controls className="w-full" />}
                {open.category === "script" && <iframe title="script" src={api.mediaUrl(open.id)} className="h-48 w-full rounded bg-white" />}
                <div className="font-medium">{open.original_name}</div>
                <div className="text-xs text-muted">{open.probe.video ? `${open.probe.video.width}×${open.probe.video.height} · ` : ""}importé le {new Date(open.created_at).toLocaleString("fr-FR")}</div>
                {open.project_id && <Link href={`/projects/${open.project_id}`} className="text-violet-300 hover:underline">Ouvrir le projet →</Link>}
              </div>
            )}
          </Card>
          <Card title="Importer une référence"><UploadZone kind="reference" onUploaded={load} /></Card>
          <p className="text-xs text-muted">Les vidéos, sons, images et scripts s&apos;importent dans un projet (page Éditeur).</p>
        </aside>
      </div>
    </main>
  );
}
