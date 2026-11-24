"""Détection des plans : coupes franches et transitions progressives (fondus)."""
import numpy as np


def hist(rgb: np.ndarray, bins: int = 16) -> np.ndarray:
    q = (rgb.reshape(-1, 3) // (256 // bins)).astype(np.int32)
    h = np.concatenate([np.bincount(q[:, c], minlength=bins) for c in range(3)]).astype(np.float32)
    return h / h.sum()


def hist_dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(0.5 * np.abs(a - b).sum() / 3)  # 0..1


def frame_change(g_prev, g, h_prev, h) -> float:
    d = float(np.abs(g - g_prev).mean() / 255.0)
    return 0.5 * min(1.0, d * 4) + 0.5 * hist_dist(h_prev, h)


def _local_median(x: np.ndarray, i: int, r: int) -> float:
    lo, hi = max(0, i - r), min(len(x), i + r + 1)
    w = np.concatenate([x[lo:i], x[i + 1:hi]])
    return float(np.median(w)) if len(w) else 0.0


def detect_cuts(change: np.ndarray, fps: float) -> list[int]:
    """Indices t où un nouveau plan commence (coupe franche entre t-1 et t)."""
    r = max(5, int(fps / 2))
    cuts = []
    for t in range(1, len(change)):
        c = change[t]
        if c > 0.25 and c > 3 * _local_median(change, t, r) + 0.06:
            if not cuts or t - cuts[-1] >= max(3, int(fps * 0.15)):
                cuts.append(t)
    return cuts


def _blend_residual(a, m, b) -> float:
    """Écart entre M et la meilleure combinaison alpha*A + (1-alpha)*B (0 = fondu parfait)."""
    a, m, b = a.astype(np.float32).ravel(), m.astype(np.float32).ravel(), b.astype(np.float32).ravel()
    d = a - b
    denom = float((d * d).sum()) or 1.0
    alpha = float(np.clip(((m - b) * d).sum() / denom, 0, 1))
    fit = alpha * a + (1 - alpha) * b
    return float(np.abs(m - fit).mean() / (np.abs(d).mean() + 1e-6))


def detect_dips(rgbs: list[np.ndarray], luma: np.ndarray, fps: float) -> list[dict]:
    """Fondus au noir / flashs blancs : creux (ou pic) de luminosité encadré de contenu différent."""
    n = len(luma)
    out = []
    for kind, extreme in (("fade_black", lambda v: v < 0.06), ("flash_white", lambda v: v > 0.94)):
        t = 0
        while t < n:
            if not extreme(luma[t]):
                t += 1
                continue
            s = t
            while t < n and extreme(luma[t]):
                t += 1
            e = t - 1
            if s == 0 or e == n - 1 or (e - s + 1) > fps * 1.5:
                continue  # début/fin de vidéo ou plan entièrement noir : pas une transition
            # étend la zone tant que la luminosité continue de varier vers l'extrême
            sign = 1 if kind == "fade_black" else -1
            step = 0.008  # variation minimale par image pour être considérée comme partie du fondu
            a = s
            while a > 0 and sign * (luma[a - 1] - luma[a]) > step and s - a < fps:
                a -= 1
            b = e
            while b < n - 1 and sign * (luma[b + 1] - luma[b]) > step and b - e < fps:
                b += 1
            before, after = luma[max(0, a - 1)], luma[min(n - 1, b + 1)]
            if kind == "fade_black" and min(before, after) < 0.12:
                continue
            if kind == "flash_white" and max(before, after) > 0.85:
                continue
            out.append({"start_frame": int(a), "end_frame": int(b), "boundary_frame": int((s + e) // 2), "type": kind,
                        "duration": round((b - a + 1) / fps, 3), "confidence": "élevée"})
    return out


def detect_gradual(grays: list[np.ndarray], rgbs: list[np.ndarray], change: np.ndarray, luma: np.ndarray,
                   cuts: list[int], fps: float) -> list[dict]:
    n = len(grays)
    k = max(3, int(round(fps * 0.25)))
    if n < 2 * k + 3:
        return []
    hists = [hist(x) for x in rgbs]
    long = np.zeros(n)
    for t in range(k, n - k):
        long[t] = 0.5 * min(1.0, np.abs(grays[t + k] - grays[t - k]).mean() / 255 * 4) + 0.5 * hist_dist(hists[t - k], hists[t + k])
    cutset = set(cuts)
    dips = detect_dips(rgbs, luma, fps)
    busy = set()
    for d in dips:
        busy.update(range(d["start_frame"] - k, d["end_frame"] + k + 1))
    cand = [t for t in range(k, n - k) if long[t] > 0.3 and t not in busy and not any(abs(t - c) <= k + 1 for c in cutset)]
    # regroupe les candidats contigus
    regions, cur = [], []
    for t in cand:
        if cur and t - cur[-1] > 1:
            regions.append(cur)
            cur = []
        cur.append(t)
    if cur:
        regions.append(cur)

    out = list(dips)
    for reg in regions:
        if len(reg) < 2:
            continue
        lo, hi = max(1, reg[0] - k), min(n - 1, reg[-1] + k)
        win = change[lo:hi + 1]
        peak = float(win.max())
        base = float(np.median(change)) if len(change) else 0.0
        thr = max(0.3 * peak, base + 0.004)
        idx = [lo + i for i, v in enumerate(win) if v >= thr]
        if not idx:
            continue
        s, e = idx[0], idx[-1]
        a_i, b_i = max(0, s - 1), min(n - 1, e + 1)
        if hist_dist(hists[a_i], hists[b_i]) < 0.2:
            continue  # même contenu avant/après : mouvement de caméra, pas une transition
        span = e - s + 1
        if span > fps * 2.5:
            continue
        mid = (s + e) // 2
        conf = "moyenne"
        res = _blend_residual(grays[a_i], grays[mid], grays[b_i])
        if res < 0.35:
            kind = "crossfade"
        else:
            kind, conf = "animated", "faible"  # glissement / balayage / masque probable
        out.append({"start_frame": s, "end_frame": e, "boundary_frame": mid, "type": kind,
                    "duration": round(span / fps, 3), "confidence": conf})
    out.sort(key=lambda x: x["boundary_frame"])
    return out


TRANSITION_LABELS = {
    "cut": "Coupe franche",
    "crossfade": "Fondu enchaîné",
    "fade_black": "Fondu au noir",
    "flash_white": "Flash blanc",
    "animated": "Transition animée (glissement/balayage probable)",
}
