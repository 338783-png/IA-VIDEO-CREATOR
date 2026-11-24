"use client";
import Link from "next/link";
import { Badge } from "@/components/ui";
import { api, type ProjectCard } from "@/lib/api";

const FORMAT: Record<string, string> = { tiktok: "TikTok", reels: "Reels", shorts: "Shorts", youtube: "YouTube" };
const STATUS: Record<string, string> = { draft: "brouillon", storyboard: "storyboard", validated: "validé", exported: "exporté" };

export default function ProjectCards({ projects, empty }: { projects: ProjectCard[]; empty?: React.ReactNode }) {
  if (!projects.length) return <>{empty ?? <p className="text-sm text-muted">Aucun projet.</p>}</>;
  return (
    <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" data-testid="project-cards">
      {projects.map((p) => (
        <li key={p.id}>
          <Link href={`/projects/${p.id}`} className="group block overflow-hidden rounded-xl border border-border bg-surface transition hover:border-accent">
            <div className="relative grid aspect-video place-items-center overflow-hidden bg-black">
              {p.thumbnail_media_id ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={api.thumbnailUrl(p.thumbnail_media_id)} alt="" className="absolute inset-0 h-full w-full object-cover opacity-90 group-hover:opacity-100" />
              ) : <span className="text-3xl text-muted">{p.project_type === "3d" ? "◆" : "▶"}</span>}
              <span className="absolute left-2 top-2"><Badge tone="accent">{p.project_type === "3d" ? "3D" : "2D"}</Badge></span>
            </div>
            <div className="p-3">
              <div className="truncate font-medium">{p.name}</div>
              <div className="mt-1 flex flex-wrap gap-1.5 text-xs">
                <Badge>{FORMAT[p.target_format] ?? p.target_format}</Badge>
                <Badge tone={p.status === "exported" ? "good" : p.status === "validated" ? "good" : "neutral"}>{STATUS[p.status] ?? p.status}</Badge>
                <Badge>{p.media_count} média{p.media_count > 1 ? "s" : ""}</Badge>
                {p.storyboard_version && <Badge>storyboard v{p.storyboard_version}</Badge>}
                {p.exports_count > 0 && <Badge tone="good">{p.exports_count} export{p.exports_count > 1 ? "s" : ""}</Badge>}
              </div>
              <div className="mt-2 text-[11px] text-muted">Modifié le {new Date(p.updated_at).toLocaleString("fr-FR")}</div>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
