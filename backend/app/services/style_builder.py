"""Synthèse d'un style à partir d'une ou plusieurs analyses de référence.

Règle de classement :
- OBLIGATOIRE : caractéristique présente dans toutes les références (ou ≥ 60 % des plans s'il n'y en a qu'une)
  et suffisamment cohérente.
- FACULTATIF : présente dans une partie des références/plans (≥ 15 %).
- PROPRE À UNE SCÈNE : particularité d'un plan, documentée mais non imposée.
Les éléments à confiance « faible » ne sont jamais obligatoires.
"""
from datetime import datetime, timezone

import numpy as np

from app.services.analysis.colors import kmeans, to_hex
from app.services.analysis.motion import MOTION_LABELS
from app.services.analysis.scenes import TRANSITION_LABELS

CONFIG_VERSION = 1
FORMATS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}
FONT_SUGGESTIONS = ["Montserrat ExtraBold", "Poppins Bold", "Anton", "Bebas Neue"]  # polices libres (OFL)


def _r(x, n=2):
    return None if x is None else round(float(x), n)


def _rule(key: str, label: str, value, source: str, confidence: str) -> dict:
    return {"key": key, "label": label, "value": value, "source": source, "confidence": confidence}


def _hex_to_rgb(h: str) -> np.ndarray:
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], np.float32)


def _merge_palettes(analyses: list[dict], k: int = 6) -> list[dict]:
    pts, weights = [], []
    for a in analyses:
        for p in a["colors"]["palette"]:
            pts.append(_hex_to_rgb(p["hex"]))
            weights.append(p["share"])
    if not pts:
        return []
    # pondération par répétition proportionnelle à la part
    rep = np.concatenate([np.repeat(p[None], max(1, int(w * 100)), 0) for p, w in zip(pts, weights)])
    c, s = kmeans(rep, min(k, len(pts)))
    return [{"hex": to_hex(cc), "share": round(float(ss), 3)} for cc, ss in zip(c, s) if ss >= 0.03]


