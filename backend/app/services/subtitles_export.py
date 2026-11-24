"""Sous-titres : segments (cues) automatiques ou manuels, export SRT / WebVTT, contrôle de synchronisation."""
import re

from app.core.errors import AppError
from app.services import subtitles_ass, timeline

MAX_CUES = 2000


def auto_cues(storyboard: dict) -> list[dict]:
    """Segments calculés depuis les horaires des mots (mêmes regroupements que l'incrustation)."""
    sub = storyboard.get("subtitles") or {}
    words = subtitles_ass.timeline_words(storyboard)
    mode = sub.get("mode") or "chunk"
    if mode == "word":
        groups = [[w] for w in words]
    else:
        groups = subtitles_ass.chunks(words, 3 if mode == "chunk" else 12, 0.45 if mode == "chunk" else 0.9)
    cues = []
    for i, g in enumerate(groups):
        nxt = groups[i + 1][0]["start"] if i + 1 < len(groups) else g[-1]["end"] + 0.5
        end = max(min(g[-1]["end"] + 0.3, nxt), g[0]["start"] + 0.2)
        cues.append({"start": round(g[0]["start"], 3), "end": round(end, 3), "text": " ".join(w["word"] for w in g),
                     "words": [{"word": w["word"], "start": round(w["start"], 3), "end": round(w["end"], 3)} for w in g]})
    return cues


def cues(storyboard: dict) -> list[dict]:
    manual = (storyboard.get("subtitles") or {}).get("manual_cues")
    return manual if manual else auto_cues(storyboard)


def validate_manual(raw: list, total: float) -> list[dict]:
    if not isinstance(raw, list):
        raise AppError("Format des sous-titres invalide.", 422, "bad_cues")
    if len(raw) > MAX_CUES:
        raise AppError("Trop de sous-titres.", 422, "bad_cues")
    out = []
    for i, c in enumerate(raw):
        try:
            s, e, txt = float(c["start"]), float(c["end"]), str(c["text"]).strip()
        except (KeyError, TypeError, ValueError) as err:
            raise AppError(f"Sous-titre {i + 1} incomplet.", 422, "bad_cues") from err
        if not txt:
            continue  # un sous-titre vidé est supprimé
        if s < 0 or e - s < 0.1 or s > total + 0.05:
            raise AppError(f"Sous-titre {i + 1} : horaires invalides ({s:.2f} → {e:.2f} s).", 422, "bad_cues")
        out.append({"start": round(s, 3), "end": round(min(e, total), 3), "text": txt[:300]})
    out.sort(key=lambda c: c["start"])
    for a, b in zip(out, out[1:]):
        if b["start"] < a["end"] - 1e-3:
            raise AppError(f"Les sous-titres « {a['text'][:20]} » et « {b['text'][:20]} » se chevauchent.", 422, "cue_overlap")
    return out


def _ts(t: float, sep: str) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("-->", "→")).strip()


def to_srt(cs: list[dict]) -> str:
    return "\n".join(f"{i}\n{_ts(c['start'], ',')} --> {_ts(c['end'], ',')}\n{_clean(c['text'])}\n" for i, c in enumerate(cs, 1))


def to_vtt(cs: list[dict]) -> str:
    body = "\n".join(f"{_ts(c['start'], '.')} --> {_ts(c['end'], '.')}\n{_clean(c['text'])}\n" for c in cs)
    return "WEBVTT\n\n" + body


def _norm(w: str) -> str:
    return re.sub(r"[^\w']", "", w.lower())


def sync_report(storyboard: dict) -> dict:
    """Écart entre le début de chaque sous-titre et l'instant où son premier mot est prononcé."""
    words = subtitles_ass.timeline_words(storyboard)
    cs = cues(storyboard)
    _, total = timeline.compute(storyboard["scenes"])
    if not words or not cs:
        return {"checked": 0, "max_offset_ms": None, "ok": True, "total_duration": total}
    offsets = []
    for c in cs:
        first = _norm(c["text"].split()[0]) if c["text"].split() else ""
        same = [w for w in words if _norm(w["word"]) == first and abs(w["start"] - c["start"]) < 3.0]
        if same:  # mot retrouvé dans la parole : écart à son début réel
            offsets.append(min(abs(w["start"] - c["start"]) for w in same))
    mx = max(offsets) if offsets else 0.0
    return {"checked": len(offsets), "max_offset_ms": int(round(mx * 1000)), "ok": mx <= 0.15,
            "manual": bool((storyboard.get("subtitles") or {}).get("manual_cues")), "total_duration": total}
