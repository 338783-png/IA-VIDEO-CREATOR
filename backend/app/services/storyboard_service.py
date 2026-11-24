"""Validation et normalisation des modifications manuelles du storyboard."""
import json
import re

from app.core.config import settings
from app.core.errors import AppError
from app.services import timeline

ALLOWED_PLATFORMS = {"tiktok": (1080, 1920), "reels": (1080, 1920), "shorts": (1080, 1920), "youtube": (1920, 1080)}
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def normalize(data: dict, media: dict[int, dict], previous: dict | None) -> dict:
    """Vérifie un storyboard soumis par l'utilisateur et recalcule durées, positions et textes."""
    scenes_in = data.get("scenes")
    if not isinstance(scenes_in, list) or not scenes_in:
        raise AppError("Le storyboard doit contenir au moins une scène.", 422, "empty_storyboard")
    if len(scenes_in) > 300:
        raise AppError("Trop de scènes (300 maximum).", 422, "too_many_scenes")
    prev_scenes = {s["id"]: s for s in (previous or {}).get("scenes", [])}
    out_scenes = []
    for i, s in enumerate(scenes_in):
        mid = s.get("media_id")
        m = media.get(mid)
        if not m:
            raise AppError(f"Scène {i + 1} : média {mid} absent du projet.", 422, "bad_media")
        kind = "image" if m["category"] == "image" else "video"
        start, end = float(s.get("start", 0)), float(s.get("end", 0))
        src_dur = m["probe"].get("duration") or None
        if kind == "image":
            start = 0.0
        if start < 0 or end - start < 0.3:
            raise AppError(f"Scène {i + 1} : durée trop courte (0,3 s minimum).", 422, "bad_range")
        if src_dur and kind == "video" and end > src_dur + 0.05:
            raise AppError(f"Scène {i + 1} : la fin ({end:.2f} s) dépasse la durée de la source ({src_dur:.2f} s).", 422, "bad_range")
        effect = s.get("effect", "none")
        if effect not in timeline.EFFECTS:
            raise AppError(f"Scène {i + 1} : effet inconnu « {effect} ».", 422, "bad_effect")
        tr = s.get("transition", "cut")
        if tr not in timeline.TRANSITIONS:
            raise AppError(f"Scène {i + 1} : transition inconnue « {tr} ».", 422, "bad_transition")
        prev = prev_scenes.get(s.get("id"), {})
        text = str(s.get("text", ""))[:2000]
        words = prev.get("words", [])
        text_auto = bool(s.get("text_auto", True))
        if prev and text != prev.get("text", ""):
            text_auto = False  # texte modifié à la main
        if text_auto and prev and (abs(start - prev.get("start", start)) > 1e-3 or abs(end - prev.get("end", end)) > 1e-3):
            words = [w for w in s.get("all_words", []) or words if w["start"] >= start - 0.05 and w["end"] <= end + 0.05]
        sc = {
            "id": str(s.get("id") or f"s{i + 1}")[:20], "media_id": mid, "source": m["original_name"], "kind": kind,
            "start": round(start, 3), "end": round(end, 3), "duration": round(end - start, 3),
            "text": text, "text_auto": text_auto, "words": words, "effect": effect, "transition": tr,
            "transition_duration": round(max(0.0, min(1.5, float(s.get("transition_duration") or (0.3 if tr != "cut" else 0)))), 3),
            "volume": round(max(0.0, min(2.0, float(s.get("volume", 1.0)))), 3),
            "group": s.get("group"), "score": s.get("score"), "reason": s.get("reason", "modifié manuellement"),
        }
        out_scenes.append(sc)
    ids = [s["id"] for s in out_scenes]
    if len(set(ids)) != len(ids):
        raise AppError("Identifiants de scène en double.", 422, "duplicate_ids")
    for i, sc in enumerate(out_scenes):
        sc["position"] = i + 1
    starts, total = timeline.compute(out_scenes)
    for sc, t0 in zip(out_scenes, starts):
        sc["timeline_start"] = t0

    base = dict(previous or {})
    base["scenes"] = out_scenes
    base["total_duration"] = total
    if "format" in data:
        plat = data["format"].get("platform")
        if plat not in ALLOWED_PLATFORMS:
            raise AppError("Plateforme inconnue.", 422, "bad_platform")
        W, H = ALLOWED_PLATFORMS[plat]
        fps = int(data["format"].get("fps") or 30)
        if fps not in (24, 25, 30, 50, 60):
            raise AppError("Fréquence d'images autorisée : 24, 25, 30, 50 ou 60.", 422, "bad_fps")
        base["format"] = {"platform": plat, "width": W, "height": H, "fps": fps}
    if "fit_mode" in data:
        if data["fit_mode"] not in ("cover", "blur"):
            raise AppError("Cadrage inconnu.", 422, "bad_fit")
        base["fit_mode"] = data["fit_mode"]
    if "subtitles" in data:
        sub = {**base.get("subtitles", {}), **data["subtitles"]}
        for k in ("primary_color", "outline_color", "highlight_color"):
            if sub.get(k) and not HEX.match(sub[k]):
                raise AppError(f"Couleur invalide : {k}.", 422, "bad_color")
        if sub.get("mode") not in ("word", "chunk", "phrase"):
            raise AppError("Mode de sous-titres inconnu.", 422, "bad_mode")
        if sub.get("source", "scenes") not in ("scenes", "voiceover"):
            raise AppError("Source des sous-titres inconnue.", 422, "bad_source")
        if sub.get("position") not in ("haut", "centre", "bas"):
            raise AppError("Position de sous-titres inconnue.", 422, "bad_position")
        sub["size_pct"] = max(2.0, min(10.0, float(sub.get("size_pct") or 4.6)))
        if sub.get("manual_cues"):
            from app.services import subtitles_export
            sub["manual_cues"] = subtitles_export.validate_manual(sub["manual_cues"], total) or None
        else:
            sub["manual_cues"] = None
        sub["font"] = re.sub(r"[^\w \-]", "", str(sub.get("font") or "DejaVu Sans"))[:60] or "DejaVu Sans"
        base["subtitles"] = sub
    if "audio" in data:
        au = {**base.get("audio", {}), **data["audio"]}
        for k in ("music_media_id", "voiceover_media_id"):
            if au.get(k) is not None and (au[k] not in media or media[au[k]]["category"] != "audio"):
                raise AppError(f"{k} : fichier audio absent du projet.", 422, "bad_audio")
        au["music_volume_db"] = max(-40.0, min(0.0, float(au.get("music_volume_db", -16))))
        au["original_volume"] = max(0.0, min(2.0, float(au.get("original_volume", 1.0))))
        base["audio"] = au
    return base


def save_json(project_id: int, version: int, data: dict) -> str:
    folder = settings.projects_dir / "storyboards" / f"project-{project_id}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"storyboard_v{version:03d}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
