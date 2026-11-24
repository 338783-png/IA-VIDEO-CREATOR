"use client";
import { use, useCallback, useEffect, useState } from "react";
import JobStatus from "@/components/JobStatus";
import UploadZone from "@/components/UploadZone";
import ScenarioEditor from "@/components/ScenarioEditor";
import SubtitleEditor from "@/components/SubtitleEditor";
import VoicePanel from "@/components/VoicePanel";
import { Badge, Card } from "@/components/ui";
import StoryboardEditor from "@/storyboard/StoryboardEditor";
import {
  api, editApi, styleApi, type EngineStatus, type ExportItem, type Media, type MediaAnalysisItem, type ProjectDetail,
  type StoryboardData, type StoryboardOut, type StyleListItem,
} from "@/lib/api";
import { useJob } from "@/lib/useJob";

const STEPS = ["Importer", "Analyser", "Storyboard", "Aperçu", "Valider", "Exporter"];

export default function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const id = Number(use(params).id);
  const [p, setP] = useState<ProjectDetail | null>(null);
  const [analysis, setAnalysis] = useState<MediaAnalysisItem[]>([]);
  const [sb, setSb] = useState<StoryboardOut | null>(null);
  const [styles, setStyles] = useState<StyleListItem[]>([]);
  const [engine, setEngine] = useState<EngineStatus | null>(null);
  const [exports, setExports] = useState<ExportItem[]>([]);
  const [instruction, setInstruction] = useState("");
  const [styleId, setStyleId] = useState<number | "">("");
  const [duration, setDuration] = useState("");
  const [exp, setExp] = useState({ platform: "tiktok", quality: "standard", fps: 30 });
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [previewKey, setPreviewKey] = useState(0);

  const loadSb = useCallback(() => editApi.storyboard(id).then(setSb).catch(() => setSb(null)), [id]);
  const load = useCallback(async () => {
    try {
      const d = await api.getProject(id);
      setP(d);
      setInstruction((v) => v || d.instruction);
      setExp((e) => ({ ...e, platform: d.target_format }));
      setAnalysis(await editApi.analysis(id));
      setExports(await editApi.exports(id));
    } catch (e) { setErr((e as Error).message); }
  }, [id]);
  useEffect(() => {
    load(); loadSb();
    styleApi.list().then((s) => setStyles(s.filter((x) => x.status === "validated"))).catch(() => {});
    editApi.engine().then(setEngine).catch(() => {});
  }, [load, loadSb]);

  const analyzeJob = useJob(() => load());
  const genJob = useJob((j) => { if (j.status === "done") loadSb(); load(); });
  const prevJob = useJob((j) => { if (j.status === "done") { loadSb(); setPreviewKey((k) => k + 1); } });
  const expJob = useJob(() => { load(); loadSb(); });

  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setErr(null);
    try { return await fn(); } catch (e) { setErr((e as Error).message); }
  }

  async function save(data: Partial<StoryboardData> & { base_version: number }) {
    setSaving(true);
    const r = await run(() => editApi.save(id, data));
    if (r) setSb(r);
    setSaving(false);
  }

  if (err && !p) return <main className="mx-auto max-w-7xl px-4 py-6"><p className="text-rose-400">{err}</p></main>;
  if (!p) return <main className="mx-auto max-w-7xl px-4 py-6"><p className="text-muted">Chargement…</p></main>;

  const media = p.media.filter((m) => m.kind !== "reference") as Media[];
  const toAnalyze = analysis.filter((a) => ["video", "audio"].includes(a.media.category));
  const allAnalyzed = toAnalyze.length > 0 && toAnalyze.every((a) => a.analyzed);
  const step = exports.length ? 5 : sb?.status === "validated" ? 4 : sb?.has_preview ? 3 : sb ? 2 : allAnalyzed ? 1 : 0;

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">{p.name}</h1>
        <Badge>{p.target_format}</Badge>
      </div>
      <ol className="mb-6 flex flex-wrap gap-2 text-xs" aria-label="Étapes">
        {STEPS.map((s, i) => (
          <li key={s} className={`rounded-full px-3 py-1 ${i <= step ? "bg-accent text-white" : "bg-surface-2 text-muted"}`}>{i + 1}. {s}</li>
        ))}
      </ol>
      {err && <p className="mb-4 rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200">{err}</p>}

      <div className="grid gap-6 lg:grid-cols-[340px_minmax(0,1fr)] [&>*]:min-w-0">
        {/* ---------- colonne gauche : médias, analyse, consigne ---------- */}
        <aside className="space-y-4">
          <Card title="1. Médias du projet">
            <div className="space-y-2">
              <UploadZone kind="video" projectId={id} onUploaded={load} compact />
              <UploadZone kind="audio" projectId={id} onUploaded={load} compact />
              <UploadZone kind="image" projectId={id} onUploaded={load} compact />
              <UploadZone kind="script" projectId={id} onUploaded={load} compact />
            </div>
            <ul className="mt-3 space-y-1.5 text-xs" data-testid="media-list">
              {media.map((m) => {
                const a = analysis.find((x) => x.media.id === m.id);
                return (
                  <li key={m.id} className="rounded-lg border border-border bg-surface-2 p-2">
                    <div className="flex items-center gap-2"><span className="flex-1 truncate font-medium">{m.original_name}</span>
                      <Badge>{m.kind}</Badge>
                      {["video", "audio"].includes(m.category) && <Badge tone={a?.analyzed ? "good" : "warn"}>{a?.analyzed ? "analysé" : "à analyser"}</Badge>}
                    </div>
                    <div className="text-muted">{[m.probe.duration ? `${m.probe.duration.toFixed(1)} s` : "", m.probe.video ? `${m.probe.video.width}×${m.probe.video.height}` : ""].filter(Boolean).join(" · ")}
                      {a?.data?.shots ? ` · ${a.data.shots.length} plans` : ""}{a?.data?.tempo_bpm ? ` · ${Math.round(a.data.tempo_bpm)} BPM` : ""}</div>
                    {a?.transcript?.text && <p className="mt-1 line-clamp-3 italic text-muted">« {a.transcript.text} »</p>}
                    {a?.data?.transcription_note && <p className="mt-1 text-amber-300">{a.data.transcription_note}</p>}
                  </li>
                );
              })}
            </ul>
          </Card>

          <Card title="2. Analyse">
            {engine && (
              <ul className="mb-3 space-y-1 text-xs text-muted">
                <li>Whisper : {engine.whisper.library ? (engine.whisper.downloaded ? `prêt (${engine.whisper.model})` : `modèle « ${engine.whisper.model} » téléchargé au 1er usage (~${engine.whisper.approx_size_mb} Mo)`) : "non installé"}</li>
                <li>Ollama : {engine.ollama.model_ready ? `prêt (${engine.ollama.configured_model})` : engine.ollama.available ? "démarré, modèle absent — sélection par règles" : "arrêté — sélection par règles"}</li>
              </ul>
            )}
            <button disabled={analyzeJob.running || !toAnalyze.length} onClick={async () => { const j = await run(() => editApi.analyze(id, allAnalyzed)); if (j) analyzeJob.start(j); }}
              className="w-full rounded-lg bg-accent px-3 py-2 text-sm font-medium disabled:opacity-40">
              {allAnalyzed ? "Relancer l'analyse" : "Analyser (scènes, silences, transcription)"}</button>
            <JobStatus job={analyzeJob.job} onCancel={analyzeJob.cancel} />
          </Card>

          <Card title="3. Consigne de montage">
            <textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} rows={5} maxLength={5000}
              placeholder="Ex. : Transforme cette vidéo en TikTok éducatif de 60 s avec sous-titres animés, zooms, transitions dynamiques et musique discrète."
              className="w-full rounded-lg border border-border bg-surface-2 p-2 text-sm outline-none focus:border-accent" />
            <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-muted">
              <label>Style<select value={styleId} onChange={(e) => setStyleId(e.target.value ? Number(e.target.value) : "")} className="mt-1 w-full rounded border border-border bg-surface-2 px-2 py-1 text-sm">
                <option value="">Style officiel / défaut</option>{styles.map((s) => <option key={s.id} value={s.id}>{s.is_official ? "★ " : ""}{s.name}</option>)}</select></label>
              <label>Durée (s, optionnel)<input type="number" min="5" max="600" value={duration} onChange={(e) => setDuration(e.target.value)} placeholder="depuis la consigne"
                className="mt-1 w-full rounded border border-border bg-surface-2 px-2 py-1 text-sm" /></label>
            </div>
            <button disabled={!allAnalyzed || genJob.running} onClick={async () => {
              const j = await run(() => editApi.generate(id, { instruction, style_id: styleId || null, target_duration: duration ? Number(duration) : null }));
              if (j) genJob.start(j);
            }} className="mt-3 w-full rounded-lg bg-accent px-3 py-2 text-sm font-medium disabled:opacity-40">
              {sb ? "Régénérer le storyboard" : "Générer le storyboard"}</button>
            {!allAnalyzed && <p className="mt-1 text-xs text-muted">Analysez d&apos;abord les médias.</p>}
            <JobStatus job={genJob.job} onCancel={genJob.cancel} />
          </Card>

          <VoicePanel projectId={id} sb={sb} onGenerated={load} onUse={(mid) => sb && save({
            base_version: sb.version, scenes: sb.data.scenes,
            audio: { ...sb.data.audio, voiceover_media_id: mid, original_volume: Math.min(sb.data.audio.original_volume, 0.25) },
            subtitles: { ...sb.data.subtitles, source: "voiceover" } as typeof sb.data.subtitles,
          })} />
        </aside>

        {/* ---------- colonne droite : aperçu, storyboard, export ---------- */}
        <section className="space-y-4">
          {sb && (
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px] [&>*]:min-w-0">
              <Card title="4. Aperçu">
                <div className={`mx-auto overflow-hidden rounded-lg bg-black ${sb.data.format.height > sb.data.format.width ? "aspect-[9/16] max-h-[560px]" : "aspect-video"}`}>
                  {sb.has_preview ? (
                    <video key={`${sb.version}-${previewKey}`} src={`${editApi.previewUrl(id, sb.version)}&k=${previewKey}`} controls className="h-full w-full" data-testid="preview-player" />
                  ) : (
                    <div className="grid h-full place-items-center p-4 text-center text-sm text-muted">Aperçu non généré pour la version {sb.version}.</div>
                  )}
                </div>
                <button disabled={prevJob.running} onClick={async () => { const j = await run(() => editApi.preview(id)); if (j) prevJob.start(j); }}
                  className="mt-3 w-full rounded-lg border border-border px-3 py-2 text-sm hover:border-accent disabled:opacity-40">
                  {sb.has_preview ? "Regénérer l'aperçu" : "Générer l'aperçu (basse résolution)"}</button>
                <JobStatus job={prevJob.job} onCancel={prevJob.cancel} />
                {prevJob.job?.status === "done" && (prevJob.job.result.warnings as string[] | undefined)?.map((w) => <p key={w} className="mt-1 text-xs text-amber-300">{w}</p>)}
              </Card>
              <div className="space-y-4">
                <Card title="5. Validation">
                  <p className="mb-2 text-xs text-muted">Visionnez l&apos;aperçu, puis validez. Toute modification ultérieure demandera une nouvelle validation.</p>
                  <button disabled={!sb.has_preview || sb.status === "validated"} onClick={async () => { const r = await run(() => editApi.validate(id, sb.version)); if (r) setSb(r); }}
                    className="w-full rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium disabled:opacity-40">
                    {sb.status === "validated" ? "✓ Montage validé" : "Valider ce montage"}</button>
                </Card>
                <Card title="6. Export MP4">
                  <div className="space-y-2 text-xs text-muted">
                    <label className="block">Format<select value={exp.platform} onChange={(e) => setExp({ ...exp, platform: e.target.value })} className="mt-1 w-full rounded border border-border bg-surface-2 px-2 py-1 text-sm">
                      <option value="tiktok">TikTok 1080×1920</option><option value="reels">Instagram Reels 1080×1920</option>
                      <option value="shorts">YouTube Shorts 1080×1920</option><option value="youtube">YouTube 1920×1080</option></select></label>
                    <div className="grid grid-cols-2 gap-2">
                      <label>Qualité<select value={exp.quality} onChange={(e) => setExp({ ...exp, quality: e.target.value })} className="mt-1 w-full rounded border border-border bg-surface-2 px-2 py-1 text-sm">
                        <option value="haute">Haute</option><option value="standard">Standard</option><option value="rapide">Rapide</option></select></label>
                      <label>Images/s<select value={exp.fps} onChange={(e) => setExp({ ...exp, fps: Number(e.target.value) })} className="mt-1 w-full rounded border border-border bg-surface-2 px-2 py-1 text-sm">
                        {[24, 25, 30, 50, 60].map((f) => <option key={f} value={f}>{f}</option>)}</select></label>
                    </div>
                    <p>MP4 · H.264 · AAC. Aucune publication automatique.</p>
                  </div>
                  <button disabled={sb.status !== "validated" || expJob.running} onClick={async () => {
                    if (!window.confirm(`Exporter la version ${sb.version} en MP4 (${exp.platform}, qualité ${exp.quality}, ${exp.fps} i/s) ?`)) return;
                    const j = await run(() => editApi.exportVideo(id, exp)); if (j) expJob.start(j);
                  }} className="mt-3 w-full rounded-lg bg-accent px-3 py-2 text-sm font-medium disabled:opacity-40">Exporter</button>
                  {sb.status !== "validated" && <p className="mt-1 text-xs text-muted">Validez d&apos;abord le montage.</p>}
                  <JobStatus job={expJob.job} onCancel={expJob.cancel} />
                  <ul className="mt-3 space-y-1 text-xs">
                    {exports.map((e) => (
                      <li key={e.id} className="flex items-center gap-2 rounded border border-border bg-surface-2 p-2">
                        <Badge tone={e.verification.ok ? "good" : "bad"}>{e.verification.ok ? "vérifié" : "à vérifier"}</Badge>
                        <a href={editApi.exportUrl(e.id)} className="flex-1 truncate text-violet-300 hover:underline">{e.path.split("/").pop()}</a>
                      </li>
                    ))}
                  </ul>
                </Card>
              </div>
            </div>
          )}
          <ScenarioEditor projectId={id} />
          {sb ? (
            <>
              <StoryboardEditor sb={sb} media={media} onSave={save} saving={saving} />
              <SubtitleEditor projectId={id} sb={sb} onSave={save} />
            </>
          ) : (
            <Card><p className="text-sm text-muted">Importez vos médias, lancez l&apos;analyse, écrivez votre consigne puis générez le storyboard.</p></Card>
          )}
        </section>
      </div>
    </main>
  );
}
