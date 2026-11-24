"use client";
import { useEffect, useMemo, useState } from "react";
import Timeline from "@/timeline/Timeline";
import { Badge, Card } from "@/components/ui";
import { EFFECTS, TRANSITIONS, type Media, type SbScene, type StoryboardData, type StoryboardOut } from "@/lib/api";

const num = (v: string, d = 0) => (Number.isFinite(parseFloat(v)) ? parseFloat(v) : d);
const input = "w-full rounded border border-border bg-surface px-2 py-1 text-sm";

function recompute(scenes: SbScene[]): { scenes: SbScene[]; total: number } {
  let t = 0;
  const out = scenes.map((s, i) => {
    const duration = Math.max(0, +(s.end - s.start).toFixed(3));
    return { ...s, position: i + 1, duration };
  });
  out.forEach((s, i) => {
    s.timeline_start = +t.toFixed(3);
    const next = out[i + 1];
    const td = next && s.transition !== "cut" ? Math.min(s.transition_duration || 0.3, s.duration / 2, next.duration / 2) : 0;
    t += s.duration - td;
  });
  return { scenes: out, total: +t.toFixed(3) };
}

export default function StoryboardEditor({ sb, media, onSave, saving }: {
  sb: StoryboardOut; media: Media[]; saving: boolean;
  onSave: (data: Partial<StoryboardData> & { base_version: number }) => void;
}) {
  const [scenes, setScenes] = useState<SbScene[]>(sb.data.scenes);
  const [subs, setSubs] = useState(sb.data.subtitles);
  const [audio, setAudio] = useState(sb.data.audio);
  const [fit, setFit] = useState(sb.data.fit_mode);
  const [selected, setSelected] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setScenes(sb.data.scenes); setSubs(sb.data.subtitles); setAudio(sb.data.audio); setFit(sb.data.fit_mode); setDirty(false);
  }, [sb]);

  const { scenes: view, total } = useMemo(() => recompute(scenes), [scenes]);
  const audios = media.filter((m) => m.category === "audio");
  const visuals = media.filter((m) => m.category === "video" || m.category === "image");

  const change = (fn: (s: SbScene[]) => SbScene[]) => { setScenes((prev) => fn([...prev])); setDirty(true); };
  const patch = (id: string, p: Partial<SbScene>) => change((s) => s.map((x) => (x.id === id ? { ...x, ...p } : x)));
  const move = (i: number, d: number) => change((s) => { const j = i + d; if (j < 0 || j >= s.length) return s; [s[i], s[j]] = [s[j], s[i]]; return s; });
  const remove = (i: number) => change((s) => (s.length > 1 ? s.filter((_, k) => k !== i) : s));
  const addScene = (m: Media) => change((s) => {
    const id = `s${Date.now().toString(36)}`;
    const dur = Math.min(3, m.probe.duration ?? 3);
    return [...s, { id, position: s.length + 1, media_id: m.id, source: m.original_name, kind: m.category === "image" ? "image" : "video",
      start: 0, end: dur, duration: dur, text: "", text_auto: false, words: [], effect: m.category === "image" ? "zoom_in" : "none",
      transition: "cut", transition_duration: 0, volume: 1 }];
  });

  return (
    <div className="space-y-4">
      <Card title={<span className="flex flex-wrap items-center gap-2">Storyboard v{sb.version}
        <Badge tone={sb.status === "validated" ? "good" : "warn"}>{sb.status === "validated" ? "validé" : "brouillon"}</Badge>
        <Badge>{view.length} scènes · {total.toFixed(1)} s</Badge>
        {sb.data.target_duration ? <Badge>cible {sb.data.target_duration.toFixed(0)} s</Badge> : null}
        <Badge tone="accent">style : {sb.data.style?.name}</Badge></span>}>
        <Timeline scenes={view} total={total} selected={selected} onSelect={setSelected} />
        {sb.data.notes?.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-amber-200">{sb.data.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
        {sb.data.llm?.used && sb.data.llm.title && <p className="mt-2 text-xs text-muted">IA : « {sb.data.llm.title} » — {sb.data.llm.reason}</p>}
      </Card>

      <ol className="space-y-2" data-testid="scene-list">
        {view.map((s, i) => (
          <li key={s.id} onClick={() => setSelected(s.id)}
            className={`rounded-xl border bg-surface p-3 ${selected === s.id ? "border-accent" : "border-border"}`}>
            <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
              <span className="grid h-6 w-6 place-items-center rounded bg-surface-2 text-xs font-bold">{s.position}</span>
              <span className="truncate font-medium">{s.source}</span>
              <Badge>{s.kind === "image" ? "image" : "vidéo"}</Badge>
              <span className="text-xs text-muted">sur la timeline à {s.timeline_start?.toFixed(1)} s</span>
              <div className="ml-auto flex gap-1">
                <button aria-label="Monter" onClick={() => move(i, -1)} disabled={i === 0} className="rounded border border-border px-2 disabled:opacity-30">↑</button>
                <button aria-label="Descendre" onClick={() => move(i, 1)} disabled={i === view.length - 1} className="rounded border border-border px-2 disabled:opacity-30">↓</button>
                <button aria-label="Supprimer" onClick={() => remove(i)} disabled={view.length === 1} className="rounded border border-rose-500/40 px-2 text-rose-300 disabled:opacity-30">✕</button>
              </div>
            </div>
            <div className="grid gap-2 sm:grid-cols-6">
              <label className="text-xs text-muted">Début (s)
                <input type="number" step="0.1" min="0" value={s.start} disabled={s.kind === "image"} className={input}
                  onChange={(e) => patch(s.id, { start: num(e.target.value, s.start) })} /></label>
              <label className="text-xs text-muted">Fin (s)
                <input type="number" step="0.1" min="0" value={s.end} className={input} onChange={(e) => patch(s.id, { end: num(e.target.value, s.end) })} /></label>
              <label className="text-xs text-muted">Durée
                <input readOnly value={`${s.duration.toFixed(2)} s`} className={`${input} opacity-70`} /></label>
              <label className="text-xs text-muted">Effet
                <select value={s.effect} className={input} onChange={(e) => patch(s.id, { effect: e.target.value })}>
                  {Object.entries(EFFECTS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select></label>
              <label className="text-xs text-muted">Transition → suivante
                <select value={s.transition} disabled={i === view.length - 1} className={input}
                  onChange={(e) => patch(s.id, { transition: e.target.value, transition_duration: e.target.value === "cut" ? 0 : s.transition_duration || 0.3 })}>
                  {Object.entries(TRANSITIONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select></label>
              <label className="text-xs text-muted">Volume
                <input type="number" step="0.1" min="0" max="2" value={s.volume} className={input} onChange={(e) => patch(s.id, { volume: num(e.target.value, 1) })} /></label>
            </div>
            <label className="mt-2 block text-xs text-muted">Texte / sous-titre {s.text_auto ? <span className="text-emerald-400">(transcription)</span> : <span className="text-amber-300">(modifié)</span>}
              <textarea value={s.text} rows={2} className={input} onChange={(e) => patch(s.id, { text: e.target.value })} /></label>
            {s.reason && <p className="mt-1 text-[11px] text-muted">Pourquoi : {s.reason}{s.score != null ? ` (score ${s.score})` : ""}</p>}
          </li>
        ))}
      </ol>

      {visuals.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted">Ajouter une scène :</span>
          {visuals.map((m) => <button key={m.id} onClick={() => addScene(m)} className="rounded-lg border border-border px-2 py-1 text-xs hover:border-accent">+ {m.original_name}</button>)}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Sous-titres">
          <div className="grid grid-cols-2 gap-2 text-xs text-muted">
            <label className="col-span-2 flex items-center gap-2 text-sm text-foreground"><input type="checkbox" checked={subs.enabled} className="accent-violet-500"
              onChange={(e) => { setSubs({ ...subs, enabled: e.target.checked }); setDirty(true); }} /> Sous-titres incrustés</label>
            <label>Découpage<select value={subs.mode} className={input} onChange={(e) => { setSubs({ ...subs, mode: e.target.value as SbScene["effect"] as never }); setDirty(true); }}>
              <option value="word">Mot par mot</option><option value="chunk">2-3 mots</option><option value="phrase">Phrases</option></select></label>
            <label className="col-span-2">Texte affiché<select value={subs.source ?? "scenes"} className={input}
              onChange={(e) => { setSubs({ ...subs, source: e.target.value as "scenes" | "voiceover" }); setDirty(true); }}>
              <option value="scenes">Paroles des scènes</option><option value="voiceover" disabled={!audio.voiceover_media_id}>Voix off</option></select></label>
            <label>Position<select value={subs.position} className={input} onChange={(e) => { setSubs({ ...subs, position: e.target.value as never }); setDirty(true); }}>
              <option value="haut">Haut</option><option value="centre">Centre</option><option value="bas">Bas</option></select></label>
            <label className="col-span-2">Police<input value={subs.font} className={input} onChange={(e) => { setSubs({ ...subs, font: e.target.value }); setDirty(true); }} /></label>
            <label>Texte<input type="color" value={subs.primary_color} className="block h-8 w-full" onChange={(e) => { setSubs({ ...subs, primary_color: e.target.value.toUpperCase() }); setDirty(true); }} /></label>
            <label>Mot surligné<input type="color" value={subs.highlight_color} className="block h-8 w-full" onChange={(e) => { setSubs({ ...subs, highlight_color: e.target.value.toUpperCase() }); setDirty(true); }} /></label>
            <label>Contour<input type="color" value={subs.outline_color} className="block h-8 w-full" onChange={(e) => { setSubs({ ...subs, outline_color: e.target.value.toUpperCase() }); setDirty(true); }} /></label>
            <label>Taille (% hauteur)<input type="number" step="0.2" min="2" max="10" value={subs.size_pct} className={input} onChange={(e) => { setSubs({ ...subs, size_pct: num(e.target.value, 4.6) }); setDirty(true); }} /></label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={subs.animated} className="accent-violet-500" onChange={(e) => { setSubs({ ...subs, animated: e.target.checked }); setDirty(true); }} /> Animés</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={subs.uppercase} className="accent-violet-500" onChange={(e) => { setSubs({ ...subs, uppercase: e.target.checked }); setDirty(true); }} /> Majuscules</label>
          </div>
        </Card>
        <Card title="Audio et cadrage">
          <div className="grid grid-cols-2 gap-2 text-xs text-muted">
            <label className="col-span-2">Musique de fond<select value={audio.music_media_id ?? ""} className={input}
              onChange={(e) => { setAudio({ ...audio, music_media_id: e.target.value ? Number(e.target.value) : null }); setDirty(true); }}>
              <option value="">Aucune</option>{audios.map((m) => <option key={m.id} value={m.id}>{m.original_name}</option>)}</select></label>
            <label>Volume musique (dB)<input type="number" step="1" min="-40" max="0" value={audio.music_volume_db} className={input}
              onChange={(e) => { setAudio({ ...audio, music_volume_db: num(e.target.value, -16) }); setDirty(true); }} /></label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={audio.ducking} className="accent-violet-500"
              onChange={(e) => { setAudio({ ...audio, ducking: e.target.checked }); setDirty(true); }} /> Baisser sous la voix</label>
            <label className="col-span-2">Voix off<select value={audio.voiceover_media_id ?? ""} className={input}
              onChange={(e) => { setAudio({ ...audio, voiceover_media_id: e.target.value ? Number(e.target.value) : null }); setDirty(true); }}>
              <option value="">Aucune</option>{audios.map((m) => <option key={m.id} value={m.id}>{m.original_name}</option>)}</select></label>
            {audio.voiceover?.requested && !audio.voiceover_media_id && <p className="col-span-2 text-amber-300">Voix off demandée : {audio.voiceover.status}</p>}
            <label>Volume du son original<input type="number" step="0.05" min="0" max="2" value={audio.original_volume} className={input}
              onChange={(e) => { setAudio({ ...audio, original_volume: num(e.target.value, 1) }); setDirty(true); }} /></label>
            <label>Cadrage<select value={fit} className={input} onChange={(e) => { setFit(e.target.value as "cover" | "blur"); setDirty(true); }}>
              <option value="cover">Remplir (recadrer)</option><option value="blur">Image entière + fond flou</option></select></label>
          </div>
        </Card>
      </div>

      {sb.data.rejected?.length > 0 && (
        <details className="rounded-xl border border-border bg-surface p-3 text-sm">
          <summary className="cursor-pointer">Passages écartés ({sb.data.rejected.length}) : répétitions, hésitations, silences</summary>
          <ul className="mt-2 space-y-1 text-xs text-muted">
            {sb.data.rejected.map((r, i) => <li key={i}>{r.source} {r.start.toFixed(1)}–{r.end.toFixed(1)} s · <b>{r.reason}</b> {r.text && `« ${r.text.slice(0, 80)} »`}</li>)}
          </ul>
        </details>
      )}

      {dirty && <div className="sticky bottom-3 z-10 flex items-center gap-3 rounded-xl border border-accent bg-surface/95 p-3 shadow-lg backdrop-blur">
        <span className="flex-1 text-sm">Modifications non enregistrées.</span>
        <button disabled={!dirty || saving} onClick={() => onSave({ base_version: sb.version, scenes: view, subtitles: subs, audio, fit_mode: fit })}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium disabled:opacity-40">{saving ? "Enregistrement…" : "Enregistrer (nouvelle version)"}</button>
      </div>}
    </div>
  );
}