def build(analyses: list[dict], name: str) -> dict:
    if not analyses:
        raise ValueError("Aucune analyse fournie")
    n_ref = len(analyses)
    scenes = [sc | {"ref": a["media"]["name"]} for a in analyses for sc in a["scenes"]]
    n_sc = len(scenes)
    mandatory, optional, per_scene = [], [], []

    def classify(share_refs: float, share_scenes: float, conf: str = "moyenne") -> str | None:
        strong = share_refs >= 0.999 if n_ref > 1 else share_scenes >= 0.6
        if strong and conf != "faible":
            return "mandatory"
        if share_refs > 0 and (share_scenes >= 0.15 or n_ref > 1):
            return "optional"
        return None

    def put(where, rule):
        (mandatory if where == "mandatory" else optional).append(rule) if where else None

    # --- Format --------------------------------------------------------------------------------
    aspects = [a["format"]["aspect"] for a in analyses]
    aspect = max(set(aspects), key=aspects.count)
    fps_vals = [a["format"]["fps"] for a in analyses]
    fps = int(round(float(np.median(fps_vals)))) if fps_vals else 30
    fps = 30 if fps in (29, 30) else 60 if fps in (59, 60) else fps
    w, h = FORMATS.get(aspect, (1080, 1920))
    put("mandatory" if aspects.count(aspect) == n_ref else "optional",
        _rule("format", "Format d'image", f"{aspect} ({w}×{h}), {fps} i/s", "métadonnées FFmpeg", "élevée"))

    # --- Rythme --------------------------------------------------------------------------------
    avgs = np.array([a["rhythm"]["avg_shot"] for a in analyses])
    durs = np.array([sc["duration"] for sc in scenes])
    cv = float(avgs.std() / avgs.mean()) if n_ref > 1 and avgs.mean() else 0.0
    target = float(np.median(durs))
    lo, hi = float(np.percentile(durs, 10)), float(np.percentile(durs, 90))
    rhythm = {
        "target_shot_duration": _r(target), "min_shot": _r(max(0.4, lo)), "max_shot": _r(hi),
        "avg_shot": _r(durs.mean()), "cuts_per_minute": _r(np.mean([a["rhythm"]["cuts_per_minute"] or 0 for a in analyses]), 1),
        "pace": analyses[0]["rhythm"]["pace"] if n_ref == 1 else max(set(x["rhythm"]["pace"] for x in analyses), key=[x["rhythm"]["pace"] for x in analyses].count),
        "trend": analyses[0]["rhythm"].get("trend"),
    }
    put("mandatory" if cv < 0.35 else "optional",
        _rule("rhythm", "Durée des plans", f"≈ {rhythm['target_shot_duration']} s (entre {rhythm['min_shot']} et {rhythm['max_shot']} s), rythme {rhythm['pace']}",
              "détection des coupes", "élevée" if cv < 0.35 else "moyenne"))

    # --- Transitions ---------------------------------------------------------------------------
    tcounts: dict[str, int] = {}
    tdur: dict[str, list] = {}
    for sc in scenes:
        t = sc["transition_in"]
        if t:
            tcounts[t["type"]] = tcounts.get(t["type"], 0) + 1
            tdur.setdefault(t["type"], []).append(t["duration"])
    total_t = sum(tcounts.values()) or 1
    dist = {k: round(v / total_t, 2) for k, v in sorted(tcounts.items(), key=lambda x: -x[1])}
    default_t = next(iter(dist), "cut")
    refs_with = {k: sum(1 for a in analyses if a["transitions"]["counts"].get(k)) / n_ref for k in dist}
    for k, share in dist.items():
        label = TRANSITION_LABELS.get(k, k)
        d = _r(np.median(tdur[k])) if k != "cut" else 0
        conf = "faible" if k == "animated" else "élevée" if k in ("cut", "fade_black") else "moyenne"
        txt = f"{label} — {round(share * 100)} % des transitions" + (f", durée ≈ {d} s" if d else "")
        if k == default_t and share >= 0.6:
            put(classify(refs_with[k], 1.0, conf), _rule(f"transition_{k}", "Transition principale", txt, "analyse image par image", conf))
        else:
            put("optional" if share >= 0.1 or refs_with[k] > 0 else None, _rule(f"transition_{k}", "Transition", txt, "analyse image par image", conf))
    transitions = {"default": default_t, "distribution": dist,
                   "durations": {k: _r(np.median(v)) for k, v in tdur.items() if k != "cut"}}

    # --- Mouvements / animations ---------------------------------------------------------------
    mcounts: dict[str, int] = {}
    for sc in scenes:
        mcounts[sc["motion"]["type"]] = mcounts.get(sc["motion"]["type"], 0) + 1
    zoom_sc = [sc["motion"] for sc in scenes if sc["motion"]["type"] in ("zoom_avant", "zoom_arriere")]
    zoom_share = len(zoom_sc) / n_sc
    zin = sum(1 for z in zoom_sc if z["type"] == "zoom_avant")
    zoom_cfg = {
        "enabled": bool(zoom_sc), "probability": _r(zoom_share),
        "direction": "in" if zin >= len(zoom_sc) - zin else "out",
        "scale_per_second": _r(np.median([abs(z["zoom_per_second"]) for z in zoom_sc]), 4) if zoom_sc else 0.0,
        "max_scale": _r(max([max(z["zoom_total"], 1 / z["zoom_total"]) for z in zoom_sc]), 3) if zoom_sc else 1.0,
    }
    if zoom_sc:
        refs_zoom = sum(1 for a in analyses if any(s["motion"]["type"].startswith("zoom") for s in a["scenes"])) / n_ref
        put(classify(refs_zoom, zoom_share, "moyenne"),
            _rule("zoom", "Zooms", f"{'avant' if zoom_cfg['direction'] == 'in' else 'arrière'} progressif sur {round(zoom_share * 100)} % des plans, "
                  f"≈ +{round(zoom_cfg["scale_per_second"] * 100)} %/s, jusqu'à ×{zoom_cfg['max_scale']}", "estimation d'échelle entre images", "moyenne"))
    pan_sc = [sc for sc in scenes if sc["motion"]["type"] == "panoramique"]
    if pan_sc:
        put(classify(sum(1 for a in analyses if any(s["motion"]["type"] == "panoramique" for s in a["scenes"])) / n_ref, len(pan_sc) / n_sc, "moyenne"),
            _rule("pan", "Panoramiques / glissements", f"{len(pan_sc)} plan(s) sur {n_sc}", "corrélation de phase", "moyenne"))
    shake = mcounts.get("tremblement", 0)
    if shake:
        put("optional", _rule("shake", "Caméra à l'épaule / tremblement", f"{shake} plan(s)", "variance du déplacement", "faible"))
    static_share = mcounts.get("statique", 0) / n_sc
    motion_cfg = {"zoom": zoom_cfg, "pan": {"enabled": bool(pan_sc), "probability": _r(len(pan_sc) / n_sc)},
                  "static_share": _r(static_share), "distribution": {k: _r(v / n_sc) for k, v in mcounts.items()}}

    # --- Couleurs ------------------------------------------------------------------------------
    pal = _merge_palettes(analyses)
    st = {k: _r(np.mean([a["colors"]["stats"][k] for a in analyses]), 3) for k in ("brightness", "contrast", "saturation", "warmth")}
    temps = [a["colors"]["stats"]["temperature"] for a in analyses]
    st["temperature"] = max(set(temps), key=temps.count)
    br_std = float(np.std([sc["color_stats"]["brightness"] for sc in scenes]))
    sat_std = float(np.std([sc["color_stats"]["saturation"] for sc in scenes]))
    consistent = br_std < 0.12 and sat_std < 0.12
    put("mandatory" if consistent and (n_ref == 1 or temps.count(st["temperature"]) == n_ref) else "optional",
        _rule("grading", "Étalonnage", f"luminosité {st['brightness']}, saturation {st['saturation']}, contraste {st['contrast']}, tonalité {st['temperature']}",
              "statistiques de pixels", "moyenne" if consistent else "faible"))
    put("optional", _rule("palette", "Palette d'accent (graphismes, textes)", " ".join(p["hex"] for p in pal[:5]), "k-means sur les images", "moyenne"))
    colors_cfg = {"palette": pal, "grading": st, "consistent_across_scenes": consistent}

    # --- Sous-titres ---------------------------------------------------------------------------
    caps = [a["captions"] for a in analyses]
    det = [c for c in caps if c.get("detected")]
    if det:
        pos = [c["position"] for c in det]
        position = max(set(pos), key=pos.count)
        fills = [c["fill_color"] for c in det if c.get("fill_color")]
        outl = [c["outline_color"] for c in det if c.get("outline_color")]
        intervals = [c["change_interval_s"] for c in det if c.get("change_interval_s")]
        conf = "moyenne" if all(c["confidence"] != "faible" for c in det) else "faible"
        sub_cfg = {
            "enabled": True, "position": position,
            "vertical_center_pct": _r(np.median([c["vertical_center_pct"] for c in det]), 1),
            "max_width_pct": _r(max(c.get("avg_width_pct") or 0 for c in det) * 1.4 or 80, 0),
            "primary_color": fills[0] if fills else "#FFFFFF",
            "outline_color": outl[0] if outl else "#000000",
            "outline": bool(outl),
            "update_interval_s": _r(np.median(intervals)) if intervals else None,
            "mode": "word" if intervals and np.median(intervals) < 0.6 else "phrase" if intervals and np.median(intervals) > 1.6 else "chunk",
            "uppercase": None,
            "font": {"family": None, "detected": False, "suggestions": FONT_SUGGESTIONS,
                     "note": "Police non identifiée : à choisir avant validation."},
            "confidence": conf,
        }
        put(classify(len(det) / n_ref, 1.0, conf),
            _rule("subtitles", "Sous-titres incrustés",
                  f"position {position} (≈ {sub_cfg['vertical_center_pct']} % de la hauteur), texte {sub_cfg['primary_color']}"
                  + (f" contour {sub_cfg['outline_color']}" if outl else "") + f", {det[0]['mode']}", "heuristique image", conf))
    else:
        sub_cfg = {"enabled": False, "note": "Aucun sous-titre incrusté détecté dans les références.", "confidence": "moyenne",
                   "font": {"family": None, "detected": False, "suggestions": FONT_SUGGESTIONS}}

    # --- Audio et synchronisation --------------------------------------------------------------
    auds = [a["audio"] for a in analyses if a["audio"].get("has_audio")]
    audio_cfg: dict = {"has_reference_audio": bool(auds)}
    sync_cfg: dict = {"cut_on_beat": False, "tolerance_ms": 80}
    if auds:
        music = [x for x in auds if x["music"]["likely"]]
        bpms = [x["tempo_bpm"] for x in auds if x.get("tempo_bpm")]
        lufs = [x["loudness_lufs"] for x in auds if x.get("loudness_lufs") is not None]
        on_beat = [x["sync"]["cuts_on_beat_ratio"] for x in auds if x["sync"].get("cuts_on_beat_ratio") is not None]
        sfx = [x["sound_effects"]["on_cuts_ratio"] for x in auds if x["sound_effects"].get("on_cuts_ratio") is not None]
        audio_cfg |= {
            "music": {"enabled": bool(music), "bpm": _r(np.median(bpms), 0) if bpms else None, "ducking_under_voice": True},
            "target_lufs": -14.0,
            "reference_lufs": _r(np.median(lufs), 1) if lufs else None,
            "sfx_on_cuts": bool(sfx) and float(np.median(sfx)) > 0.5,
            "silence_ratio": _r(np.mean([x["silence_ratio"] for x in auds]), 3),
        }
        if music:
            put(classify(len(music) / n_ref, 1.0, "moyenne"),
                _rule("music", "Fond musical", f"musique rythmée ≈ {audio_cfg['music']['bpm']} BPM", "autocorrélation des attaques", music[0]["music"]["confidence"]))
        if on_beat and float(np.median(on_beat)) >= 0.6:
            sync_cfg["cut_on_beat"] = True
            put(classify(sum(1 for r in on_beat if r >= 0.6) / n_ref, 1.0, "moyenne"),
                _rule("cut_on_beat", "Coupes sur le temps", f"{int(np.median(on_beat) * 100)} % des coupes à ±80 ms d'un temps musical", "grille de tempo", "moyenne"))
        if audio_cfg["sfx_on_cuts"]:
            put("optional", _rule("sfx", "Effets sonores aux coupes", "attaque sonore marquée à chaque coupe (whoosh/impact)", "attaques audio", "faible"))
        put("mandatory", _rule("loudness", "Volume final", "normalisation à -14 LUFS (standard des plateformes)", "recommandation plateforme", "élevée"))
    sync_cfg["subtitle_sync"] = "mot à mot sur la voix (timestamps Whisper)" if sub_cfg.get("mode") == "word" else "par segment de phrase"

    # --- Par scène -----------------------------------------------------------------------------
    for sc in scenes:
        t = sc["transition_in"]
        per_scene.append({
            "ref": sc["ref"], "index": sc["index"], "start": sc["start"], "duration": sc["duration"],
            "transition_in": TRANSITION_LABELS.get(t["type"], t["type"]) if t else "début",
            "motion": MOTION_LABELS.get(sc["motion"]["type"], sc["motion"]["type"]),
            "dominant_color": sc["palette"][0]["hex"] if sc["palette"] else None,
            "keyframe": sc["keyframe"],
        })

    limits = sorted({lim for a in analyses for lim in a.get("limits", [])})
    vision_used = [a["vision"]["model"] for a in analyses if a.get("vision", {}).get("available")]

    config = {
        "version": CONFIG_VERSION, "name": name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provenance": {"reference_media_ids": [a["media"]["id"] for a in analyses], "vision_model": vision_used[0] if vision_used else None,
                       "note": "Seules des mesures sont conservées ; aucun contenu des références n'est réutilisé."},
        "format": {"aspect": aspect, "width": w, "height": h, "fps": fps},
        "rhythm": rhythm, "transitions": transitions, "motion": motion_cfg, "color": colors_cfg,
        "subtitles": sub_cfg, "audio": audio_cfg, "sync": sync_cfg,
        "rules": {"mandatory": [r["key"] for r in mandatory], "optional": [r["key"] for r in optional]},
    }
    summary = {"mandatory": mandatory, "optional": optional, "per_scene": per_scene, "limits": limits,
               "reference_count": n_ref, "scene_count": n_sc}
    return {"summary": summary, "config": config}


