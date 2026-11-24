"use client";
import { useEffect, useState } from "react";
import { Badge, Card } from "@/components/ui";
import { charApi, voiceApi, type Character, type VoiceInfo } from "@/lib/api";

const field = "mt-1 w-full rounded border border-border bg-surface-2 px-2 py-1.5 text-sm";
const EMPTY = { name: "", description: "", voice_id: "", speaker: "", speed: 1 };

export default function Characters() {
  const [list, setList] = useState<Character[]>([]);
  const [voices, setVoices] = useState<VoiceInfo[]>([]);
  const [edit, setEdit] = useState<Character | null>(null);
  const [f, setF] = useState(EMPTY);
  const [err, setErr] = useState<string | null>(null);
  const [sample, setSample] = useState<string | null>(null);

  const load = () => charApi.list().then(setList).catch((e) => setErr(e.message));
  useEffect(() => { load(); voiceApi.list().then((r) => setVoices(r.voices.filter((v) => !v.excluded))).catch(() => {}); }, []);

  function pick(c: Character | null) {
    setEdit(c); setErr(null); setSample(null);
    const v = (c?.voice ?? {}) as { voice_id?: string; speaker?: string; speed?: number };
    setF(c ? { name: c.name, description: c.description, voice_id: v.voice_id ?? "", speaker: v.speaker ?? "", speed: v.speed ?? 1 } : EMPTY);
  }
  const voice = voices.find((v) => v.id === f.voice_id);
  const body = () => ({ name: f.name.trim(), description: f.description,
    voice: f.voice_id ? { voice_id: f.voice_id, speaker: f.speaker || (voice?.speakers[0]?.id ?? null), speed: f.speed } : undefined });

  async function run(fn: () => Promise<unknown>) { setErr(null); try { await fn(); await load(); } catch (e) { setErr((e as Error).message); } }

  return (
    <main className="mx-auto max-w-6xl px-4 py-6">
      <h1 className="mb-1 text-2xl font-bold">Personnages</h1>
      <p className="mb-6 text-sm text-muted">Bibliothèque commune à tous vos projets animés : nom, description, voix. L&apos;apparence 2D/3D se règle dans les étapes suivantes du module.</p>
      {err && <p className="mb-4 text-sm text-rose-400">{err}</p>}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px] [&>*]:min-w-0">
        <ul className="grid content-start gap-3 sm:grid-cols-2" data-testid="character-list">
          {list.length === 0 && <li className="text-sm text-muted">Aucun personnage. Créez-en un à droite.</li>}
          {list.map((c) => (
            <li key={c.id} className={`rounded-xl border bg-surface p-3 ${edit?.id === c.id ? "border-accent" : "border-border"}`}>
              <div className="flex items-center gap-2"><span className="grid h-9 w-9 place-items-center rounded-full bg-accent/30 font-bold">{c.name[0]}</span>
                <b className="flex-1 truncate">{c.name}</b><Badge>{c.kind.toUpperCase()}</Badge></div>
              <p className="mt-1 line-clamp-2 text-xs text-muted">{c.description || "—"}</p>
              <p className="mt-1 text-xs">{"voice_id" in c.voice && c.voice.voice_id ? `Voix : ${c.voice.voice_id}${c.voice.speaker ? ` (${c.voice.speaker})` : ""} ×${c.voice.speed}` : <span className="text-amber-300">Pas de voix</span>}</p>
              <div className="mt-2 flex gap-2 text-xs">
                <button onClick={() => pick(c)} className="rounded border border-border px-2 py-1 hover:border-accent">Modifier</button>
                <button onClick={() => run(() => charApi.duplicate(c.id))} className="rounded border border-border px-2 py-1 hover:border-accent">Dupliquer</button>
                <button onClick={() => window.confirm(`Retirer « ${c.name} » de la bibliothèque ?`) && run(async () => { await charApi.remove(c.id); if (edit?.id === c.id) pick(null); })}
                  className="rounded border border-rose-500/40 px-2 py-1 text-rose-300">Supprimer</button>
              </div>
            </li>
          ))}
        </ul>
        <Card title={edit ? `Modifier « ${edit.name} »` : "Nouveau personnage"}>
          <div className="space-y-2 text-xs text-muted">
            <label className="block">Nom<input value={f.name} maxLength={100} onChange={(e) => setF({ ...f, name: e.target.value })} className={field} /></label>
            <label className="block">Description (personnalité, rôle)<textarea value={f.description} rows={2} maxLength={1000} onChange={(e) => setF({ ...f, description: e.target.value })} className={field} /></label>
            <label className="block">Voix<select value={f.voice_id} onChange={(e) => setF({ ...f, voice_id: e.target.value, speaker: "" })} className={field}>
              <option value="">Aucune</option>{voices.map((v) => <option key={v.id} value={v.id}>{v.name} ({v.quality}) — {v.license}</option>)}</select></label>
            {voice && voice.speakers.length > 1 && <label className="block">Locuteur<select value={f.speaker} onChange={(e) => setF({ ...f, speaker: e.target.value })} className={field}>
              {voice.speakers.map((s) => <option key={s.id} value={s.id}>Voix {s.index + 1} ({s.id})</option>)}</select></label>}
            {f.voice_id && <label className="block">Vitesse ×{f.speed.toFixed(2)}<input type="range" min="0.7" max="1.5" step="0.05" value={f.speed} onChange={(e) => setF({ ...f, speed: +e.target.value })} className="w-full accent-violet-500" /></label>}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button disabled={!f.name.trim()} onClick={() => run(async () => { if (edit) pick(await charApi.update(edit.id, body())); else { await charApi.create(body()); pick(null); } })}
              className="rounded-lg bg-accent px-3 py-1.5 text-sm text-white disabled:opacity-40">{edit ? "Enregistrer" : "Créer"}</button>
            {f.voice_id && <button onClick={async () => { try { setSample(await voiceApi.preview({ text: `Bonjour, je suis ${f.name || "un personnage"} !`, voice_id: f.voice_id, speaker: f.speaker || voice?.speakers[0]?.id, speed: f.speed, pause_s: 0, volume_db: 0 })); } catch (e) { setErr((e as Error).message); } }}
              className="rounded-lg border border-border px-3 py-1.5 text-sm">▶ Écouter la voix</button>}
            {edit && <button onClick={() => pick(null)} className="rounded-lg px-3 py-1.5 text-sm text-muted">Annuler</button>}
          </div>
          {sample && <audio src={sample} controls autoPlay className="mt-2 w-full" />}
        </Card>
      </div>
    </main>
  );
}
