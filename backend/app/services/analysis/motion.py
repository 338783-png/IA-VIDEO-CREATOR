"""Estimation des mouvements de caméra/animations par plan : zoom, panoramique, tremblement."""
import numpy as np


def _warp_scale(img: np.ndarray, s: float, dx: float = 0.0, dy: float = 0.0) -> np.ndarray:
    """Zoom centré de facteur s (s>1 = zoom avant), échantillonnage bilinéaire."""
    h, w = img.shape
    cy, cx = (h - 1) / 2, (w - 1) / 2
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    sy = np.clip(cy + (ys - cy) / s - dy, 0, h - 1.001)
    sx = np.clip(cx + (xs - cx) / s - dx, 0, w - 1.001)
    y0, x0 = sy.astype(np.int32), sx.astype(np.int32)
    fy, fx = sy - y0, sx - x0
    a, b = img[y0, x0], img[y0, x0 + 1]
    c, d = img[y0 + 1, x0], img[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def _phase_shift(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    fa, fb = np.fft.fft2(a - a.mean()), np.fft.fft2(b - b.mean())
    r = fb * np.conj(fa)
    r /= np.abs(r) + 1e-9
    corr = np.abs(np.fft.ifft2(r))
    py, px = np.unravel_index(np.argmax(corr), corr.shape)
    h, w = a.shape
    if py > h // 2:
        py -= h
    if px > w // 2:
        px -= w
    return float(px), float(py)


def _crop(img: np.ndarray, m: float = 0.12) -> np.ndarray:
    h, w = img.shape
    return img[int(h * m):int(h * (1 - m)), int(w * m):int(w * (1 - m))]


def _err(a: np.ndarray, b: np.ndarray, s: float, dx: float, dy: float) -> float:
    return float(np.abs(_crop(_warp_scale(a, s, dx, dy)) - _crop(b)).mean())


def pair_motion(a: np.ndarray, b: np.ndarray) -> dict:
    """Meilleur modèle (zoom centré, translation) expliquant b à partir de a."""
    a, b = a.astype(np.float32), b.astype(np.float32)
    base_err = float(np.abs(_crop(a) - _crop(b)).mean())
    pdx, pdy = _phase_shift(a, b)
    best = (base_err, 1.0, 0.0, 0.0)
    # hypothèse translation pure (phase) puis zoom avec/sans translation
    for dx, dy in {(0.0, 0.0), (pdx, pdy)}:
        e = _err(a, b, 1.0, dx, dy)
        if e < best[0]:
            best = (e, 1.0, dx, dy)
    for s in np.arange(0.90, 1.1001, 0.005):
        if abs(s - 1) < 1e-6:
            continue
        for dx, dy in {(0.0, 0.0), (pdx, pdy)}:
            e = _err(a, b, float(s), dx, dy)
            if e < best[0]:
                best = (e, float(s), dx, dy)
    # affinage fin autour de l'échelle retenue (sans translation parasite)
    if best[1] != 1.0:
        for s in np.arange(best[1] - 0.004, best[1] + 0.0041, 0.001):
            e = _err(a, b, float(s), best[2], best[3])
            if e < best[0]:
                best = (e, float(s), best[2], best[3])
    err, scale, dx, dy = best
    return {"scale": scale, "dx": dx, "dy": dy, "base_err": base_err, "err": err}


def shot_motion(grays: list[np.ndarray], start: int, end: int, fps: float) -> dict:
    """grays : images en niveaux de gris de petite taille ; [start, end] inclusifs."""
    length = end - start + 1
    if length < max(4, int(fps * 0.3)):
        return {"type": "trop_court", "zoom_total": 1.0, "pan": [0.0, 0.0], "intensity": 0.0, "confidence": "faible"}
    n_samples = int(min(10, max(3, length / (fps * 0.3))))
    idx = np.linspace(start, end, n_samples).round().astype(int)
    h, w = grays[start].shape
    scale_total, pan_x, pan_y, shifts, improvements, diffs = 1.0, 0.0, 0.0, [], [], []
    for i0, i1 in zip(idx[:-1], idx[1:]):
        m = pair_motion(grays[i0], grays[i1])
        scale_total *= m["scale"]
        pan_x += m["dx"]
        pan_y += m["dy"]
        shifts.append((m["dx"], m["dy"]))
        diffs.append(m["base_err"])
        if m["base_err"] > 0.5:
            improvements.append(1 - m["err"] / m["base_err"])
    intensity = float(np.mean(diffs) / 255) if diffs else 0.0
    explained = float(np.mean(improvements)) if improvements else 0.0
    duration = length / fps
    pan_pct = [round(100 * pan_x / w, 1), round(100 * pan_y / h, 1)]
    sh = np.array(shifts) if shifts else np.zeros((1, 2))
    jitter = float(np.std(sh[:, 0]) / w + np.std(sh[:, 1]) / h) * 100

    if intensity < 0.004:
        kind = "statique"
    elif scale_total > 1.04 and explained > 0.3:
        kind = "zoom_avant"
    elif scale_total < 0.96 and explained > 0.3:
        kind = "zoom_arriere"
    elif max(abs(pan_pct[0]), abs(pan_pct[1])) > 6 and explained > 0.3:
        kind = "panoramique"
    elif jitter > 2.5 and explained > 0.2:
        kind = "tremblement"
    else:
        kind = "mouvement_interne"  # mouvement dans l'image (sujet), sans mouvement de cadre identifié
    conf = "moyenne" if explained > 0.5 else "faible"
    if kind == "statique":
        conf, pan_pct, scale_total = "élevée", [0.0, 0.0], 1.0
    return {
        "type": kind,
        "zoom_total": round(scale_total, 3),
        "zoom_per_second": round((scale_total - 1) / duration, 4) if duration else 0.0,
        "pan": pan_pct,
        "intensity": round(intensity, 4),
        "jitter": round(jitter, 2),
        "explained": round(explained, 2),
        "confidence": conf,
    }


MOTION_LABELS = {
    "statique": "Plan fixe",
    "zoom_avant": "Zoom avant",
    "zoom_arriere": "Zoom arrière",
    "panoramique": "Panoramique / glissement",
    "tremblement": "Tremblement / caméra à l'épaule",
    "mouvement_interne": "Mouvement dans l'image",
    "trop_court": "Plan trop court pour mesurer",
}
