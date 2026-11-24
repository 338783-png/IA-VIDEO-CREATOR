"""Interprétation de la consigne utilisateur : règles déterministes + LLM local facultatif."""
import json
import logging
import re
import unicodedata

from app.core.config import ROOT_DIR
from app.services import ollama_service

log = logging.getLogger("instruction")


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()


NUM_WORDS = {"trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60, "quatre-vingt-dix": 90, "vingt": 20, "quinze": 15, "dix": 10}


def parse_rules(text: str) -> dict:
    t = _norm(text)
    out: dict = {}
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(s\b|sec|secondes?|seconds?)", t)
    if m:
        out["target_duration_s"] = float(m.group(1).replace(",", "."))
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(min\b|mn\b|minutes?)", t)
    if m:
        out["target_duration_s"] = float(m.group(1).replace(",", ".")) * 60 + out.get("target_duration_s", 0) if "target_duration_s" not in out else out["target_duration_s"]
    if "target_duration_s" not in out:
        for w, v in NUM_WORDS.items():
            if re.search(rf"\b{w}\s+secondes", t):
                out["target_duration_s"] = float(v)
                break
        if re.search(r"\bune\s+minute\b", t):
            out["target_duration_s"] = 60.0
    for key, pat in [("tiktok", r"tik\s*tok"), ("reels", r"reels?|instagram"), ("shorts", r"shorts?"), ("youtube", r"youtube")]:
        if re.search(pat, t):
            out["platform"] = "shorts" if key == "youtube" and re.search(r"shorts?", t) else key
            break

    def flag(name, pos, neg=None):
        if neg and re.search(neg, t):
            out[name] = False
        elif re.search(pos, t):
            out[name] = True

    flag("voiceover", r"voix[- ]?off|voiceover|narrat|commentaire audio", r"(sans|pas de|ni)\s+(de\s+)?voix")
    flag("subtitles", r"sous[- ]?titr|captions?|texte a l.ecran", r"(sans|pas de|ni)\s+(les\s+|de\s+)?sous[- ]?titr")
    flag("animated_subtitles", r"sous[- ]?titres? anime|texte anime|mot (a|par) mot|karaoke")
    flag("zooms", r"zoom", r"(sans|pas de|ni)\s+(de\s+)?zoom")
    flag("dynamic_transitions", r"transitions? (dynamique|rapide|energique|stylee)|dynamique")
    flag("music", r"musique|music|fond sonore", r"(sans|pas de|ni)\s+(de\s+)?musique")
    if re.search(r"musique[^.]{0,30}(discrete|douce|legere|faible|basse)|(discrete|douce|legere)[^.]{0,15}musique", t):
        out["music_level"] = "discrète"
    elif re.search(r"musique[^.]{0,20}(forte|puissante)", t):
        out["music_level"] = "forte"
    for tone, pat in [("éducatif", r"educati|pedagog|apprendre|tutoriel|cours"), ("dynamique", r"dynamique|energique|rythme"),
                      ("calme", r"calme|pose|doux"), ("humoristique", r"drole|humour|fun"), ("promotionnel", r"promo|publicit|vendre")]:
        if re.search(pat, t):
            out["tone"] = tone
            break
    if out.get("animated_subtitles"):
        out["subtitles"] = True
    return out


def parse(text: str, use_llm: bool = True) -> dict:
    rules = parse_rules(text or "")
    result = {"target_duration_s": None, "platform": None, "tone": None, "voiceover": False, "subtitles": True,
              "animated_subtitles": False, "zooms": False, "dynamic_transitions": False, "music": False,
              "music_level": None, "topic": None, "summary": (text or "").strip()[:300]}
    llm_info = {"used": False}
    if use_llm and (text or "").strip() and ollama_service.status()["model_ready"]:
        try:
            prompt = (ROOT_DIR / "ai" / "prompts" / "instruction_parser.md").read_text(encoding="utf-8") + text
            raw = json.loads(ollama_service.generate(prompt, as_json=True, timeout=180))
            for k in result:
                if k in raw and raw[k] not in (None, ""):
                    result[k] = raw[k]
            llm_info = {"used": True}
        except Exception as e:  # noqa: BLE001
            log.warning("Analyse LLM de la consigne échouée : %s", e)
            llm_info = {"used": False, "error": str(e)[:200]}
    result.update(rules)  # les règles explicites priment (fiables)
    if isinstance(result.get("target_duration_s"), (int, float)):
        result["target_duration_s"] = float(max(5, min(600, result["target_duration_s"])))
    else:
        result["target_duration_s"] = None
    if result.get("platform") not in ("tiktok", "reels", "shorts", "youtube"):
        result["platform"] = None
    result["_llm"] = llm_info
    result["_rules"] = sorted(rules)
    return result
