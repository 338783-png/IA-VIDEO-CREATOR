"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import ProjectCards from "@/components/ProjectCards";
import { Card } from "@/components/ui";
import { api, type ProjectCard } from "@/lib/api";

export default function Editor() {
  const [projects, setProjects] = useState<ProjectCard[]>([]);
  const [type, setType] = useState<"" | "2d" | "3d">("");
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api.listProjects().then(setProjects).catch((e) => setErr(e.message)); }, []);
  const shown = projects.filter((p) => !type || p.project_type === type);
  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div className="flex-1"><h1 className="text-2xl font-bold">Éditeur</h1>
          <p className="text-sm text-muted">Choisissez un projet à monter : médias, analyse, storyboard, voix off, aperçu, validation, export.</p></div>
        {(["", "2d", "3d"] as const).map((t) => (
          <button key={t} onClick={() => setType(t)} className={`rounded-lg px-3 py-1.5 text-sm ${type === t ? "bg-accent text-white" : "bg-surface-2 text-muted"}`}>{t ? t.toUpperCase() : "Tous"}</button>
        ))}
        <Link href="/new" className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white">+ Nouveau projet</Link>
      </div>
      {err && <p className="text-sm text-rose-400">{err}</p>}
      <ProjectCards projects={shown} empty={<Card><p className="text-sm text-muted">Aucun projet.</p></Card>} />
    </main>
  );
}
