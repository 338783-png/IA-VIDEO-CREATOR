"""Génération du storyboard : sélection des passages, ordre, effets, transitions, textes, audio."""
import difflib
import json
import logging
import random
import re
from datetime import datetime, timezone

from app.core.config import ROOT_DIR
from app.services import instruction_parser, ollama_service, timeline

log = logging.getLogger("planner")

PLATFORM_FORMATS = {"tiktok": (1080, 1920), "reels": (1080, 1920), "shorts": (1080, 1920), "youtube": (1920, 1080)}
FILLERS = {"euh", "heu", "hum", "hmm", "bah", "ben", "euhm", "mmh"}
DEFAULT_STYLE = {
    "rhythm": {"target_shot_duration": 3.0, "min_shot": 1.2, "max_shot": 5.0},
    "transitions": {"default": "cut", "distribution": {"cut": 1.0}, "durations": {}},
    "motion": {"zoom": {"enabled": True, "probability": 0.3, "direction": "in", "scale_per_second": 0.03, "max_scale": 1.15}},
    "subtitles": {"enabled": True, "position": "bas", "vertical_center_pct": 75, "primary_color": "#FFFFFF", "outline_color": "#000000",
                  "outline": True, "mode": "chunk", "font": {"family": None}},
    "audio": {"target_lufs": -14.0},
    "sync": {"cut_on_beat": False},
}


def _norm_text(s: str) -> str:
    s = re.sub(r"[^\w\s']", " ", s.lower())
    return " ".join(w for w in s.split() if w not in FILLERS)


# --------------------------------------------------------------------------- découpage en phrases
def merge_word_tokens(words: list[dict]) -> list[dict]:
    """Recolle les jetons Whisper coupés (« aujourd » + « 'hui », « quelqu » + « 'un », « peut » + « -être »)."""
    out: list[dict] = []
    for w in words:
        tok = w["word"]
        if out and (tok[:1] in "'’-" or out[-1]["word"][-1:] in "'’") and tok.strip("'’-"):
            out[-1] = {**out[-1], "word": out[-1]["word"] + tok, "end": w["end"], "prob": min(out[-1].get("prob", 1), w.get("prob", 1))}
        else:
            out.append(dict(w))
    return out


def join_words(words: list[dict]) -> str:
    return " ".join(w["word"] for w in merge_word_tokens(words)).strip()


def sentences_from_transcript(media_id: int, transcript: dict, duration: float) -> list[dict]:
    words = merge_word_tokens(transcript.get("words") or [])
    out, cur = [], []

    def flush():
        if not cur:
            return
        text = join_words(cur)
        out.append({"media_id": media_id, "start": cur[0]["start"], "end": cur[-1]["end"], "text": text,
                    "words": list(cur), "prob": sum(w["prob"] for w in cur) / len(cur)})
        cur.clear()

    for i, w in enumerate(words):
        if cur and w["start"] - cur[-1]["end"] > 0.7:
            flush()
        cur.append(w)
        if re.search(r"[.!?…]$", w["word"]) or len(cur) >= 40:
            flush()
    flush()
    # une phrase très courte (« Première astuce. ») est collée à la suivante si elles s'enchaînent sans pause
    merged: list[dict] = []
    for sent in out:
        prev = merged[-1] if merged else None
        if prev and len(prev["words"]) <= 3 and sent["start"] - prev["end"] < 0.8:
            ws = prev["words"] + sent["words"]
            merged[-1] = {**prev, "end": sent["end"], "text": join_words(ws), "words": ws,
                          "prob": sum(w["prob"] for w in ws) / len(ws)}
        else:
            merged.append(sent)
    out = merged
    # marges : un peu d'air avant/après, sans empiéter sur les phrases voisines
    for i, s in enumerate(out):
        prev_end = out[i - 1]["end"] if i else 0.0
        next_start = out[i + 1]["start"] if i + 1 < len(out) else duration
        s["start"] = round(max(prev_end, s["start"] - 0.12, 0.0), 3)
        s["end"] = round(min(next_start, s["end"] + 0.2, duration), 3)
        s["duration"] = round(s["end"] - s["start"], 3)
    return out


