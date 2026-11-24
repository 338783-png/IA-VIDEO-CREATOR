"use client";
import { useEffect, useState } from "react";
import JobStatus from "@/components/JobStatus";
import { Badge, Card } from "@/components/ui";
import { api, voiceApi, type StoryboardOut, type VoiceInfo, type VoiceTrackItem } from "@/lib/api";
import { useJob } from "@/lib/useJob";

const field = "mt-1 w-full rounded border border-border bg-surface-2 px-2 py-1 text-sm";

export default function VoicePanel({ projectId, sb, onUse, onGenerated }: {
  projectId: number; sb: StoryboardOut | null;
  onUse: (mediaId: number) => void; onGenerated: () => void;
}) {
  const [voices, setVoices] = useState<VoiceInfo[]>([]);
  const [tracks, setTracks] = useState<VoiceTrackItem[]>([]);
  const [text, setText] = useState("");
  const [voiceId, setVoiceId] = useState("");
  const [speaker, setSpeaker] = useState<string>("");
  const [speed, setSpeed] = useState(1.0);
  const [pause, setPause] = useState(0.35);
  const [volume, setVolume] = useState(0);
  const [sample, setSample] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadTracks = () => voiceApi.tracks(projectId).then(setTracks).catch(() => {});
  useEffect(() => {
    voiceApi.list().then((r) => {
      const ok = r.voices.filter((v) => !v.excluded);
      setVoices(ok);
      if (ok.length) setVoiceId((v) => v || ok[0].id);
    }).catch((e) => setErr(e.message));
    loadTracks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  useEffect(() => {
    if (text || !sb) return;
    const vo = sb.data.audio?.voiceover;
    setText(vo?.script || sb.data.scenes.map((s) => s.text).filter(Boolean).join(" "));
  }, [sb, text]);

  const voice = voices.find((v) => v.id === voiceId);
  const params = { voice_id: voiceId, speaker: speaker || null, speed, pause_s: pause, volume_db: volume };
  const job = useJob((j) => { if (j.status === "done") { loadTracks(); onGenerated(); } });

  async function listen() {
    setErr(null); setBusy(true);
    try {
      if (sample) URL.revokeObjectURL(sample);
      setSample(await voiceApi.preview({ ...params, text: text.slice(0, 400) }));
    } catch (e) { setErr((e as Error).message); }
    setBusy(false);
  }

  const used = sb?.data.audio?.voiceover_media_id;
  return (
    <Card title="Voix off (synthèse locale)">
      {!voices.length && <p className="text-sm text-muted">Aucune voix installée (dossier ai/models/piper).</p>}
      {err && <p className="mb-2 text-sm text-rose-400">{err}</p>}
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} maxLength={20000} placeholder="Texte de la voix off…"
        className="w-full rounded-lg border border-border bg-surface-2 p-2 text-sm outline-none focus:border-accent" />
      <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-muted">
        <label className="col-span-2">Voix<select value={voiceId} onChange={(e) => { setVoiceId(e.target.value); setSpeaker(""); }} className={field}>
          {voices.map((v) => <option key={v.id} value={v.id}>{v.name} ({v.quality}) — {v.license}</option>)}</select></label>
        {voice && voice.speakers.length > 1 && (
          <label className="col-span-2">Locuteur ({voice.speakers.length})<select value={speaker} onChange={(e) => setSpeaker(e.target.value)} className={field}>
            {voice.speakers.map((s) => <option key={s.id} value={s.id}>Voix {s.index + 1} ({s.id})</option>)}</select></label>
        )}
        <label>Vitesse ×{speed.toFixed(2)}<input type="range" min="0.6" max="1.6" step="0.05" value={speed} onChange={(e) => setSpeed(+e.target.value)} className="w-full accent-violet-500" /></label>
        <label>Pause entre phrases {pause.toFixed(2)} s<input type="range" min="0" max="1.5" step="0.05" value={pause} onChange={(e) => setPause(+e.target.value)} className="w-full accent-violet-500" /></label>
        <label className="col-span-2">Volume {volume > 0 ? "+" : ""}{volume} dB<input type="range" min="-12" max="6" step="1" value={volume} onChange={(e) => setVolume(+e.target.value)} className="w-full accent-violet-500" /></label>
      </div>
      {voice && <p className="mt-1 text-[11px] text-muted">{voice.attribution}</p>}
      <div className="mt-3 flex gap-2">
        <button disabled={!text.trim() || !voiceId || busy} onClick={listen} className="flex-1 rounded-lg border border-border px-3 py-2 text-sm hover:border-accent disabled:opacity-40">
          {busy ? "…" : "▶ Écouter un extrait"}</button>
        <button disabled={!text.trim() || !voiceId || job.running} onClick={async () => {
          setErr(null);
          try { job.start(await voiceApi.generate(projectId, { ...params, text, name: "voix-off" })); } catch (e) { setErr((e as Error).message); }
        }} className="flex-1 rounded-lg bg-accent px-3 py-2 text-sm font-medium disabled:opacity-40">Générer</button>
      </div>
      {sample && <audio src={sample} controls autoPlay className="mt-2 w-full" />}
      <JobStatus job={job.job} onCancel={job.cancel} />
      {tracks.length > 0 && (
        <ul className="mt-3 space-y-2 text-xs">
          {tracks.map((t) => (
            <li key={t.media_id} className="rounded-lg border border-border bg-surface-2 p-2">
              <div className="mb-1 flex items-center gap-2">
                <span className="flex-1 truncate">{t.name} · {t.duration?.toFixed(1)} s · ×{t.params.speed}</span>
                {used === t.media_id ? <Badge tone="good">utilisée</Badge> : sb &&
                  <button onClick={() => onUse(t.media_id)} className="rounded border border-accent px-2 py-0.5 text-violet-200">Utiliser dans le montage</button>}
              </div>
              <audio src={api.mediaUrl(t.media_id)} controls className="w-full" preload="none" />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
