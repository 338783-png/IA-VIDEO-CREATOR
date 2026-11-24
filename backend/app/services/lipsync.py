"""Synchronisation labiale commune 2D/3D : phonèmes français (alphabet phonétique) -> formes de bouche (visèmes).

Visèmes canoniques : rest (repos), MBP (lèvres fermées), A, E, I, O, U, FV (lèvre sur les dents), L (langue/consonnes).
Sources, de la plus précise à la plus simple :
  1. horaires de phonèmes (voix Piper) ;
  2. mots horodatés (Whisper) + phonétisation de chaque mot, phonèmes répartis dans le mot ;
  3. volume du son (repli : bouche plus ou moins ouverte).
Une couche d'adaptation par personnage (rig) traduit ensuite ces visèmes vers les formes disponibles.
"""
import re

import numpy as np

VISEMES = ["rest", "MBP", "A", "E", "I", "O", "U", "FV", "L"]
PHONEME_TO_VISEME = {
    "p": "MBP", "b": "MBP", "m": "MBP",
    "f": "FV", "v": "FV",
    "a": "A", "ɑ": "A",
    "e": "E", "ɛ": "E", "ə": "E", "ø": "E", "œ": "E", "ɜ": "E",
    "i": "I", "j": "I",
    "o": "O", "ɔ": "O",
    "u": "U", "w": "U", "ɥ": "U", "y": "U", "ʃ": "U", "ʒ": "U",
    "t": "L", "d": "L", "n": "L", "l": "L", "s": "L", "z": "L", "k": "L", "g": "L", "ɡ": "L",
    "ʁ": "L", "r": "L", "ɲ": "L", "ŋ": "L", "x": "L", "h": "L",
}
PAUSE = re.compile(r"^[\s,.;:!?…«»\"()\-—]+$")
MIN_SEG = 0.04      # durée minimale d'une forme de bouche (s) : un peu plus d'une image à 30 i/s
MIN_MBP = 0.035     # une fermeture de lèvres doit rester visible
ANTICIPATION = 0.03  # la bouche se forme légèrement avant le son


def viseme_of(phoneme: str) -> str | None:
    """Visème d'un phonème ; None pour les marques (accent, durée, nasalisation) qui prolongent le précédent."""
    p = phoneme.strip()
    if not p:
        return None
    if p in PHONEME_TO_VISEME:
        return PHONEME_TO_VISEME[p]
    base = p[0]
    return PHONEME_TO_VISEME.get(base)


def _merge(segs: list[dict]) -> list[dict]:
    out: list[dict] = []
    for s in segs:
        if s["end"] - s["start"] <= 1e-4:
            continue
        if out and out[-1]["viseme"] == s["viseme"] and abs(out[-1]["end"] - s["start"]) < 1e-3:
            out[-1]["end"] = s["end"]
        else:
            out.append(dict(s))
    return out


def _min_duration(segs: list[dict]) -> list[dict]:
    """Évite le scintillement sans perdre de sons :
    - un segment trop bref est fusionné avec un voisin qui n'est PAS une fermeture de lèvres ;
    - s'il est entouré de fermetures (ex. « m-a-p »), il prend du temps aux fermetures, qui gardent au moins MIN_MBP.
    """
    segs = _merge(segs)
    i = 0
    while i < len(segs) and len(segs) > 1:
        s = segs[i]
        d = s["end"] - s["start"]
        need = MIN_MBP if s["viseme"] == "MBP" else MIN_SEG
        if d >= need:
            i += 1
            continue
        prev = segs[i - 1] if i > 0 else None
        nxt = segs[i + 1] if i + 1 < len(segs) else None
        # 1) voler du temps à un voisin assez long (en priorité une fermeture, qui garde MIN_MBP)
        stolen = False
        for nb, side in ((prev, -1), (nxt, 1)):
            if nb is None:
                continue
            floor = MIN_MBP if nb["viseme"] == "MBP" else MIN_SEG
            spare = (nb["end"] - nb["start"]) - floor
            if spare > 0:
                take = min(spare, need - (s["end"] - s["start"]))
                if side < 0:
                    nb["end"] -= take
                    s["start"] -= take
                else:
                    nb["start"] += take
                    s["end"] += take
                stolen = True
                if s["end"] - s["start"] >= need - 1e-6:
                    break
        if s["end"] - s["start"] >= need - 1e-6:
            i += 1
            continue
        # 2) sinon fusion avec un voisin non-fermeture (jamais une voyelle avalée par MBP)
        cands = [(nb, side) for nb, side in ((prev, -1), (nxt, 1)) if nb is not None and (nb["viseme"] != "MBP" or s["viseme"] == "MBP")]
        if not cands:
            i += 1  # entouré de fermetures sans marge : on le garde tel quel
            continue
        nb, side = cands[0]
        if side < 0:
            nb["end"] = s["end"]
        else:
            nb["start"] = s["start"]
        segs.pop(i)
        segs = _merge(segs)
        i = max(0, i - 1)
        _ = stolen
    return segs


