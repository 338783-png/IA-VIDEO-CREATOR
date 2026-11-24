"""Génération de sous-titres ASS (libass) animés à partir du storyboard.

Modes : word (un mot à la fois, effet « pop »), chunk (2-4 mots, mot courant surligné), phrase (segment entier).
Les horaires des mots (Whisper) sont reportés de la source vers la timeline du montage.
"""
import re
import subprocess

from app.services import timeline


def ass_color(hex_color: str, alpha: int = 0) -> str:
    h = (hex_color or "#FFFFFF").lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def ass_time(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def font_available(family: str) -> bool:
    try:
        out = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True, timeout=10).stdout.lower()
        return family.lower() in out
    except (OSError, subprocess.SubprocessError):
        return False


def timeline_words(storyboard: dict) -> list[dict]:
    """Mots positionnés sur la timeline finale (depuis les scènes ou depuis la voix off)."""
    scenes = storyboard["scenes"]
    starts, total = timeline.compute(scenes)
    vo_words = (storyboard.get("audio") or {}).get("voiceover_words") or []
    if (storyboard.get("subtitles") or {}).get("source") == "voiceover" and vo_words:
        # la voix off démarre au début du montage ; découpage par phrase via un identifiant de « scène » fictif
        out, sent = [], 0
        for w in vo_words:
            if w["start"] >= total:
                break
            out.append({"word": w["word"], "start": w["start"], "end": min(w["end"], total), "scene": f"vo{sent}"})
            if re.search(r"[.!?…]$", w["word"]):
                sent += 1
        return out
    out = []
    for sc, t0 in zip(scenes, starts):
        if not sc.get("text"):
            continue
        words = sc.get("words") or []
        if sc.get("text_auto", True) and words:
            for w in words:
                ws = t0 + (w["start"] - sc["start"])
                we = t0 + (w["end"] - sc["start"])
                if we > t0 and ws < t0 + sc["duration"]:
                    out.append({"word": w["word"], "start": max(t0, ws), "end": min(t0 + sc["duration"], we), "scene": sc["id"]})
        else:  # texte modifié à la main : répartition régulière sur la durée du plan
            toks = sc["text"].split()
            step = sc["duration"] / max(1, len(toks))
            out += [{"word": tok, "start": t0 + i * step, "end": t0 + (i + 1) * step, "scene": sc["id"]} for i, tok in enumerate(toks)]
    return out


def chunks(words: list[dict], max_words: int = 3, max_gap: float = 0.45) -> list[list[dict]]:
    groups, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w["start"] - cur[-1]["end"] > max_gap or w["scene"] != cur[-1]["scene"]
                    or re.search(r"[.!?,;:…]$", cur[-1]["word"])):
            groups.append(cur)
            cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def build_ass(storyboard: dict, warnings: list[str] | None = None) -> str:
    sub = storyboard["subtitles"]
    W, H = storyboard["format"]["width"], storyboard["format"]["height"]
    font = sub.get("font") or "DejaVu Sans"
    if not font_available(font):
        if warnings is not None:
            warnings.append(f"Police « {font} » non installée : remplacée par DejaVu Sans. Installez-la (fichier .ttf) pour l'utiliser.")
        font = "DejaVu Sans"
    size = int(H * (sub.get("size_pct") or 4.6) / 100)
    if sub.get("mode") == "word":
        size = int(size * 1.25)
    pos = sub.get("position") or "bas"
    align = {"haut": 8, "centre": 5, "bas": 2}.get(pos, 2)
    center = (sub.get("vertical_center_pct") or {"haut": 18, "centre": 50, "bas": 75}[pos]) / 100
    margin_v = int(H * center - size / 2) if align == 8 else int(H * (1 - center) - size / 2) if align == 2 else 0
    margin_v = max(int(H * 0.04), margin_v)
    outline = max(2, int(size * 0.09)) if sub.get("outline", True) else 0
    primary = ass_color(sub.get("primary_color", "#FFFFFF"))
    highlight = ass_color(sub.get("highlight_color", "#FFD400"))
    out_c = ass_color(sub.get("outline_color", "#000000"))
    head = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        # Karaoké : SecondaryColour = avant prononciation, PrimaryColour = mot prononcé (surligné)
        f"Style: Sub,{font},{size},{highlight if sub.get('animated') else primary},{primary},{out_c},&H80000000,-1,0,0,0,100,100,0,0,1,{outline},"
        f"{max(1, outline // 2)},{align},{int(W * 0.08)},{int(W * 0.08)},{margin_v},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    words = timeline_words(storyboard)
    up = (lambda s: s.upper()) if sub.get("uppercase") else (lambda s: s)
    lines = []
    mode = sub.get("mode") or "chunk"
    manual = sub.get("manual_cues")
    if manual:
        for c in manual:
            toks = c["text"].split()
            if sub.get("animated") and toks:
                step = max(1, int(round((c["end"] - c["start"]) * 100 / len(toks))))
                text = r"{\fad(60,40)}" + " ".join(r"{\k%d}" % step + esc(up(t)) for t in toks)
            else:
                text = esc(up(c["text"]))
            lines.append(f"Dialogue: 0,{ass_time(c['start'])},{ass_time(c['end'])},Sub,,0,0,0,,{text}")
    elif mode == "word":
        for i, w in enumerate(words):
            end = min(w["end"] + 0.25, words[i + 1]["start"]) if i + 1 < len(words) else w["end"] + 0.4
            end = max(end, w["start"] + 0.12)
            pop = r"{\fscx70\fscy70\t(0,90,\fscx108\fscy108)\t(90,160,\fscx100\fscy100)}" if sub.get("animated") else ""
            lines.append(f"Dialogue: 0,{ass_time(w['start'])},{ass_time(end)},Sub,,0,0,0,,{pop}{esc(up(w['word']))}")
    else:
        groups = chunks(words, 3 if mode == "chunk" else 12, 0.45 if mode == "chunk" else 0.9)
        for gi, g in enumerate(groups):
            start = g[0]["start"]
            nxt = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else g[-1]["end"] + 0.5
            end = max(min(g[-1]["end"] + 0.3, nxt), start + 0.2)
            if sub.get("animated"):
                parts, t = [], start
                for w in g:
                    lead = max(0, int(round((w["start"] - t) * 100)))
                    dur = max(1, int(round((w["end"] - w["start"]) * 100)))
                    parts.append((r"{\k%d}" % lead if lead else "") + r"{\k%d}" % dur + esc(up(w["word"])))
                    t = w["end"]
                text = r"{\fad(60,40)}" + " ".join(parts)
            else:
                text = esc(up(" ".join(w["word"] for w in g)))
            lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Sub,,0,0,0,,{text}")
    return "\n".join(head + lines) + "\n"