def mark_repetitions(sents: list[dict]) -> None:
    """Prises ratées : une phrase très proche d'une phrase suivante (même média) est une répétition -> on garde la dernière."""
    for i, a in enumerate(sents):
        na = _norm_text(a["text"])
        if not na:
            a["reject"] = "hésitation seule"
            continue
        for b in sents[i + 1:i + 6]:
            if b["media_id"] != a["media_id"]:
                continue
            nb = _norm_text(b["text"])
            if len(na.split()) < 4:  # trop court pour être une prise ratée (titres, transitions)
                break
            ratio = difflib.SequenceMatcher(None, na, nb).ratio()
            false_start = len(na) >= 8 and nb.startswith(na[: max(8, int(len(na) * 0.8))]) and len(nb) > len(na)
            if ratio > 0.75 or false_start:
                a["reject"] = "répétition (prise reprise plus loin)"
                a["repeat_of"] = b["start"]
                break


def score_sentence(s: dict, keywords: set[str], energy: list[float]) -> float:
    words = [w for w in _norm_text(s["text"]).split()]
    n = len(words)
    if n == 0:
        return 0.0
    rate = n / max(0.3, s["duration"])
    rate_score = 1.0 - min(1.0, abs(rate - 2.8) / 2.8)  # débit naturel ~2.8 mots/s
    fill = sum(1 for w in s["text"].lower().split() if w.strip(",.") in FILLERS) / max(1, len(s["text"].split()))
    kw = len(keywords & set(words)) / max(1, len(keywords)) if keywords else 0.0
    sec = energy[int(s["start"]):int(s["end"]) + 1] if energy else []
    en = sum(sec) / len(sec) if sec else 0.5
    hook = 0.15 if re.search(r"\?|savez-vous|saviez-vous|secret|astuce|pourquoi|comment|erreur|jamais|toujours", s["text"].lower()) else 0.0
    length_ok = 1.0 if 1.0 <= s["duration"] <= 12 else 0.5
    return round(0.25 * rate_score + 0.25 * s["prob"] + 0.15 * en + 0.15 * kw + hook + 0.1 * length_ok - 0.4 * fill, 4)


