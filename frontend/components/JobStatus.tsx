"use client";
import type { Job } from "@/lib/api";
import { ProgressBar } from "@/components/ui";

export default function JobStatus({ job, onCancel }: { job: Job | null; onCancel?: () => void }) {
  if (!job) return null;
  if (job.status === "queued" || job.status === "running")
    return (
      <div className="mt-2 flex items-center gap-3">
        <div className="flex-1"><ProgressBar value={job.progress} label={job.message} /></div>
        {onCancel && <button onClick={onCancel} className="rounded-lg border border-rose-500/50 px-2 py-1 text-xs text-rose-300 hover:bg-rose-500/10">Annuler</button>}
      </div>
    );
  if (job.status === "failed") return <p className="mt-2 text-sm text-rose-400">Échec : {job.error}</p>;
  if (job.status === "cancelled") return <p className="mt-2 text-sm text-amber-300">Tâche annulée.</p>;
  if (job.status === "interrupted") return <p className="mt-2 text-sm text-amber-300">Tâche interrompue (serveur redémarré).</p>;
  return null;
}
