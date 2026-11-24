"""Analyse complète d'une vidéo de référence -> métriques de style (aucune copie du contenu)."""
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.core.config import settings
from app.services import ffmpeg_service
from app.services.analysis import audio as audio_mod
from app.services.analysis import captions as captions_mod
from app.services.analysis import colors as colors_mod
from app.services.analysis import motion as motion_mod
from app.services.analysis import scenes as scenes_mod
from app.services.analysis import vision as vision_mod
from app.services.analysis.decode import analysis_size, gray, iter_frames, read_audio
from app.services.jobs import JobContext

ANALYSIS_VERSION = 1


def aspect_label(w: int, h: int) -> str:
    r = w / h
    for label, v in {"9:16": 9 / 16, "3:4": 3 / 4, "4:5": 4 / 5, "1:1": 1, "4:3": 4 / 3, "16:9": 16 / 9, "21:9": 21 / 9}.items():
        if abs(r - v) / v < 0.03:
            return label
    return f"{w}:{h}"


def pace_label(avg: float) -> str:
    return "très rapide" if avg < 1.5 else "rapide" if avg < 3 else "modéré" if avg < 6 else "lent"


def keyframes_dir(media_id: int) -> Path:
    return settings.storage_dir / "thumbnails" / f"ref_{media_id}"


