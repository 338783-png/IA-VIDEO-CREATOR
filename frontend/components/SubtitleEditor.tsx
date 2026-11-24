"use client";
import { useEffect, useState } from "react";
import { Badge, Card } from "@/components/ui";
import { subApi, type Cue, type StoryboardData, type StoryboardOut, type SubtitlesOut } from "@/lib/api";

const fmt = (t: number) => `${Math.floor(t / 60)}:${(t % 60).toFixed(2).padStart(5, "0")}`;

export default function SubtitleEditor({ projectId, sb, onSave }: {
  projectId: number; sb: StoryboardOut;
  onSave: (data: Partial<StoryboardData> & { base_version: number }) => void;
}) {
  const [data, setData] = useState<SubtitlesOut | null>(null);
  const [cues, setCues] = useState<Cue[]>([]);
  const [dirty, setDirty] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    subApi.get(projectId).then((d) => { setData(d); setCues(d.cues.map(({ start, end, text }) => ({ start, end, text }))); setDirty(false); })
      .catch((e) => setErr(e.message));
  }, [projectId, sb.version]);

  if (!sb.data.subtitles.enabled) return null;
  const edit = (i: number, p: Partial<Cue>) => { setCues((c) => c.map((x, k) => (k === i ? { ...x, ...p } : x))); setDirty(true); };
  const save = (manual: Cue[] | null) =>
    onSave({ base_version: sb.version, scenes: sb.data.scenes, subtitles: { ...sb.data.subtitles, manual_cues: manual } });

  return (
    <Card title={<span className="flex flex-wrap items-center gap-2">Sous-titres
      {data && <Badge tone={data.manual ? "warn" : "good"}>{data.manual ? "modifiés à la main" : "automatiques"}</Badge>}
      {data?.sync.max_offset_ms != null && <Badge tone={data.sync.ok ? "good" : "bad"}>synchro ±{data.sync.max_offset_ms} ms</Badge>}
      <a href={subApi.fileUrl(projectId, "srt")} className="ml-auto text-xs text-violet-300 hover:underline">⬇ SRT</a>
      <a href={subApi.fileUrl(projectId, "vtt")} className="text-xs text-violet-300 hover:underline">⬇ VTT</a></span>}>
      {err && <p className="text-sm text-rose-400">{err}</p>}
      <div className="max-h-80 overflow-y-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-surface text-muted"><tr><th className="w-20 py-1">Début (s)</th><th className="w-20">Fin (s)</th><th>Texte</th></tr></thead>
          <tbody>
            {cues.map((c, i) => (
              <tr key={i} className="border-t border-border">
                <td className="py-1 pr-1"><input type="number" step="0.05" value={c.start} onChange={(e) => edit(i, { start: +e.target.value })} title={fmt(c.start)}
                  className="w-full rounded border border-border bg-surface-2 px-1" /></td>
                <td className="pr-1"><input type="number" step="0.05" value={c.end} onChange={(e) => edit(i, { end: +e.target.value })} title={fmt(c.end)}
                  className="w-full rounded border border-border bg-surface-2 px-1" /></td>
                <td><input value={c.text} onChange={(e) => edit(i, { text: e.target.value })} className="w-full rounded border border-border bg-surface-2 px-1" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[11px] text-muted">Videz un texte pour supprimer le sous-titre. Les sous-titres modifiés à la main remplacent la synchronisation automatique.</p>
      <div className="mt-2 flex gap-2">
        <button disabled={!dirty} onClick={() => save(cues)} className="rounded-lg bg-accent px-3 py-1.5 text-sm disabled:opacity-40">Enregistrer les sous-titres</button>
        {data?.manual && <button onClick={() => save(null)} className="rounded-lg border border-border px-3 py-1.5 text-sm hover:border-accent">Revenir à l&apos;automatique</button>}
      </div>
    </Card>
  );
}
