"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useRef, useState } from "react";
import { Card } from "@/components/ui";
import { ACCEPT, api, type TargetFormat } from "@/lib/api";

const FORMATS: { value: TargetFormat; label: string }[] = [
  { value: "tiktok", label: "TikTok — 1080×1920" }, { value: "reels", label: "Instagram Reels — 1080×1920" },
  { value: "shorts", label: "YouTube Shorts — 1080×1920" }, { value: "youtube", label: "YouTube — 1920×1080" },
];
const field = "mt-1 w-full rounded-lg border border-border bg-surface-2 px-3 py-2 outline-none focus:border-accent";

function NewProject() {
  const router = useRouter();
  const importMode = useSearchParams().get("import") === "1";
  const files = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [ptype, setPtype] = useState<"2d" | "3d">("2d");
  const [format, setFormat] = useState<TargetFormat>("tiktok");
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null); setBusy(true);
    try {
      const chosen = Array.from(files.current?.files ?? []);
      const p = await api.createProject({ name: name.trim() || chosen[0]?.name.replace(/\.[^.]+$/, "") || "Nouveau projet",
        target_format: format, project_type: ptype, instruction });
      const errors: string[] = [];
      for (const [i, f] of chosen.entries()) {
        setMsg(`Import ${i + 1}/${chosen.length} : ${f.name}…`);
        try { await api.upload([f], "video", p.id); } catch (x) { errors.push(`${f.name} : ${(x as Error).message}`); }
      }
      if (errors.length) { setErr(`Projet créé, mais certains imports ont échoué :\n${errors.join("\n")}`); setBusy(false); return; }
      router.push(`/projects/${p.id}`);
    } catch (x) { setErr((x as Error).message); setBusy(false); }
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-6">
      <h1 className="mb-6 text-2xl font-bold">{importMode ? "Importer une vidéo" : "Nouveau projet"}</h1>
      <Card>
        <form onSubmit={submit} className="space-y-4 text-sm">
          <fieldset>
            <legend className="mb-2 text-muted">Type de projet</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              {([["2d", "Projet 2D", "Montage de vos vidéos, images, voix off et sous-titres."],
                 ["3d", "Projet 3D", "Studio 3D avec personnages animés (en construction)."]] as const).map(([v, t, d]) => (
                <label key={v} className={`cursor-pointer rounded-lg border p-3 ${ptype === v ? "border-accent bg-accent/10" : "border-border"}`}>
                  <input type="radio" name="ptype" value={v} checked={ptype === v} onChange={() => setPtype(v)} className="mr-2 accent-violet-500" />
                  <b>{t}</b><span className="mt-1 block text-xs text-muted">{d}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <label className="block">Nom du projet<input value={name} onChange={(e) => setName(e.target.value)} maxLength={200} placeholder="Ex. : 3 astuces pour apprendre" className={field} /></label>
          <label className="block">Format de sortie<select value={format} onChange={(e) => setFormat(e.target.value as TargetFormat)} className={field}>
            {FORMATS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}</select></label>
          <label className="block">Consigne de montage (facultatif)
            <textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} rows={3} maxLength={5000} className={field}
              placeholder="Ex. : TikTok éducatif de 60 s, sous-titres animés, zooms, musique discrète." /></label>
          {ptype === "2d" && (
            <label className="block">Vidéos à importer {importMode ? "" : "(facultatif)"}
              <input ref={files} type="file" multiple accept={ACCEPT.video} required={importMode} className={`${field} file:mr-3 file:rounded file:border-0 file:bg-accent file:px-3 file:py-1 file:text-white`} />
              <span className="mt-1 block text-xs text-muted">MP4, MOV ou AVI. Musiques, images et scripts s&apos;ajoutent ensuite dans le projet.</span>
            </label>
          )}
          {msg && busy && <p className="text-muted">{msg}</p>}
          {err && <p className="whitespace-pre-line text-rose-400">{err}</p>}
          <button disabled={busy} className="w-full rounded-lg bg-accent px-4 py-2 font-medium text-white disabled:opacity-50">{busy ? "Création…" : "Créer le projet"}</button>
        </form>
      </Card>
    </main>
  );
}

export default function Page() {
  return <Suspense><NewProject /></Suspense>;
}