def track_from_phonemes(phonemes: list[dict], pause_min: float = 0.08) -> list[dict]:
    """phonemes : [{p, start, end}] (horaires Piper). Retourne [{viseme, start, end}]."""
    segs: list[dict] = []
    for ph in phonemes:
        p, s, e = ph["p"], float(ph["start"]), float(ph["end"])
        if PAUSE.match(p):
            if e - s >= pause_min:
                segs.append({"viseme": "rest", "start": s, "end": e})
            elif segs:
                segs[-1]["end"] = e
            continue
        v = viseme_of(p)
        if v is None:  # marque phonétique : prolonge le son précédent
            if segs:
                segs[-1]["end"] = e
            continue
        segs.append({"viseme": v, "start": s, "end": e})
    for s in segs:
        s["start"] = max(0.0, s["start"] - ANTICIPATION)
        s["end"] = max(s["start"], s["end"] - ANTICIPATION)
    return [{"viseme": s["viseme"], "start": round(s["start"], 3), "end": round(s["end"], 3)} for s in _min_duration(segs)]


def track_from_words(words: list[dict], phonemize) -> list[dict]:
    """Mots horodatés (Whisper) : chaque mot est phonétisé, ses phonèmes répartis sur sa durée.

    phonemize(texte) -> liste de phonèmes (ex. via la phonétisation de Piper).
    """
    phons = []
    for i, w in enumerate(words):
        ps = [p for p in phonemize(w["word"]) if not PAUSE.match(p) and viseme_of(p)]
        if not ps:
            continue
        d = (w["end"] - w["start"]) / len(ps)
        phons += [{"p": p, "start": w["start"] + k * d, "end": w["start"] + (k + 1) * d} for k, p in enumerate(ps)]
        nxt = words[i + 1]["start"] if i + 1 < len(words) else None
        if nxt is not None and nxt - w["end"] >= 0.08:
            phons.append({"p": " ", "start": w["end"], "end": nxt})
    return track_from_phonemes(phons)


def track_from_audio(samples: np.ndarray, sr: int, hop: float = 0.04) -> list[dict]:
    """Repli sans texte : ouverture de la bouche selon le volume (silence = repos)."""
    n = int(sr * hop)
    if len(samples) < n:
        return []
    k = len(samples) // n
    rms = np.sqrt((samples[: k * n].reshape(k, n).astype(np.float64) ** 2).mean(1) + 1e-12)
    db = 20 * np.log10(rms)
    loud = np.percentile(db, 95)
    segs = []
    for i, v in enumerate(db):
        rel = v - loud
        vis = "rest" if rel < -30 else "E" if rel < -14 else "A" if rel > -6 else "O"
        segs.append({"viseme": vis, "start": i * hop, "end": (i + 1) * hop})
    return [{"viseme": s["viseme"], "start": round(s["start"], 3), "end": round(s["end"], 3)} for s in _min_duration(segs)]


def viseme_at(track: list[dict], t: float) -> str:
    """Forme de bouche à l'instant t (recherche dichotomique)."""
    lo, hi = 0, len(track) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        s = track[mid]
        if t < s["start"]:
            hi = mid - 1
        elif t >= s["end"]:
            lo = mid + 1
        else:
            return s["viseme"]
    return "rest"


CLOSED_NAMES = {"rest", "mbp", "closed", "close", "neutral", "sil", "silence", "ferme", "fermee"}


def adapt(viseme: str, available: list[str]) -> str:
    """Couche d'adaptation : visème canonique -> forme disponible sur un personnage donné (2D ou 3D).

    Si la forme n'existe pas, on prend la plus proche visuellement ; à défaut, ouverte/fermée.
    """
    if viseme in available:
        return viseme
    nearest = {"MBP": ["rest"], "FV": ["E", "MBP", "rest"], "A": ["O", "E"], "E": ["A", "I"], "I": ["E", "A"],
               "O": ["U", "A"], "U": ["O", "A"], "L": ["E", "A"], "rest": ["MBP"]}
    for cand in nearest.get(viseme, []):
        if cand in available:
            return cand
    closed = [v for v in available if v.lower() in CLOSED_NAMES]
    opened = [v for v in available if v.lower() not in CLOSED_NAMES]
    if viseme in ("rest", "MBP"):
        return closed[0] if closed else (available[0] if available else "rest")
    return opened[0] if opened else (available[0] if available else "rest")