# --------------------------------------------------------------------------- candidats sans parole
def visual_candidates(media: dict, analysis: dict, target_shot: float) -> list[dict]:
    dur = analysis.get("duration") or media["probe"].get("duration") or 0
    shots = analysis.get("shots") or [{"start": 0.0, "end": dur}]
    motion = analysis.get("motion_per_second") or []
    energy = analysis.get("energy_per_second") or []
    out = []
    for sh in shots:
        s, e = sh["start"], sh["end"]
        length = e - s
        if length < 0.6:
            continue
        n = max(1, int(length // (target_shot * 1.5)))
        for k in range(n):
            cs = s + k * length / n
            ce = min(e, cs + target_shot)
            if ce - cs < 0.6:
                continue
            mo = motion[int(cs):int(ce) + 1]
            en = energy[int(cs):int(ce) + 1]
            score = 0.5 * min(1.0, (sum(mo) / len(mo) * 25) if mo else 0.2) + 0.3 * ((sum(en) / len(en)) if en else 0.5) + 0.2
            out.append({"media_id": media["id"], "start": round(cs, 3), "end": round(ce, 3), "duration": round(ce - cs, 3),
                        "text": "", "words": [], "score": round(score, 4), "visual": True})
    return out


# --------------------------------------------------------------------------- sélection
def llm_select(cands: list[dict], instruction: str, target: float) -> tuple[list[int] | None, dict]:
    if not ollama_service.status()["model_ready"] or not cands:
        return None, {"used": False, "note": "Ollama indisponible : sélection par règles."}
    listing = "\n".join(f"[{i}] ({c['duration']:.1f} s) {c['text'][:220] or '(plan sans parole)'}" for i, c in enumerate(cands[:120]))
    tpl = (ROOT_DIR / "ai" / "prompts" / "segment_selection.md").read_text(encoding="utf-8")
    prompt = tpl.replace("{target}", str(int(target))).replace("{instruction}", instruction or "montage court et percutant").replace("{segments}", listing)
    try:
        raw = json.loads(ollama_service.generate(prompt, as_json=True, timeout=300))
        sel = [int(x) for x in raw.get("selected", []) if str(x).isdigit() or isinstance(x, int)]
        sel = [i for i in dict.fromkeys(sel) if 0 <= i < min(len(cands), 120)]
        total = sum(cands[i]["duration"] for i in sel)
        if not sel or not (0.5 * target <= total <= 1.4 * target):
            return None, {"used": True, "rejected": True, "note": f"Proposition du LLM écartée (durée {total:.0f} s pour {target:.0f} s visés) : sélection par règles."}
        return sel, {"used": True, "title": raw.get("title"), "hook": raw.get("hook"), "reason": raw.get("reason")}
    except Exception as e:  # noqa: BLE001
        log.warning("Sélection LLM échouée : %s", e)
        return None, {"used": False, "note": f"Erreur LLM ({str(e)[:100]}) : sélection par règles."}


def greedy_select(cands: list[dict], target: float) -> list[int]:
    order = sorted(range(len(cands)), key=lambda i: -cands[i]["score"])
    chosen, total = [], 0.0
    for i in order:
        if total >= target:
            break
        if total + cands[i]["duration"] > target * 1.15 and total > target * 0.8:
            continue
        chosen.append(i)
        total += cands[i]["duration"]
    # ordre chronologique (récit cohérent) : par média puis par temps
    return sorted(chosen, key=lambda i: (cands[i]["media_order"], cands[i]["start"]))


# --------------------------------------------------------------------------- construction des scènes
def split_long(c: dict, max_shot: float, target_shot: float) -> list[dict]:
    """Découpe un long passage parlé en plans plus courts, aux frontières de mots (audio continu)."""
    if c["duration"] <= max_shot * 1.3 or not c["words"]:
        return [c]
    parts, cur_start, cur_words = [], c["start"], []
    for w in c["words"]:
        cur_words.append(w)
        if w["end"] - cur_start >= target_shot and w is not c["words"][-1]:
            end = round((w["end"] + c["words"][c["words"].index(w) + 1]["start"]) / 2, 3)
            parts.append({**c, "start": cur_start, "end": end, "words": cur_words, "text": join_words(cur_words)})
            cur_start, cur_words = end, []
    if cur_words:
        parts.append({**c, "start": cur_start, "end": c["end"], "words": cur_words, "text": join_words(cur_words)})
    elif parts:
        parts[-1]["end"] = c["end"]
    for p in parts:
        p["duration"] = round(p["end"] - p["start"], 3)
    # fusion d'un dernier morceau trop court
    if len(parts) > 1 and parts[-1]["duration"] < 1.0:
        last = parts.pop()
        parts[-1] |= {"end": last["end"], "duration": round(last["end"] - parts[-1]["start"], 3),
                      "words": parts[-1]["words"] + last["words"], "text": parts[-1]["text"] + " " + last["text"]}
    return parts


class _Spread:
    """Répartit régulièrement un effet selon une proportion (au lieu d'un tirage au hasard)."""

    def __init__(self, p: float):
        self.p, self.acc = max(0.0, min(1.0, p)), 0.5

    def next(self) -> bool:
        self.acc += self.p
        if self.acc >= 1.0:
            self.acc -= 1.0
            return True
        return False


DYNAMIC = ["slide_left", "zoom_in", "wipe_left", "slide_up", "circle_open"]


def _transition_plan(rng: random.Random, style: dict, dynamic: bool):
    tr = style.get("transitions") or {}
    dist = {("crossfade" if k == "animated" else k): v for k, v in (tr.get("distribution") or {"cut": 1.0}).items()}
    dist = {k: v for k, v in dist.items() if k in timeline.TRANSITIONS}
    non_cut = {k: v for k, v in dist.items() if k != "cut"}
    share = sum(non_cut.values()) / (sum(dist.values()) or 1)
    if dynamic:
        share = max(share, 0.6)
    spread = _Spread(share)
    rot = list(DYNAMIC)
    rng.shuffle(rot)
    counter = {"i": 0}

    def pick() -> tuple[str, float]:
        if not spread.next():
            return "cut", 0.0
        if dynamic:
            t = rot[counter["i"] % len(rot)]
            counter["i"] += 1
        else:
            keys = list(non_cut) or ["crossfade"]
            t = rng.choices(keys, weights=[non_cut.get(k, 1) for k in keys])[0]
        d = float((tr.get("durations") or {}).get(t) or (0.3 if dynamic else 0.45))
        return t, round(min(0.8, max(0.15, d)), 2)

    return pick


def build(project: dict, media: list[dict], analyses: dict[int, dict], transcripts: dict[int, dict],
          style: dict | None, style_meta: dict, instruction: str, overrides: dict, use_llm: bool = True) -> dict:
    parsed = instruction_parser.parse(instruction, use_llm=use_llm)
    st = {**DEFAULT_STYLE, **(style or {})}
    rhythm = st["rhythm"]
    target_shot = float(rhythm.get("target_shot_duration") or 3.0)
    max_shot = float(rhythm.get("max_shot") or target_shot * 1.8)
    platform = overrides.get("platform") or parsed.get("platform") or project.get("target_format") or "tiktok"
    W, H = PLATFORM_FORMATS.get(platform, (1080, 1920))
    fps = int((style or {}).get("format", {}).get("fps") or 30)
    rng = random.Random(project["id"] * 1000 + len(instruction or ""))
    notes, rejected = [], []

    videos = [m for m in media if m["category"] == "video" and m["kind"] == "video"]
    images = [m for m in media if m["category"] == "image"]
    audios = [m for m in media if m["category"] == "audio"]
    if not videos and not images:
        raise ValueError("Importez au moins une vidéo ou une image dans le projet.")

    keywords = {w for w in _norm_text(instruction or "").split() if len(w) > 4} - {"video", "transforme", "ajoute", "secondes", "tiktok", "musique", "sous", "titres", "transitions", "zooms", "dynamiques", "discrete", "francaise"}

    # 1) candidats
    cands = []
    for order, m in enumerate(videos):
        an, tr = analyses.get(m["id"], {}), transcripts.get(m["id"], {})
        dur = an.get("duration") or m["probe"].get("duration") or 0
        sents = sentences_from_transcript(m["id"], tr, dur) if tr.get("words") else []
        if sents:
            mark_repetitions(sents)
            for s in sents:
                s["media_order"] = order
                if s.get("reject"):
                    rejected.append({"media_id": m["id"], "source": m["original_name"], "start": s["start"], "end": s["end"],
                                     "text": s["text"], "reason": s["reject"]})
                    continue
                s["score"] = score_sentence(s, keywords, an.get("energy_per_second") or [])
                cands.append(s)
            for sil in an.get("silences") or []:
                if sil[1] - sil[0] >= 1.0:
                    rejected.append({"media_id": m["id"], "source": m["original_name"], "start": sil[0], "end": sil[1], "text": "", "reason": "silence"})
        else:
            for c in visual_candidates(m, an, target_shot):
                c["media_order"] = order
                cands.append(c)
    for k, m in enumerate(images):
        cands.append({"media_id": m["id"], "start": 0.0, "end": target_shot, "duration": target_shot, "text": "", "words": [],
                      "score": 0.4, "image": True, "media_order": len(videos) + k})
    if not cands:
        raise ValueError("Aucun passage exploitable trouvé (vidéos silencieuses et sans images ?).")

    total_available = sum(c["duration"] for c in cands)
    target = overrides.get("target_duration") or parsed.get("target_duration_s") or min(60.0, total_available)
    target = float(min(target, total_available))

    # 2) sélection — si tout le contenu utile tient dans la durée visée, rien à couper : on garde tout, dans l'ordre
    if total_available <= target * 1.05:
        sel = sorted(range(len(cands)), key=lambda i: (cands[i]["media_order"], cands[i]["start"]))
        llm_info = {"used": False, "note": "Tout le contenu utile tient dans la durée visée : aucun passage n'est coupé."}
    elif use_llm:
        sel, llm_info = llm_select(cands, instruction, target)
    else:
        sel, llm_info = None, {"used": False, "note": "LLM désactivé."}
    if sel is None:
        sel = greedy_select(cands, target)
    chosen = [cands[i] for i in sel]
    if total_available < (parsed.get("target_duration_s") or 0) * 0.9:
        notes.append(f"Contenu disponible ({total_available:.0f} s) inférieur à la durée demandée ({parsed['target_duration_s']:.0f} s) : tout le contenu utile est utilisé.")

    # 3) scènes
    zoom_cfg = st["motion"].get("zoom", {})
    zoom_p = float(zoom_cfg.get("probability") or 0) if zoom_cfg.get("enabled") else 0.0
    if parsed.get("zooms") is True:
        zoom_p = max(zoom_p, 0.5)
    elif parsed.get("zooms") is False:
        zoom_p = 0.0
    zoom_eff = "zoom_out" if zoom_cfg.get("direction") == "out" else "zoom_in"
    media_by_id = {m["id"]: m for m in media}
    zoom_spread = _Spread(zoom_p)
    scenes = []
    for gi, c in enumerate(chosen):
        parts = split_long(c, max_shot, target_shot) if not c.get("image") else [c]
        for pi, p in enumerate(parts):
            m = media_by_id[p["media_id"]]
            if p.get("image"):
                effect = rng.choice(["zoom_in", "pan_left", "pan_right"]) if zoom_p else "zoom_in"
            elif len(parts) > 1 and pi % 2 == 1 and zoom_p:
                effect = "punch_in"  # « jump cut » : recadrage alterné dans une même phrase
            else:
                effect = zoom_eff if zoom_spread.next() else "none"
            scenes.append({
                "id": f"s{len(scenes) + 1}", "media_id": m["id"], "source": m["original_name"],
                "kind": "image" if p.get("image") else "video",
                "start": round(p["start"], 3), "end": round(p["end"], 3), "duration": round(p["end"] - p["start"], 3),
                "text": p["text"], "text_auto": True, "words": [{"word": w["word"], "start": w["start"], "end": w["end"]} for w in p["words"]],
                "effect": effect, "transition": "cut", "transition_duration": 0.0, "volume": 1.0,
                "group": gi, "score": c.get("score"),
                "reason": "passage parlé retenu" if p["text"] else ("image du projet" if p.get("image") else "plan visuel le plus vivant"),
            })
    # transitions : jamais au milieu d'une phrase ni entre deux phrases parlées qui s'enchaînent
    pick = _transition_plan(rng, st, bool(parsed.get("dynamic_transitions")))
    for i in range(len(scenes) - 1):
        a, b = scenes[i], scenes[i + 1]
        contiguous = a["media_id"] == b["media_id"] and abs(a["end"] - b["start"]) < 0.05
        continuous_speech = (a["group"] == b["group"]) or (contiguous and a["text"] and b["text"])
        if not continuous_speech:
            t, d = pick()
            if a["text"] and b["text"] and t in ("fade_black", "flash_white") and not parsed.get("dynamic_transitions"):
                t = "crossfade"
            a["transition"], a["transition_duration"] = t, (d if t != "cut" else 0.0)
    # recalage sur le temps musical pour les plans sans parole
    music = None
    music_candidates = [m for m in audios if (analyses.get(m["id"], {}).get("speech_seconds") or 0) < 0.25 * (m["probe"].get("duration") or 1)]
    voice_candidates = [m for m in audios if m not in music_candidates]
    if parsed.get("music") is not False and music_candidates and (parsed.get("music") or st.get("audio", {}).get("music", {}).get("enabled")):
        music = music_candidates[0]
    elif parsed.get("music") and not music_candidates:
        notes.append("Musique demandée mais aucun fichier musical importé : ajoutez un MP3/WAV libre de droits au projet.")
    bpm = analyses.get(music["id"], {}).get("tempo_bpm") if music else None
    if bpm and st.get("sync", {}).get("cut_on_beat"):
        beat = 60 / bpm
        for sc in scenes:
            if not sc["text"]:
                n = max(1, round(sc["duration"] / beat))
                new_end = sc["start"] + n * beat
                src_dur = media_by_id[sc["media_id"]]["probe"].get("duration") or new_end
                if sc["kind"] == "image" or new_end <= src_dur:
                    sc["end"], sc["duration"] = round(new_end, 3), round(n * beat, 3)
        notes.append(f"Plans visuels calés sur le tempo de la musique ({bpm:.0f} BPM).")

    for i, sc in enumerate(scenes):
        sc["position"] = i + 1
    starts, total = timeline.compute(scenes)
    for sc, t0 in zip(scenes, starts):
        sc["timeline_start"] = t0

    # 4) sous-titres et audio
    sub = dict(st.get("subtitles") or DEFAULT_STYLE["subtitles"])
    sub_enabled = parsed.get("subtitles") is not False and any(s["text"] for s in scenes)
    font = (sub.get("font") or {}).get("family") or "DejaVu Sans"
    mode = "word" if parsed.get("animated_subtitles") and sub.get("mode") == "word" else ("chunk" if parsed.get("animated_subtitles") else sub.get("mode") or "chunk")
    subtitles = {"enabled": sub_enabled, "mode": mode, "position": sub.get("position") or "bas",
                 "vertical_center_pct": sub.get("vertical_center_pct") or 75, "font": font,
                 "primary_color": sub.get("primary_color") or "#FFFFFF", "outline_color": sub.get("outline_color") or "#000000",
                 "highlight_color": "#FFD400", "outline": sub.get("outline", True), "uppercase": True, "size_pct": 4.6,
                 "animated": bool(parsed.get("animated_subtitles"))}
    level_db = {"discrète": -22, "normale": -16, "forte": -10}.get(parsed.get("music_level") or "normale", -16)
    voiceover = {"requested": bool(parsed.get("voiceover")), "media_id": None, "script": None, "status": "non demandée"}
    if parsed.get("voiceover"):
        if voice_candidates:
            voiceover |= {"media_id": voice_candidates[0]["id"], "status": "fichier audio du projet", "source": voice_candidates[0]["original_name"]}
        else:
            voiceover |= {"status": "à générer (moteur vocal : prompt 6) ou importez un enregistrement",
                          "script": " ".join(s["text"] for s in scenes if s["text"])[:2000] or None}
            notes.append("Voix off demandée : aucun enregistrement fourni. Le texte est préparé ; la synthèse vocale locale sera ajoutée au prompt 6.")
    audio = {"original_volume": 0.25 if voiceover["media_id"] else 1.0, "music_media_id": music["id"] if music else None,
             "music_source": music["original_name"] if music else None, "music_volume_db": level_db, "ducking": True,
             "voiceover_media_id": voiceover["media_id"], "voiceover": voiceover,
             "target_lufs": float((st.get("audio") or {}).get("target_lufs") or -14.0)}

    if not style:
        notes.append("Aucun style officiel validé : style par défaut appliqué.")
    if llm_info.get("note"):
        notes.append(llm_info["note"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "instruction": instruction, "parsed_instruction": parsed,
        "style": style_meta, "format": {"platform": platform, "width": W, "height": H, "fps": fps},
        "fit_mode": "cover", "target_duration": round(target, 2), "total_duration": total,
        "scenes": scenes, "subtitles": subtitles, "audio": audio,
        "rejected": rejected[:200], "notes": notes, "llm": llm_info,
    }
