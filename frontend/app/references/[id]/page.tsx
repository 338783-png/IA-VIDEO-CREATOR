"use client";
import Link from "next/link";
import { use, useEffect, useState } from "react";
import { Badge, Card, ConfidenceBadge, Swatch } from "@/components/ui";
import { LABELS, refApi, type Analysis } from "@/lib/api";

const pct = (x: number | null | undefined) => (x === null || x === undefined ? "—" : `${Math.round(x * 100)} %`);

export default function ReferenceDetail({ params }: { params: Promise<{ id: string }> }) {
  const id = Number(use(params).id);
  const [a, setA] = useState<Analysis | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { refApi.analysis(id).then(setA).catch((e) => setErr(e.message)); }, [id]);

  if (err) return <main className="mx-auto max-w-6xl px-4 py-6"><p className="text-rose-400">{err}</p></main>;
  if (!a) return <main className="mx-auto max-w-6xl px-4 py-6"><p className="text-muted">Chargement…</p></main>;
  const c = a.captions, au = a.audio;

  return (
    <main className="mx-auto max-w-6xl px-4 py-6">
      
      <Link href="/references" className="text-sm text-muted hover:text-foreground">← Références</Link>
      <h1 className="mb-6 mt-2 text-2xl font-bold">Analyse de la référence</h1>

      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card title="Format">
          <p className="text-2xl font-bold">{a.format.aspect}</p>
          <p className="text-sm text-muted">{a.format.width}×{a.format.height} · {a.format.fps} i/s · {a.format.duration} s</p>
        </Card>
        <Card title="Rythme">
          <p className="text-2xl font-bold capitalize">{a.rhythm.pace}</p>
          <p className="text-sm text-muted">{a.rhythm.shot_count} plans · moy. {a.rhythm.avg_shot} s · {a.rhythm.cuts_per_minute} coupes/min</p>
        </Card>
        <Card title="Transitions">
          <ul className="text-sm">{Object.entries(a.transitions.counts).map(([k, v]) => <li key={k}>{LABELS[k] ?? k} : {v}</li>)}</ul>
        </Card>
        <Card title="Mouvements">
          <ul className="text-sm">{Object.entries(a.motion.counts).map(([k, v]) => <li key={k}>{LABELS[k] ?? k} : {v}</li>)}</ul>
        </Card>
      </div>

      <Card title="Plans détectés" className="mb-6">
        <div className="flex gap-3 overflow-x-auto pb-2" data-testid="scene-strip">
          {a.scenes.map((s) => (
            <div key={s.index} className="w-32 shrink-0 text-xs">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={refApi.keyframeUrl(id, s.keyframe)} alt={`Plan ${s.index}`} className="mb-1 aspect-[9/16] w-full rounded bg-black object-cover" />
              <div className="font-medium">Plan {s.index} · {s.duration.toFixed(2)} s</div>
              <div className="text-muted">{s.start.toFixed(2)}–{s.end.toFixed(2)} s</div>
              <div>{s.transition_in ? `↳ ${LABELS[s.transition_in.type] ?? s.transition_in.type}` : "début"}</div>
              <div>{LABELS[s.motion.type] ?? s.motion.type}{s.motion.zoom_total && s.motion.type.startsWith("zoom") ? ` ×${s.motion.zoom_total}` : ""}</div>
              <div className="mt-1 flex gap-1">{s.palette.slice(0, 3).map((p) => <span key={p.hex} className="h-3 w-5 rounded-sm" style={{ background: p.hex }} title={p.hex} />)}</div>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3 [&>*]:min-w-0">
        <Card title="Couleurs">
          <div className="space-y-1.5">{a.colors.palette.map((p) => <Swatch key={p.hex} hex={p.hex} share={p.share} />)}</div>
          <p className="mt-3 text-sm text-muted">{a.colors.description.join(" · ")}</p>
        </Card>
        <Card title={<span className="flex items-center gap-2">Sous-titres <ConfidenceBadge value={c.confidence} /></span>}>
          {c.detected ? (
            <ul className="space-y-1 text-sm">
              <li>Position : <b>{c.position}</b> ({c.vertical_center_pct} % de la hauteur)</li>
              <li className="flex items-center gap-2">Texte : {c.fill_color && <Swatch hex={c.fill_color} />}</li>
              <li className="flex items-center gap-2">Contour : {c.outline_color ? <Swatch hex={c.outline_color} /> : "aucun"}</li>
              <li>Découpage : {c.mode} {c.change_interval_s ? `(≈ ${c.change_interval_s} s)` : ""}</li>
              <li>Présence : {pct(c.coverage)} du temps</li>
              <li className="text-amber-300">{c.font_note}</li>
            </ul>
          ) : <p className="text-sm text-muted">{c.reason}</p>}
        </Card>
        <Card title="Audio & synchronisation">
          {au.has_audio ? (
            <ul className="space-y-1 text-sm">
              <li>Volume : {au.loudness_lufs ?? "—"} LUFS</li>
              <li>Tempo : {au.tempo_bpm ? `${Math.round(au.tempo_bpm)} BPM` : "non détecté"}</li>
              <li>{au.music?.description} <ConfidenceBadge value={au.music?.confidence ?? "faible"} /></li>
              <li>Coupes sur une attaque : {pct(au.sync?.cuts_on_onset_ratio)}</li>
              <li>Coupes sur le temps : {pct(au.sync?.cuts_on_beat_ratio)}</li>
              <li>Silences : {pct(au.silence_ratio)}</li>
              <li>{au.sound_effects?.description}</li>
            </ul>
          ) : <p className="text-sm text-muted">Pas de piste audio.</p>}
        </Card>
      </div>

      <Card title="Analyse visuelle par IA" className="mt-6">
        {a.vision.available ? (
          <>
            <Badge tone="accent">{a.vision.model}</Badge>
            <pre className="mt-2 max-h-72 overflow-auto rounded bg-surface-2 p-3 text-xs">{JSON.stringify(a.vision.frames, null, 2)}</pre>
            <p className="mt-2 text-xs text-muted">{a.vision.note}</p>
          </>
        ) : <p className="text-sm text-muted">{a.vision.note}</p>}
      </Card>

      <Card title="Limites de l'analyse" className="mt-6">
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted">{a.limits.map((l) => <li key={l}>{l}</li>)}</ul>
      </Card>
    </main>
  );
}
