"""Détection heuristique des textes incrustés (sous-titres) : position, couleur, cadence.

Principe : un sous-titre « réseaux sociaux » = pixels très clairs (ou saturés) bordés de pixels très
sombres (contour/ombre), concentrés dans une bande horizontale stable, dont le contenu change
indépendamment des coupes. La police n'est PAS identifiable par cette méthode.
"""
import numpy as np

from app.services.analysis.colors import to_hex

BANDS = 24


def _any_shift(m: np.ndarray, axis: int, r: int, sign: int) -> np.ndarray:
    out = np.zeros_like(m)
    for k in range(1, r + 1):
        sh = np.roll(m, sign * k, axis)
        # annule l'effet d'enroulement de np.roll
        if axis == 1:
            if sign > 0:
                sh[:, :k] = False
            else:
                sh[:, -k:] = False
        else:
            if sign > 0:
                sh[:k] = False
            else:
                sh[-k:] = False
        out |= sh
    return out


def text_mask(rgb: np.ndarray, r: int = 4) -> np.ndarray:
    """Pixels de trait clair encadrés de noir des deux côtés (lettre à contour)."""
    rgb = rgb.astype(np.float32)
    g = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = (mx - mn) / (mx + 1e-6)
    fill = (g > 200) | ((sat > 0.55) & (mx > 200))  # blanc, jaune, couleurs vives
    dark = mx < 70  # contour réellement noir (pas un bleu saturé)
    horiz = _any_shift(dark, 1, r, 1) & _any_shift(dark, 1, r, -1)
    vert = _any_shift(dark, 0, r, 1) & _any_shift(dark, 0, r, -1)
    return fill & (horiz | vert)


def analyze(frames: list[np.ndarray], times: list[float], cut_times: list[float]) -> dict:
    if not frames:
        return {"detected": False, "confidence": "faible", "reason": "aucune image"}
    h, w = frames[0].shape[:2]
    masks = [text_mask(f) for f in frames]
    band_h = h / BANDS
    dens = np.array([[m[int(i * band_h):int((i + 1) * band_h)].mean() for i in range(BANDS)] for m in masks])
    med_band = np.median(dens, axis=0)  # densité médiane dans le temps, par bande
    presence_band = (dens > 0.004).mean(axis=0)
    score = med_band * presence_band
    peak = int(np.argmax(score))
    others = np.delete(score, peak)
    ratio = float(score[peak] / (np.median(others) + 1e-5))
    if score[peak] < 0.0015 or ratio < 3:
        return {"detected": False, "confidence": "moyenne", "reason": "aucune zone de texte contrastée stable détectée",
                "method": "heuristique pixels clairs à contour sombre"}

    # étend la zone autour du pic
    lo = hi = peak
    while lo > 0 and score[lo - 1] > 0.3 * score[peak]:
        lo -= 1
    while hi < BANDS - 1 and score[hi + 1] > 0.3 * score[peak]:
        hi += 1
    y0, y1 = int(lo * band_h), int((hi + 1) * band_h)
    center = (y0 + y1) / 2 / h
    position = "haut" if center < 0.33 else "bas" if center > 0.62 else "centre"

    region = [m[y0:y1] for m in masks]
    present = np.array([r.mean() > 0.003 for r in region])
    coverage = float(present.mean())

    # couleur de remplissage et de contour, largeur moyenne
    fills, outlines, widths = [], [], []
    for f, m, p in zip(frames, masks, present):
        if not p:
            continue
        rm = m[y0:y1]
        px = f[y0:y1][rm]
        if len(px):
            fills.append(np.median(px, axis=0))
        cols = np.where(rm.any(0))[0]
        if len(cols):
            widths.append((cols[-1] - cols[0] + 1) / w)
        dark = f[y0:y1][(f[y0:y1].max(-1) < 70) & _near(rm)]
        if len(dark):
            outlines.append(np.median(dark, axis=0))
    fill_hex = to_hex(np.median(fills, axis=0)) if fills else None
    outline_hex = to_hex(np.median(outlines, axis=0)) if outlines else None

    # cadence : changements du contenu texte (hors coupes)
    changes = []
    for i in range(1, len(region)):
        if not (present[i] or present[i - 1]):
            continue
        a, b = region[i - 1], region[i]
        union = (a | b).sum()
        iou = (a & b).sum() / union if union else 1.0
        near_cut = any(abs(times[i] - c) < 0.2 for c in cut_times)
        if iou < 0.5 and not near_cut:
            changes.append(times[i])
    total = times[-1] - times[0] if len(times) > 1 else 0
    shown_time = coverage * total
    interval = round(shown_time / (len(changes) + 1), 2) if changes else None
    if interval is None:
        mode = "texte fixe"
    elif interval < 0.6:
        mode = "mot par mot (ou 1-2 mots)"
    elif interval < 1.6:
        mode = "groupes de mots courts"
    else:
        mode = "phrases complètes"
    conf = "moyenne" if ratio > 8 and coverage > 0.3 else "faible"
    return {
        "detected": True,
        "position": position,
        "vertical_center_pct": round(center * 100, 1),
        "region_pct": [round(y0 / h * 100, 1), round(y1 / h * 100, 1)],
        "avg_width_pct": round(float(np.mean(widths)) * 100, 1) if widths else None,
        "fill_color": fill_hex,
        "outline_color": outline_hex,
        "coverage": round(coverage, 2),
        "change_interval_s": interval,
        "changes_count": len(changes),
        "mode": mode,
        "font": None,
        "font_note": "Police non identifiable de façon fiable par analyse d'image.",
        "confidence": conf,
        "method": "heuristique pixels clairs à contour sombre",
    }


def _near(mask: np.ndarray, r: int = 2) -> np.ndarray:
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= np.roll(np.roll(mask, dy, 0), dx, 1)
    return out & ~mask
