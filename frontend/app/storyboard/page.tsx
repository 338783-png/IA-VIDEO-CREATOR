"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge, Card } from "@/components/ui";
import { api, type StoryboardRow } from "@/lib/api";

export default function Storyboards() {
  const [rows, setRows] = useState<StoryboardRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api.listStoryboards().then(setRows).catch((e) => setErr(e.message)); }, []);
  return (
    <main className="mx-auto max-w-6xl px-4 py-6">
      <h1 className="mb-1 text-2xl font-bold">Storyboards</h1>
      <p className="mb-6 text-sm text-muted">Dernière version du storyboard de chaque projet. Ouvrez-en un pour modifier les scènes, prévisualiser et valider.</p>
      {err && <p className="text-sm text-rose-400">{err}</p>}
      {rows && rows.length === 0 && <Card><p className="text-sm text-muted">Aucun storyboard. Générez-en un depuis l&apos;<Link href="/editor" className="text-violet-300 underline">éditeur</Link> d&apos;un projet.</p></Card>}
      {rows && rows.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-border">
          <table className="w-full text-left text-sm" data-testid="storyboard-table">
            <thead className="bg-surface-2 text-xs text-muted"><tr>
              <th className="px-3 py-2">Projet</th><th>Version</th><th>Scènes</th><th>Durée</th><th>Format</th><th>Style</th><th>Aperçu</th><th>Statut</th><th></th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.project_id} className="border-t border-border bg-surface">
                  <td className="px-3 py-2 font-medium">{r.project_name}</td><td>v{r.version}</td><td>{r.scenes}</td>
                  <td>{r.duration?.toFixed(1)} s</td><td>{r.platform}</td><td className="text-muted">{r.style}</td>
                  <td>{r.has_preview ? <Badge tone="good">prêt</Badge> : <Badge>à générer</Badge>}</td>
                  <td><Badge tone={r.status === "validated" ? "good" : "warn"}>{r.status === "validated" ? "validé" : "brouillon"}</Badge></td>
                  <td className="pr-3 text-right"><Link href={`/projects/${r.project_id}`} className="text-violet-300 hover:underline">Ouvrir →</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
