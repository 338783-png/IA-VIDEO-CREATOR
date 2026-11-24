"""Palette et caractéristiques colorimétriques (k-means simple en numpy)."""
import numpy as np


def kmeans(pixels: np.ndarray, k: int, iters: int = 12, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    px = pixels.astype(np.float32)
    rng = np.random.default_rng(seed)
    if len(px) <= k:
        return px, np.ones(len(px)) / max(1, len(px))
    # initialisation k-means++
    centers = [px[rng.integers(len(px))]]
    for _ in range(1, k):
        d = np.min(((px[:, None, :] - np.array(centers)[None]) ** 2).sum(-1), axis=1)
        centers.append(px[rng.choice(len(px), p=d / d.sum()) if d.sum() > 0 else rng.integers(len(px))])
    c = np.array(centers)
    for _ in range(iters):
        lab = np.argmin(((px[:, None, :] - c[None]) ** 2).sum(-1), axis=1)
        for j in range(k):
            sel = px[lab == j]
            if len(sel):
                c[j] = sel.mean(0)
    lab = np.argmin(((px[:, None, :] - c[None]) ** 2).sum(-1), axis=1)
    share = np.bincount(lab, minlength=k) / len(lab)
    order = np.argsort(-share)
    return c[order], share[order]


def to_hex(c) -> str:
    r, g, b = (int(np.clip(round(float(v)), 0, 255)) for v in c)
    return f"#{r:02X}{g:02X}{b:02X}"


def _merge_close(centers, shares, thr: float = 28.0):
    out: list[list] = []
    for c, s in zip(centers, shares):
        for o in out:
            if np.linalg.norm(o[0] - c) < thr:
                o[0] = (o[0] * o[1] + c * s) / (o[1] + s)
                o[1] += s
                break
        else:
            out.append([c.astype(np.float32), float(s)])
    out.sort(key=lambda x: -x[1])
    return out


def palette(pixels: np.ndarray, k: int = 6) -> list[dict]:
    if len(pixels) > 20000:
        pixels = pixels[np.random.default_rng(1).choice(len(pixels), 20000, replace=False)]
    c, s = kmeans(pixels, k)
    return [{"hex": to_hex(cc), "share": round(ss, 3)} for cc, ss in _merge_close(c, s) if ss >= 0.02]


def stats(pixels: np.ndarray) -> dict:
    px = pixels.astype(np.float32) / 255
    r, g, b = px[:, 0], px[:, 1], px[:, 2]
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    mx, mn = px.max(1), px.min(1)
    sat = np.where(mx > 0, (mx - mn) / (mx + 1e-6), 0)
    warm = float((r - b).mean())
    return {
        "brightness": round(float(luma.mean()), 3),
        "contrast": round(float(luma.std()), 3),
        "saturation": round(float(sat.mean()), 3),
        "warmth": round(warm, 3),
        "temperature": "chaude" if warm > 0.06 else "froide" if warm < -0.06 else "neutre",
    }


def describe(st: dict) -> list[str]:
    out = []
    out.append("lumineuse" if st["brightness"] > 0.6 else "sombre" if st["brightness"] < 0.3 else "luminosité moyenne")
    out.append("très saturée" if st["saturation"] > 0.5 else "saturée" if st["saturation"] > 0.3 else "désaturée" if st["saturation"] < 0.15 else "saturation modérée")
    out.append("contrastée" if st["contrast"] > 0.25 else "peu contrastée" if st["contrast"] < 0.12 else "contraste moyen")
    out.append(f"tonalité {st['temperature']}")
    return out
