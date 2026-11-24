"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import ProjectCards from "@/components/ProjectCards";
import SystemStatusCard from "@/components/SystemStatusCard";
import { Badge, Card } from "@/components/ui";
import { api, type ExportRow, type ProjectCard } from "@/lib/api";

export default function Home() {
  const [projects, setProjects] = useState<ProjectCard[]>([]);
  const [exports, setExports] = useState<ExportRow[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.listProjects().then(setProjects).catch((e) => setErr(e.message));
    api.listExports({ limit: 5 }).then(setExports).catch(() => {});
  }, []);

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <header className="mb-6 flex flex-wrap items-center gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-bold">Tableau de bord</h1>
          <p className="text-sm text-muted">PROF IA · montage vidéo assisté par IA locale</p>
        </div>
        <Link href="/new" className="rounded-lg bg-accent px-4 py-2 font-medium text-white hover:brightness-110">+ Nouveau projet</Link>
        <Link href="/new?import=1" className="rounded-lg border border-border px-4 py-2 hover:border-accent">Importer une vidéo</Link>
      </header>
      {err && <p className="mb-4 rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200">{err}</p>}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px] [&>*]:min-w-0">
        <section>
          <h2 className="mb-3 text-lg font-semibold">Projets récents</h2>
          <ProjectCards projects={projects.slice(0, 9)} empty={
            <Card><p className="text-sm text-muted">Aucun projet pour l&apos;instant. Commencez par <Link href="/new" className="text-violet-300 underline">créer un projet</Link>.</p></Card>} />
          {projects.length > 9 && <Link href="/editor" className="mt-3 inline-block text-sm text-violet-300 hover:underline">Voir tous les projets ({projects.length}) →</Link>}
        </section>
        <aside className="space-y-6">
          <SystemStatusCard />
          <Card title="Derniers exports">
            {exports.length === 0 ? <p className="text-sm text-muted">Aucun export.</p> : (
              <ul className="space-y-2 text-sm" data-testid="recent-exports">
                {exports.map((e) => (
                  <li key={e.id} className="flex items-center gap-2">
                    <Badge tone={e.ok ? "good" : "warn"}>{e.platform}</Badge>
                    <a href={api.exportFileUrl(e.id)} className="flex-1 truncate text-violet-300 hover:underline" title={e.path}>{e.project_name}</a>
                    <span className="text-xs text-muted">{new Date(e.created_at).toLocaleDateString("fr-FR")}</span>
                  </li>
                ))}
              </ul>
            )}
            <Link href="/exports" className="mt-3 block text-sm text-violet-300 hover:underline">Toutes les exportations →</Link>
          </Card>
        </aside>
      </div>
    </main>
  );
}