# --------------------------------------------------------------------------------------------------
def render_markdown(name: str, status: str, summary: dict, config: dict, user_notes: str = "") -> str:
    c = config
    L = [f"# STYLE-GUIDE — {name}", ""]
    L += [f"> Statut : **{'VALIDÉ (style officiel)' if status == 'validated' else 'BROUILLON — en attente de validation' if status == 'draft' else 'REJETÉ'}**  ",
          f"> Généré le {c['generated_at'][:16].replace('T', ' ')} UTC à partir de {summary['reference_count']} vidéo(s) de référence "
          f"({summary['scene_count']} plans analysés).  ",
          "> Les références servent uniquement de modèle : aucune image, son ou texte n'en est copié.", ""]

    def rules(title, items):
        out = [f"## {title}", ""]
        if not items:
            return out + ["_Aucun._", ""]
        out += ["| Élément | Règle | Confiance | Méthode |", "|---|---|---|---|"]
        out += [f"| {r['label']} | {r['value']} | {r['confidence']} | {r['source']} |" for r in items]
        return out + [""]

    L += rules("Éléments obligatoires", summary["mandatory"])
    L += rules("Éléments facultatifs", summary["optional"])

    f = c["format"]
    L += ["## Format", "", f"- Ratio {f['aspect']}, export {f['width']}×{f['height']}, {f['fps']} images/s.", ""]

    col = c["color"]
    L += ["## Palette de couleurs", "", "| Couleur | Part de l'image |", "|---|---|"]
    L += [f"| `{p['hex']}` | {round(p["share"] * 100)} % |" for p in col["palette"]]
    g = col["grading"]
    L += ["", f"Étalonnage cible : luminosité {g['brightness']}, contraste {g['contrast']}, saturation {g['saturation']}, tonalité {g['temperature']}."
          + ("" if col["consistent_across_scenes"] else " _Étalonnage variable d'un plan à l'autre : règle indicative._"), ""]

    s = c["subtitles"]
    L += ["## Polices", ""]
    fam = (s.get("font") or {}).get("family")
    if fam:
        L += [f"- Police choisie : **{fam}** (choix utilisateur)."]
    else:
        L += ["- **Police non identifiée.** L'analyse d'image ne permet pas de reconnaître une police de façon fiable.",
              f"- Suggestions de polices libres de style proche : {', '.join(FONT_SUGGESTIONS)} (à choisir)."]
    L += [""]

    L += ["## Règles de sous-titrage", ""]
    if s.get("enabled"):
        L += [f"- Position : **{s['position']}**, centre vertical ≈ {s['vertical_center_pct']} % de la hauteur, largeur max ≈ {s['max_width_pct']} %.",
              f"- Couleur du texte : `{s['primary_color']}`" + (f", contour `{s['outline_color']}`." if s.get("outline") else "."),
              f"- Découpage : **{ {'word': 'mot par mot', 'chunk': 'groupes de 2 à 4 mots', 'phrase': 'phrases complètes'}[s['mode']] }**"
              + (f", un changement toutes les ≈ {s['update_interval_s']} s." if s.get("update_interval_s") else "."),
              f"- Confiance : {s['confidence']} (heuristique ; majuscules/fond non déterminés).", ""]
    else:
        L += [f"- {s.get('note', 'Pas de sous-titres.')}", ""]

    t = c["transitions"]
    L += ["## Transitions", "", f"- Transition par défaut : **{TRANSITION_LABELS.get(t['default'], t['default'])}**."]
    for k, v in t["distribution"].items():
        d = t["durations"].get(k)
        L += [f"- {TRANSITION_LABELS.get(k, k)} : {round(v * 100)} %" + (f" (durée ≈ {d} s)" if d else "")]
    L += [""]

    m = c["motion"]
    z = m["zoom"]
    L += ["## Animations", ""]
    L += [f"- Zoom {'avant' if z['direction'] == 'in' else 'arrière'} : {round((z['probability'] or 0) * 100)} % des plans, ≈ +{round(z['scale_per_second'] * 100, 1)} % par seconde, jusqu'à ×{z['max_scale']}."
          if z["enabled"] else "- Pas de zoom détecté."]
    L += [f"- Panoramiques : {round((m['pan']['probability'] or 0) * 100)} % des plans." if m["pan"]["enabled"] else "- Pas de panoramique détecté."]
    L += [f"- Plans fixes : {round((m['static_share'] or 0) * 100)} %.", ""]

    a = c["audio"]
    L += ["## Effets", ""]
    if a.get("has_reference_audio"):
        L += [f"- Effets sonores aux coupes : {'oui (probable)' if a.get('sfx_on_cuts') else 'non systématiques'}."]
    L += ["- Effets visuels spécifiques (particules, emojis, overlays) : non détectés automatiquement"
          + (" ; voir descriptions du modèle de vision." if c["provenance"].get("vision_model") else " (aucun modèle de vision installé)."), ""]

    r = c["rhythm"]
    L += ["## Rythme", "", f"- Durée cible d'un plan : **{r['target_shot_duration']} s** (de {r['min_shot']} à {r['max_shot']} s).",
          f"- ≈ {r['cuts_per_minute']} coupes par minute — rythme **{r['pace']}**" + (f", tendance : {r['trend']}." if r.get("trend") else "."), ""]

    sy = c["sync"]
    L += ["## Règles de synchronisation", ""]
    if a.get("has_reference_audio") and a.get("music", {}).get("enabled"):
        L += [f"- Musique de fond ≈ {a['music']['bpm']} BPM, baissée automatiquement sous la voix."]
    L += [f"- Coupes calées sur les temps musicaux (tolérance {sy['tolerance_ms']} ms)." if sy["cut_on_beat"] else "- Coupes libres (non calées sur la musique)."]
    L += [f"- Sous-titres : {sy['subtitle_sync']}.", f"- Volume final normalisé à {a.get('target_lufs', -14)} LUFS." if a.get("has_reference_audio") else "", ""]

    L += ["## Caractéristiques propres à chaque scène", "", "_Documentées pour information, non imposées au montage._", "",
          "| Référence | Plan | Début | Durée | Entrée | Mouvement | Couleur dominante |", "|---|---|---|---|---|---|---|"]
    L += [f"| {p['ref']} | {p['index']} | {p['start']} s | {p['duration']} s | {p['transition_in']} | {p['motion']} | `{p['dominant_color']}` |"
          for p in summary["per_scene"]]
    L += ["", "## Limites de l'analyse", ""] + [f"- {x}" for x in summary["limits"]] + [""]
    if (user_notes or "").strip():
        L += ["## Notes de l'utilisateur", "", user_notes.strip(), ""]
    return "\n".join(L)