def extract_keyframe(src: Path, t: float, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([settings.ffmpeg_bin, "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
                    "-vf", "scale='if(gt(iw,ih),640,-2)':'if(gt(iw,ih),-2,640)'", "-q:v", "4", str(dest)], capture_output=True, timeout=60)


def analyze(ctx: JobContext, path: Path, media_id: int, media_name: str) -> dict:
    ctx.progress(0.01, "Lecture des informations techniques…", force=True)
    probe = ffmpeg_service.probe(path)
    v = probe.get("video") or {}
    if not v:
        raise ValueError("Aucune piste vidéo")
    duration = probe.get("duration") or 0.0
    src_fps = v.get("fps") or 30.0
    fps = float(min(src_fps, 30.0 if duration <= 180 else 15.0))
    W, H = v["width"], v["height"]
    fmt = {
        "width": W, "height": H, "aspect": aspect_label(W, H), "orientation": "vertical" if H > W else "horizontal" if W > H else "carré",
        "fps": src_fps, "duration": round(duration, 2), "video_codec": v.get("codec"),
        "audio_codec": (probe.get("audio") or {}).get("codec"), "bit_rate": probe.get("bit_rate"),
    }

    # --- Passe 1 : images réduites -------------------------------------------------------------
    w, h = analysis_size(W, H, 72)
    expected = max(1, int(duration * fps))
    rgbs, grays, change, luma, hists = [], [], [], [], []
    for i, f in enumerate(iter_frames(ctx, path, fps, w, h)):
        g = gray(f.astype(np.float32))
        hh = scenes_mod.hist(f)
        change.append(0.0 if not grays else scenes_mod.frame_change(grays[-1], g, hists[-1], hh))
        rgbs.append(f)
        grays.append(g)
        hists.append(hh)
        luma.append(float(g.mean() / 255))
        if i % 15 == 0:
            ctx.progress(0.03 + 0.30 * min(1, i / expected), f"Décodage des images ({i}/{expected})…")
    n = len(grays)
    if n < 2:
        raise ValueError("Vidéo trop courte pour être analysée")
    change_a, luma_a = np.array(change), np.array(luma)

    # --- Plans et transitions ------------------------------------------------------------------
    ctx.progress(0.35, "Détection des coupes et transitions…", force=True)
    cuts = scenes_mod.detect_cuts(change_a, fps)
    gradual = scenes_mod.detect_gradual(grays, rgbs, change_a, luma_a, cuts, fps)
    boundaries = [(c, {"type": "cut", "duration": 0.0, "confidence": "élevée", "start_frame": c, "end_frame": c}) for c in cuts]
    boundaries += [(g["boundary_frame"], g) for g in gradual]
    boundaries.sort(key=lambda x: x[0])
    starts = [0] + [b for b, _ in boundaries]
    ends = [b - 1 for b, _ in boundaries] + [n - 1]
    trans_in = [None] + [t for _, t in boundaries]

    scenes = []
    kdir = keyframes_dir(media_id)
    for idx, (s, e, tin) in enumerate(zip(starts, ends, trans_in)):
        ctx.progress(0.38 + 0.25 * idx / max(1, len(starts)), f"Analyse du plan {idx + 1}/{len(starts)}…")
        # exclut les images de transition de la mesure du mouvement
        ms = max(s, tin["end_frame"] + 1) if tin and tin["type"] != "cut" else s
        nxt = trans_in[idx + 1] if idx + 1 < len(trans_in) else None
        me = min(e, nxt["start_frame"] - 1) if nxt and nxt["type"] != "cut" else e
        mot = motion_mod.shot_motion(grays, ms, me, fps) if me > ms else {"type": "trop_court", "confidence": "faible"}
        sample_idx = np.linspace(ms, max(ms, me), 4).round().astype(int)
        px = np.concatenate([rgbs[i].reshape(-1, 3) for i in sample_idx])
        st = colors_mod.stats(px)
        pal = colors_mod.palette(px, k=4)
        mid_t = (s + e) / 2 / fps
        kf = kdir / f"scene_{idx + 1:02d}.jpg"
        extract_keyframe(path, mid_t, kf)
        scenes.append({
            "index": idx + 1,
            "start": round(s / fps, 3), "end": round((e + 1) / fps, 3), "duration": round((e - s + 1) / fps, 3),
            "transition_in": {k: tin[k] for k in ("type", "duration", "confidence")} if tin else None,
            "motion": mot, "palette": pal, "color_stats": st, "keyframe": kf.name,
        })

    durations = np.array([sc["duration"] for sc in scenes])
    half = len(durations) // 2
    trend = None
    if len(durations) >= 4:
        first, second = durations[:half].mean(), durations[half:].mean()
        trend = "accélération" if second < first * 0.75 else "ralentissement" if second > first * 1.33 else "régulier"
    rhythm = {
        "shot_count": len(scenes),
        "avg_shot": round(float(durations.mean()), 2), "median_shot": round(float(np.median(durations)), 2),
        "min_shot": round(float(durations.min()), 2), "max_shot": round(float(durations.max()), 2),
        "std_shot": round(float(durations.std()), 2),
        "cuts_per_minute": round(len(boundaries) / (duration / 60), 1) if duration else None,
        "pace": pace_label(float(durations.mean())), "trend": trend,
    }

    tcount: dict[str, int] = {}
    for _, t in boundaries:
        tcount[t["type"]] = tcount.get(t["type"], 0) + 1
    grad_d = [t["duration"] for _, t in boundaries if t["type"] != "cut"]
    transitions = {"counts": tcount, "total": len(boundaries),
                   "avg_gradual_duration": round(float(np.mean(grad_d)), 2) if grad_d else None}

    mcount: dict[str, int] = {}
    for sc in scenes:
        mcount[sc["motion"]["type"]] = mcount.get(sc["motion"]["type"], 0) + 1
    zooms = [sc["motion"] for sc in scenes if sc["motion"]["type"] in ("zoom_avant", "zoom_arriere")]
    motion_summary = {"counts": mcount,
                      "zoom_share": round(len(zooms) / len(scenes), 2),
                      "avg_zoom_per_second": round(float(np.mean([abs(z["zoom_per_second"]) for z in zooms])), 4) if zooms else None,
                      "avg_zoom_total": round(float(np.mean([z["zoom_total"] for z in zooms])), 3) if zooms else None}

    all_px = np.concatenate([rgbs[i].reshape(-1, 3) for i in np.linspace(0, n - 1, min(n, 40)).round().astype(int)])
    gst = colors_mod.stats(all_px)
    colors = {"palette": colors_mod.palette(all_px, k=7), "stats": gst, "description": colors_mod.describe(gst),
              "scene_brightness_std": round(float(np.std([sc["color_stats"]["brightness"] for sc in scenes])), 3)}
    del rgbs

    # --- Passe 2 : textes incrustés --------------------------------------------------------------
    ctx.progress(0.65, "Recherche des sous-titres incrustés…", force=True)
    cfps = 4.0 if duration <= 120 else 2.0
    cw, ch = analysis_size(W, H, 270)
    cframes, ctimes = [], []
    for i, f in enumerate(iter_frames(ctx, path, cfps, cw, ch)):
        cframes.append(f)
        ctimes.append(i / cfps)
        if i % 8 == 0:
            ctx.progress(0.65 + 0.12 * min(1, i / max(1, duration * cfps)), "Recherche des sous-titres incrustés…")
    cut_times = [b / fps for b, _ in boundaries]
    caps = captions_mod.analyze(cframes, ctimes, cut_times)
    del cframes

    # --- Audio ---------------------------------------------------------------------------------
    ctx.progress(0.8, "Analyse audio (rythme, silences, synchronisation)…", force=True)
    aud = {"has_audio": False}
    if probe.get("audio"):
        y = read_audio(ctx, path, audio_mod.SR)
        aud = audio_mod.analyze(y, path, cut_times, duration)

    # --- Vision (optionnelle) ------------------------------------------------------------------
    ctx.progress(0.9, "Analyse visuelle complémentaire (modèle de vision local)…", force=True)
    kfs = [kdir / sc["keyframe"] for sc in scenes]
    pick = [kfs[i] for i in np.linspace(0, len(kfs) - 1, min(6, len(kfs))).round().astype(int)] if kfs else []
    vis = vision_mod.analyze(pick)

    limits = [
        "Les polices ne sont pas identifiées : aucune méthode fiable sans modèle dédié.",
        "Les sous-titres sont détectés par heuristique (texte clair à contour sombre) ; un texte sans contour peut être manqué.",
        "Les transitions animées (glissements, masques) sont signalées sans être identifiées précisément.",
        "La distinction parole / musique sera affinée par la transcription Whisper.",
    ]
    if not vis.get("available"):
        limits.append("Aucun modèle de vision local : cadrages et éléments graphiques non décrits.")

    return {
        "version": ANALYSIS_VERSION,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "media": {"id": media_id, "name": media_name},
        "analysis_fps": fps,
        "format": fmt, "rhythm": rhythm, "transitions": transitions, "motion": motion_summary,
        "colors": colors, "captions": caps, "audio": aud, "vision": vis,
        "scenes": scenes, "limits": limits,
    }
