"use client";
import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Badge, Card, ConfidenceBadge, Swatch } from "@/components/ui";
import { LABELS, styleApi, type Style, type StyleRule } from "@/lib/api";

type Tab = "apercu" | "guide" | "json";

function RulesTable({ rules }: { rules: StyleRule[] }) {
  if (!rules.length) return <p className="text-sm text-muted">Aucun.</p>;
  return (
    <ul className="space-y-2">
      {rules.map((r) => (
        <li key={r.key} className="rounded-lg border border-border bg-surface-2 p-3 text-sm">
          <div className="mb-1 flex flex-wrap items-center gap-2"><b>{r.label}</b><ConfidenceBadge value={r.confidence} /></div>
          <div>{r.value}</div>
          <div className="mt-1 text-xs text-muted">Méthode : {r.source}</div>
        </li>
      ))}
    </ul>
  );
}

export default function StylePage({ params }: { params: Promise<{ id: string }> }) {
  const id = Number(use(params).id);
  const [s, setS] = useState<Style | null>(null);
  const [tab, setTab] = useState<Tab>("apercu");
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  // champs modifiables
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [font, setFont] = useState("");
  const [subColor, setSubColor] = useState("#FFFFFF");
  const [outColor, setOutColor] = useState("#000000");
  const [position, setPosition] = useState("bas");
  const [transition, setTransition] = useState("cut");
  const [zoom, setZoom] = useState(false);

  const hydrate = useCallback((x: Style) => {
    setS(x);
    setName(x.name);
    setNotes(x.user_notes);
    setFont(x.config.subtitles.font?.family ?? "");
    setSubColor(x.config.subtitles.primary_color ?? "#FFFFFF");
    setOutColor(x.config.subtitles.outline_color ?? "#000000");
    setPosition(x.config.subtitles.position ?? "bas");
    setTransition(x.config.transitions.default);
    setZoom(x.config.motion.zoom.enabled);
  }, []);

  useEffect(() => { styleApi.get(id).then(hydrate).catch((e) => setErr(e.message)); }, [id, hydrate]);

  async function act(fn: () => Promise<Style>, ok: string) {
    setErr(null);
    setInfo(null);
    try {
      hydrate(await fn());
      setInfo(ok);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  function save() {
    if (!s) return;
    const sub = s.config.subtitles;
    return act(() => styleApi.update(id, {
      name, user_notes: notes,
      config_patch: {
        subtitles: sub.enabled ? { font: { family: font.trim() || null }, primary_color: subColor.toUpperCase(), outline_color: outColor.toUpperCase(), position } : { font: { family: font.trim() || null } },
        transitions: { default: transition },
        motion: { zoom: { enabled: zoom } },
      },
    }), "Modifications enregistrées. Le style doit être (re)validé.");
  }

  if (err && !s) return <main className="mx-auto max-w-6xl px-4 py-6"><p className="text-rose-400">{err}</p></main>;
  if (!s) return <main className="mx-auto max-w-6xl px-4 py-6"><p className="text-muted">Chargement…</p></main>;
  const c = s.config;

  return (
    <main className="mx-auto max-w-6xl px-4 py-6">
      
      <Link href="/references" className="text-sm text-muted hover:text-foreground">← Références &amp; styles</Link>
      <div className="mb-4 mt-2 flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">{s.name}</h1>
        <Badge tone={s.status === "validated" ? "good" : s.status === "rejected" ? "bad" : "warn"}>
          {s.status === "validated" ? "validé" : s.status === "rejected" ? "rejeté" : "brouillon"}
        </Badge>
        {s.is_official && <Badge tone="accent">★ style officiel</Badge>}
      </div>

      {s.status === "draft" && (
        <div className="mb-4 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-100">
          Ce style est un <b>brouillon</b>. Vérifiez les règles ci-dessous, ajustez-les si besoin, puis validez-le pour en faire le style officiel utilisé par le moteur de montage.
        </div>
      )}
      {err && <p className="mb-4 rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200">{err}</p>}
      {info && <p className="mb-4 rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm text-emerald-200">{info}</p>}

      <div className="grid gap-6 lg:grid-cols-3 [&>*]:min-w-0">
        <div className="lg:col-span-2">
          <div className="mb-3 flex gap-2 text-sm">
            {([["apercu", "Aperçu"], ["guide", "STYLE-GUIDE.md"], ["json", "Configuration JSON"]] as [Tab, string][]).map(([k, l]) => (
              <button key={k} onClick={() => setTab(k)} className={`rounded-lg px-3 py-1.5 ${tab === k ? "bg-accent" : "bg-surface-2 text-muted hover:text-foreground"}`}>{l}</button>
            ))}
          </div>
          {tab === "apercu" && (
            <div className="space-y-6">
              <Card title={`Éléments obligatoires (${s.summary.mandatory.length})`}><RulesTable rules={s.summary.mandatory} /></Card>
              <Card title={`Éléments facultatifs (${s.summary.optional.length})`}><RulesTable rules={s.summary.optional} /></Card>
              <Card title="Palette">
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">{c.color.palette.map((p) => <Swatch key={p.hex} hex={p.hex} share={p.share} />)}</div>
              </Card>
              <Card title={`Caractéristiques propres à chaque scène (${s.summary.per_scene.length})`}>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="text-muted"><tr><th className="py-1">Réf.</th><th>Plan</th><th>Durée</th><th>Entrée</th><th>Mouvement</th><th>Couleur</th></tr></thead>
                    <tbody>
                      {s.summary.per_scene.map((p, i) => (
                        <tr key={i} className="border-t border-border">
                          <td className="py-1 pr-2">{String(p.ref)}</td><td>{p.index}</td><td>{p.duration} s</td><td>{String(p.transition_in)}</td><td>{String(p.motion)}</td>
                          <td><span className="inline-block h-3 w-5 rounded-sm align-middle" style={{ background: String(p.dominant_color) }} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
              <Card title="Limites"><ul className="list-disc space-y-1 pl-5 text-sm text-muted">{s.summary.limits.map((l) => <li key={l}>{l}</li>)}</ul></Card>
            </div>
          )}
          {tab === "guide" && (
            <Card>
              <article className="markdown text-sm">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{s.markdown}</ReactMarkdown>
              </article>
            </Card>
          )}
          {tab === "json" && (
            <Card><pre className="max-h-[70vh] overflow-auto text-xs">{JSON.stringify(c, null, 2)}</pre></Card>
          )}
        </div>

        <aside className="space-y-6">
          <Card title="Ajuster le style">
            <div className="space-y-3 text-sm">
              <label className="block">Nom
                <input value={name} onChange={(e) => setName(e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-surface-2 px-3 py-2" />
              </label>
              <label className="block">Police des sous-titres {!font && c.subtitles.enabled && <Badge tone="warn">à choisir</Badge>}
                <input list="fonts" value={font} onChange={(e) => setFont(e.target.value)} placeholder="Non identifiée — choisissez"
                  className="mt-1 w-full rounded-lg border border-border bg-surface-2 px-3 py-2" />
                <datalist id="fonts">{(c.subtitles.font?.suggestions ?? []).map((f) => <option key={f} value={f} />)}</datalist>
                <span className="text-xs text-muted">La police n&apos;a pas pu être reconnue automatiquement.</span>
              </label>
              {c.subtitles.enabled && (
                <>
                  <div className="flex gap-3">
                    <label className="flex-1">Texte<input type="color" value={subColor} onChange={(e) => setSubColor(e.target.value)} className="mt-1 block h-9 w-full rounded bg-surface-2" /></label>
                    <label className="flex-1">Contour<input type="color" value={outColor} onChange={(e) => setOutColor(e.target.value)} className="mt-1 block h-9 w-full rounded bg-surface-2" /></label>
                  </div>
                  <label className="block">Position
                    <select value={position} onChange={(e) => setPosition(e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-surface-2 px-3 py-2">
                      <option value="haut">Haut</option><option value="centre">Centre</option><option value="bas">Bas</option>
                    </select>
                  </label>
                </>
              )}
              <label className="block">Transition par défaut
                <select value={transition} onChange={(e) => setTransition(e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-surface-2 px-3 py-2">
                  {["cut", "crossfade", "fade_black", "flash_white"].map((t) => <option key={t} value={t}>{LABELS[t]}</option>)}
                </select>
              </label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={zoom} onChange={(e) => setZoom(e.target.checked)} className="accent-violet-500" /> Zooms progressifs</label>
              <label className="block">Notes
                <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} className="mt-1 w-full rounded-lg border border-border bg-surface-2 p-2" />
              </label>
              <button onClick={save} className="w-full rounded-lg border border-border px-4 py-2 hover:border-accent">Enregistrer les modifications</button>
            </div>
          </Card>
          <Card title="Validation">
            <p className="mb-3 text-sm text-muted">Valider enregistre <code>style.json</code> et <code>STYLE-GUIDE.md</code> et en fait le style officiel.</p>
            <div className="flex gap-2">
              <button onClick={() => act(() => styleApi.validate(id), "Style validé et enregistré comme style officiel.")} disabled={s.status === "validated"}
                className="flex-1 rounded-lg bg-emerald-600 px-4 py-2 font-medium hover:brightness-110 disabled:opacity-40">Valider</button>
              <button onClick={() => act(() => styleApi.reject(id), "Style rejeté.")} disabled={s.status === "rejected"}
                className="rounded-lg border border-rose-500/50 px-4 py-2 text-rose-300 hover:bg-rose-500/10 disabled:opacity-40">Rejeter</button>
            </div>
            {s.files_dir && s.status === "validated" && <p className="mt-2 text-xs text-muted">Fichiers : {s.files_dir}/</p>}
          </Card>
        </aside>
      </div>
    </main>
  );
}
