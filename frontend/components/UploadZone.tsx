"use client";
import { useRef, useState } from "react";
import { ACCEPT, api, type Media } from "@/lib/api";

const LABELS: Record<string, string> = {
  video: "Vidéos", audio: "Audio (musique, voix)", image: "Images", script: "Scripts (texte)", reference: "Vidéos de référence",
};

export default function UploadZone({ kind, projectId, onUploaded, compact }: { kind: Media["kind"]; projectId?: number; onUploaded?: (m: Media[]) => void; compact?: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function send(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    setMsg(null);
    const done: Media[] = [];
    const errors: string[] = [];
    for (const f of Array.from(files)) {
      try {
        done.push(...(await api.upload([f], kind, projectId)));
      } catch (e) {
        errors.push(`${f.name} : ${(e as Error).message}`);
      }
    }
    setBusy(false);
    if (done.length) onUploaded?.(done);
    setMsg(errors.length ? { ok: false, text: errors.join("\n") } : { ok: true, text: `${done.length} fichier(s) importé(s).` });
    if (input.current) input.current.value = "";
  }

  return (
    <div>
      <div
        onClick={() => input.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          send(e.dataTransfer.files);
        }}
        className={`cursor-pointer rounded-xl border-2 border-dashed border-border bg-surface-2/50 text-center text-sm text-muted transition hover:border-accent hover:text-foreground ${compact ? "p-3" : "p-6"}`}
      >
        <span className="block font-medium text-foreground">{LABELS[kind]}</span>
        {busy ? "Import et vérification en cours…" : <span className="text-xs">Glissez ou cliquez · {ACCEPT[kind].replaceAll(",", " ")}</span>}
        <input ref={input} type="file" multiple accept={ACCEPT[kind]} className="hidden" onChange={(e) => send(e.target.files)} />
      </div>
      {msg && <p className={`mt-2 whitespace-pre-line text-sm ${msg.ok ? "text-emerald-400" : "text-rose-400"}`}>{msg.text}</p>}
    </div>
  );
}
