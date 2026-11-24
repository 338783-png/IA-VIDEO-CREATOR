"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { editApi, type Job } from "@/lib/api";

/** Suit une tâche de fond jusqu'à sa fin (progression, annulation). */
export function useJob(onFinish: (job: Job) => void) {
  const [job, setJob] = useState<Job | null>(null);
  const cb = useRef(onFinish);
  cb.current = onFinish;
  const running = job && (job.status === "queued" || job.status === "running");

  useEffect(() => {
    if (!running || !job) return;
    const t = setInterval(async () => {
      try {
        const j = await editApi.job(job.id);
        setJob(j);
        if (j.status !== "queued" && j.status !== "running") cb.current(j);
      } catch {
        /* réessaie au prochain tick */
      }
    }, 700);
    return () => clearInterval(t);
  }, [running, job]);

  const start = useCallback((j: Job) => {
    setJob(j);
    if (j.status !== "queued" && j.status !== "running") cb.current(j);
  }, []);
  const cancel = useCallback(async () => {
    if (job) setJob(await editApi.cancel(job.id));
  }, [job]);
  return { job, running: Boolean(running), start, cancel };
}
