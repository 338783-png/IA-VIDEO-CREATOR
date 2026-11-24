"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import JobStatus from "@/components/JobStatus";
import { Badge, Card } from "@/components/ui";
import { CAMERAS, EMOTIONS, charApi, type Character, type ScenarioData, type ScenarioOut, type ScLine } from "@/lib/api";
import { useJob } from "@/lib/useJob";

const field = "w-full rounded border border-border bg-surface-2 px-2 py-1 text-sm";
const estimate = (t: string) => (t.match(/\w+/g)?.length ?? 0) / 2.6;

export default function ScenarioEditor({ projectId }: { projectId: number }) {
  const [chars, setChars] = useState<Character[]>([]);
  const [sc, setSc] = useState<ScenarioOut | null>(null);
  const [data, setData] = useState<ScenarioData | null>(null);
  const [dirty, setDirty] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [gen, setGen] = useState({ topic: "", ids: [] as number[], seconds: 45, tone: "pédagogique et chaleureux", instructions: "" });

  const load = useCallback(() => charApi.scenario(projectId).then((s) => { setSc(s); setData(s.data); setDirty(false); }).catch(() => setSc(null)), [projectId]);
  useEffect(() => { load(); charApi.list().then(setChars).catch(() => {}); }, [load]);
  const job = useJob((j) => { if (j.status === "done") load(); });

  const upd = (fn: (d: ScenarioData) => void) => setData((d) => { if (!d) return d; const c = structuredClone(d); fn(c); setDirty(true); return c; });
  const newLine = (): ScLine => ({ character_id: chars[0]?.id ?? 0, text: "", emotion: "neutre", intention: "", pause_after: 0.3 });
  const total = data ? data.scenes.reduce((a, s) => a + s.lines.reduce((b, l) => b + estimate(l.text) + (l.pause_after || 0), 0), 0) : 0;
  const name = (id: number) => chars.find((c) => c.id === id)?.name ?? `#${id}`;

  async function run(fn: () => Promise<unknown>) { setErr(null); try { await fn(); } catch (e) { setErr((e as Error).message); } }

  return (
    <Card title={<span className="flex flex-wrap items-center gap-2">Scénario dialogué (dessin animé)
      {sc && <Badge tone={sc.status === "validated" ? "good" : "warn"}>v{sc.version} · {sc.status === "validated" ? "validé" : "brouillon"}</Badge>}
      {data && <Badge>≈ {total.toFixed(0)} s</Badge>}</span>}>
      {err && <p className="mb-2 text-sm text-rose-400">{err}</p>}
      {chars.length === 0 ? (
        <p className="text-sm text-muted">Créez d&apos;abord des personnages dans la page <Link href="/characters" className="text-violet-300 underline">Personnages</Link>.</p>
      ) : (
        <details className="mb-3 rounded-lg border border-border bg-surface-2/50 p-3" open={!sc}>
          <summary className="cursor-pointer text-sm font-medium">Générer un scénario avec l&apos;IA locale</summary>
          <div className="mt-2 grid gap-2 text-xs text-muted sm:grid-cols-2">
            <label className="sm:col-span-2">Sujet<input value={gen.topic} onChange={(e) => setGen({ ...gen, topic: e.target.value })} placeholder="Ex. : comment fonctionne l'intelligence artificielle" className={field} /></label>
            <fieldset className="sm:col-span-2"><legend>Personnages</legend>
              <div className="mt-1 flex flex-wrap gap-2">{chars.map((c) => (
                <label key={c.id} className="flex items-center gap-1 rounded border border-border px-2 py-1 text-sm text-foreground">
                  <input type="checkbox" className="accent-violet-500" checked={gen.ids.includes(c.id)}
                    onChange={(e) => setGen({ ...gen, ids: e.target.checked ? [...gen.ids, c.id] : gen.ids.filter((x) => x !== c.id) })} />{c.name}</label>))}</div></fieldset>
            <label>Durée visée (s)<input type="number" min={10} max={300} value={gen.seconds} onChange={(e) => setGen({ ...gen, seconds: +e.target.value })} className={field} /></label>
            <label>Ton<input value={gen.tone} onChange={(e) => setGen({ ...gen, tone: e.target.value })} className={field} /></label>
            <label className="sm:col-span-2">Consignes (facultatif)<input value={gen.instructions} onChange={(e) => setGen({ ...gen, instructions: e.target.value })} className={field} /></label>
          </div>
          <button disabled={gen.topic.trim().length < 3 || !gen.ids.length || job.running}
            onClick={() => run(async () => job.start(await charApi.generate(projectId, { topic: gen.topic, character_ids: gen.ids, target_seconds: gen.seconds, tone: gen.tone, instructions: gen.instructions })))}
            className="mt-2 rounded-lg bg-accent px-3 py-1.5 text-sm text-white disabled:opacity-40">Générer (1 à 5 min)</button>
          {!sc && <button onClick={() => { setData({ title: "Mon dessin animé", topic: "", scenes: [{ title: "Scène 1", setting: "", camera: "plan_moyen", lines: [newLine()] }] }); setDirty(true); }}
            className="ml-2 mt-2 rounded-lg border border-border px-3 py-1.5 text-sm">Écrire à la main</button>}
          <JobStatus job={job.job} onCancel={job.cancel} />
        </details>
      )}

      {data && (
        <div className="space-y-3" data-testid="scenario-editor">
          <input value={data.title} onChange={(e) => upd((d) => { d.title = e.target.value; })} className={`${field} text-base font-medium`} aria-label="Titre" />
          {data.scenes.map((s, si) => (
            <div key={si} className="rounded-lg border border-border p-2">
              <div className="mb-2 grid gap-2 sm:grid-cols-[1fr_1fr_160px_auto]">
                <input value={s.title} onChange={(e) => upd((d) => { d.scenes[si].title = e.target.value; })} placeholder="Titre de scène" className={field} />
                <input value={s.setting} onChange={(e) => upd((d) => { d.scenes[si].setting = e.target.value; })} placeholder="Décor" className={field} />
                <select value={s.camera} onChange={(e) => upd((d) => { d.scenes[si].camera = e.target.value; })} className={field}>
                  {Object.entries(CAMERAS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
                <button onClick={() => upd((d) => { d.scenes.splice(si, 1); })} disabled={data.scenes.length === 1} className="rounded border border-rose-500/40 px-2 text-rose-300 disabled:opacity-30" aria-label="Supprimer la scène">✕</button>
              </div>
              {s.lines.map((l, li) => (
                <div key={li} className="mb-1 grid gap-1 sm:grid-cols-[130px_1fr_120px_70px_auto]">
                  <select value={l.character_id} onChange={(e) => upd((d) => { d.scenes[si].lines[li].character_id = +e.target.value; })} className={field}>
                    {chars.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                    {!chars.some((c) => c.id === l.character_id) && <option value={l.character_id}>{name(l.character_id)} (supprimé)</option>}</select>
                  <input value={l.text} onChange={(e) => upd((d) => { d.scenes[si].lines[li].text = e.target.value; })} placeholder="Réplique" title={l.intention} className={field} />
                  <select value={l.emotion} onChange={(e) => upd((d) => { d.scenes[si].lines[li].emotion = e.target.value; })} className={field}>
                    {EMOTIONS.map((x) => <option key={x}>{x}</option>)}</select>
                  <input type="number" step="0.1" min="0" max="3" value={l.pause_after} title="Pause après (s)" onChange={(e) => upd((d) => { d.scenes[si].lines[li].pause_after = +e.target.value; })} className={field} />
                  <button onClick={() => upd((d) => { d.scenes[si].lines.splice(li, 1); })} className="rounded border border-border px-2 text-muted" aria-label="Supprimer la réplique">✕</button>
                </div>
              ))}
              <button onClick={() => upd((d) => { d.scenes[si].lines.push(newLine()); })} className="mt-1 text-xs text-violet-300">+ Réplique</button>
            </div>
          ))}
          <div className="flex flex-wrap gap-2">
            <button onClick={() => upd((d) => { d.scenes.push({ title: `Scène ${d.scenes.length + 1}`, setting: "", camera: "plan_moyen", lines: [newLine()] }); })}
              className="rounded-lg border border-border px-3 py-1.5 text-sm">+ Scène</button>
            <button disabled={!dirty} onClick={() => run(async () => { const s = await charApi.save(projectId, { ...data, base_version: sc?.version }); setSc(s); setData(s.data); setDirty(false); })}
              className="rounded-lg bg-accent px-3 py-1.5 text-sm text-white disabled:opacity-40">Enregistrer (nouvelle version)</button>
            {sc && !dirty && sc.status !== "validated" && (
              <button onClick={() => run(async () => setSc(await charApi.validate(projectId, sc.version)))} className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm text-white">Valider le scénario</button>)}
          </div>
          <p className="text-[11px] text-muted">L&apos;animation des personnages (bouche, expressions, gestes) à partir de ce scénario arrive dans les étapes suivantes du module.</p>
        </div>
      )}
    </Card>
  );
}
