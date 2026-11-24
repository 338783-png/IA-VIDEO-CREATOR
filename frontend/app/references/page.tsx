"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import UploadZone from "@/components/UploadZone";
import { Badge, Card, ProgressBar } from "@/components/ui";
import { api, refApi, styleApi, type ReferenceItem, type StyleListItem } from "@/lib/api";

const RUNNING = ["queued", "running"];

export default function ReferencesPage() {
  const router = useRouter();
  const [refs, setRefs] = useState<ReferenceItem[]>([]);
  const [styles, setStyles] = useState<StyleListItem[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [r, s] = await Promise.all([refApi.list(), styleApi.list()]);
      setRefs(r);
      setStyles(s);
    } catch (e) {
      setErr((e as Error).message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // rafraîchit tant qu'une analyse tourne
  const busy = refs.some((r) => r.last_job && RUNNING.includes(r.last_job.status));
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(load, 800);
    return () => clearInterval(t);
  }, [busy, load]);

  async function run(fn: () => Promise<unknown>) {
    setErr(null);
    try { await fn(); } catch (e) { setErr((e as Error).message); }
    load();
  }

  async function createStyle() {
    setErr(null);
    try {
      const s = await styleApi.create(name.trim() || "Mon style", selected);
      router.push(`/styles/${s.id}`);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  const toggle = (id: number) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  return (
    <main className="mx-auto max-w-6xl px-4 py-6">
      
      <h1 className="mb-1 text-2xl font-bold">Références &amp; styles</h1>
      <p className="mb-6 text-sm text-muted">
        Importez des vidéos dont vous aimez le montage. L&apos;IA en mesure le rythme, les transitions, les zooms, les couleurs,
        les sous-titres et la synchronisation audio — sans jamais copier leur contenu.
      </p>
      {err && <p className="mb-4 rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200">{err}</p>}

      <div className="grid gap-6 lg:grid-cols-3 [&>*]:min-w-0">
        <div className="space-y-6 lg:col-span-2">
          <Card title="Vidéos de référence">
            <UploadZone kind="reference" onUploaded={load} />
            <ul className="mt-4 space-y-3" data-testid="reference-list">
              {refs.length === 0 && <li className="text-sm text-muted">Aucune référence importée.</li>}
              {refs.map((r) => {
                const j = r.last_job;
                const running = j && RUNNING.includes(j.status);
                return (
                  <li key={r.id} className="flex gap-3 rounded-lg border border-border bg-surface-2 p-3">
                    <input type="checkbox" className="mt-1 accent-violet-500" disabled={!r.analyzed} checked={selected.includes(r.id)}
                      onChange={() => toggle(r.id)} aria-label={`Sélectionner ${r.original_name}`} />
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={api.thumbnailUrl(r.id)} alt="" className="h-20 w-14 shrink-0 rounded bg-black object-cover" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">{r.original_name}</div>
                      <div className="text-xs text-muted">
                        {r.probe.duration?.toFixed(1)} s · {r.probe.video?.width}×{r.probe.video?.height} · {(r.size_bytes / 1e6).toFixed(1)} Mo
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {r.summary ? (
                          <>
                            <Badge tone="good">analysée</Badge>
                            <Badge>{r.summary.shots} plans</Badge>
                            <Badge>rythme {r.summary.pace}</Badge>
                            <Badge>{r.summary.aspect}</Badge>
                            {r.summary.captions && <Badge tone="accent">sous-titres</Badge>}
                            {r.summary.bpm && <Badge>{Math.round(r.summary.bpm)} BPM</Badge>}
                          </>
                        ) : !running && <Badge tone="warn">non analysée</Badge>}
                        {j?.status === "failed" && <Badge tone="bad">échec : {j.error}</Badge>}
                        {j?.status === "cancelled" && <Badge tone="warn">analyse annulée</Badge>}
                        {j?.status === "interrupted" && <Badge tone="warn">analyse interrompue</Badge>}
                      </div>
                      {running && <div className="mt-2"><ProgressBar value={j.progress} label={j.message} /></div>}
                    </div>
                    <div className="flex shrink-0 flex-col gap-2 text-sm">
                      {running ? (
                        <button onClick={() => run(() => refApi.cancelJob(j.id))} className="rounded-lg border border-rose-500/50 px-3 py-1 text-rose-300 hover:bg-rose-500/10">Annuler</button>
                      ) : (
                        <button onClick={() => run(() => refApi.analyze(r.id))} className="rounded-lg bg-accent px-3 py-1 font-medium hover:brightness-110">
                          {r.analyzed ? "Relancer" : "Analyser"}
                        </button>
                      )}
                      {r.analyzed && <Link href={`/references/${r.id}`} className="rounded-lg border border-border px-3 py-1 text-center hover:border-accent">Détails</Link>}
                    </div>
                  </li>
                );
              })}
            </ul>
          </Card>
        </div>

        <aside className="space-y-6">
          <Card title="Créer un style">
            <p className="mb-3 text-sm text-muted">Cochez une ou plusieurs références analysées. Les points communs deviendront les règles obligatoires.</p>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nom du style" maxLength={200}
              className="mb-2 w-full rounded-lg border border-border bg-surface-2 px-3 py-2 outline-none focus:border-accent" />
            <button disabled={!selected.length} onClick={createStyle}
              className="w-full rounded-lg bg-accent px-4 py-2 font-medium disabled:cursor-not-allowed disabled:opacity-40">
              Analyser le style ({selected.length} réf.)
            </button>
          </Card>
          <Card title="Styles">
            <ul className="space-y-2" data-testid="style-list">
              {styles.length === 0 && <li className="text-sm text-muted">Aucun style.</li>}
              {styles.map((s) => (
                <li key={s.id}>
                  <Link href={`/styles/${s.id}`} className="flex items-center gap-2 rounded-lg border border-border bg-surface-2 p-2 text-sm hover:border-accent">
                    <span className="flex-1 truncate">{s.is_official && "★ "}{s.name}</span>
                    <Badge tone={s.status === "validated" ? "good" : s.status === "rejected" ? "bad" : "warn"}>
                      {s.status === "validated" ? "validé" : s.status === "rejected" ? "rejeté" : "brouillon"}
                    </Badge>
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        </aside>
      </div>
    </main>
  );
}
