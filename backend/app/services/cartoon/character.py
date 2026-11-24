"""Personnages 2D « vidéo explicative » dessinés par l'application (créations originales).

Le personnage est un assemblage de pièces : jambes, buste, bras (pivot à l'épaule), tête (pivot au cou).
Corps et bras sont dessinés une fois ; la tête dépend de l'expression (yeux, sourcils, bouche) et est mise en cache.
Coordonnées internes : personnage de 1000 unités de haut, dessiné en sur-échantillonnage puis réduit (anti-crénelage).
"""
from dataclasses import dataclass, field
from functools import lru_cache
import json
import math

from PIL import Image, ImageDraw

SS = 3  # sur-échantillonnage
HAIR_STYLES = ["court", "long", "chignon", "boucle", "chauve"]
BODIES = {"fin": 0.85, "moyen": 1.0, "fort": 1.2}
EMOTIONS = ["neutre", "joie", "surprise", "tristesse", "colere", "reflexion"]
VISEMES = ["rest", "MBP", "A", "E", "I", "O", "U", "FV", "L"]
DEFAULT = {
    "skin": "#F1C9A5", "hair_style": "court", "hair_color": "#3B2A20", "eye_color": "#3A2A1A",
    "shirt_color": "#5B6CFF", "pants_color": "#2B3245", "shoe_color": "#1E1E24", "glasses": False,
    "body": "moyen", "height": 1.0, "accessory": "aucun", "accent_color": "#FFB020",
}


def validate_params(p: dict) -> dict:
    out = dict(DEFAULT)
    for k, v in (p or {}).items():
        if k not in DEFAULT:
            continue
        if k.endswith("_color") or k == "skin":
            v = str(v).upper()
            if not (len(v) == 7 and v[0] == "#" and all(ch in "0123456789ABCDEF" for ch in v[1:])):
                raise ValueError(f"Couleur invalide pour {k}")
        elif k == "hair_style" and v not in HAIR_STYLES:
            raise ValueError("Coiffure inconnue")
        elif k == "body" and v not in BODIES:
            raise ValueError("Silhouette inconnue")
        elif k == "height":
            v = max(0.8, min(1.15, float(v)))
        elif k == "glasses":
            v = bool(v)
        elif k == "accessory" and v not in ("aucun", "cravate", "noeud", "collier"):
            raise ValueError("Accessoire inconnu")
        out[k] = v
    return out


def _rgb(h: str, a: int = 255) -> tuple:
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), a)


def _shade(h: str, f: float) -> str:
    r, g, b = (max(0, min(255, int(int(h[i:i + 2], 16) * f))) for i in (1, 3, 5))
    return f"#{r:02X}{g:02X}{b:02X}"


@dataclass(frozen=True)
class Pose:
    """État d'animation d'une image."""
    emotion: str = "neutre"
    viseme: str = "rest"
    eyes: float = 1.0          # 1 ouvert, 0 fermé
    look: float = 0.0          # -1 gauche … 1 droite
    head_tilt: float = 0.0     # degrés
    head_dy: float = 0.0       # unités (hochement)
    arm_l: float = 0.0         # degrés (0 = bras le long du corps, positif = levé vers l'extérieur)
    arm_r: float = 0.0
    breath: float = 0.0        # 0..1
    facing: int = 1            # 1 vers la droite, -1 vers la gauche


@dataclass
class Character:
    params: dict = field(default_factory=lambda: dict(DEFAULT))

    def key(self) -> str:
        return json.dumps(self.params, sort_keys=True)


# ------------------------------------------------------------------------------------------- tête
@lru_cache(maxsize=4096)
def head_sprite(pkey: str, emotion: str, viseme: str, eyes_q: int, look_q: int) -> Image.Image:
    p = json.loads(pkey)
    W, H = 360, 420
    im = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    s = SS

    def E(box, **kw):
        d.ellipse([v * s for v in box], **kw)

    def P(pts, **kw):
        d.polygon([(x * s, y * s) for x, y in pts], **kw)

    def L(pts, width, **kw):
        d.line([(x * s, y * s) for x, y in pts], width=int(width * s), joint="curve", **kw)

    def A(box, a0, a1, width, **kw):
        d.arc([v * s for v in box], a0, a1, width=int(width * s), **kw)

    skin, hair = p["skin"], p["hair_color"]
    cx, cy = 180, 225
    # cheveux arrière
    if p["hair_style"] == "long":  # dessus + deux longues mèches sur les côtés (rien sous le menton)
        E([66, 88, 294, 330], fill=_rgb(hair))
        d.rounded_rectangle([62 * s, 190 * s, 128 * s, 410 * s], radius=30 * s, fill=_rgb(hair))
        d.rounded_rectangle([232 * s, 190 * s, 298 * s, 410 * s], radius=30 * s, fill=_rgb(hair))
    elif p["hair_style"] == "boucle":
        for ang in range(0, 360, 30):
            x, y = cx + 120 * math.cos(math.radians(ang)), cy - 20 + 125 * math.sin(math.radians(ang))
            E([x - 48, y - 48, x + 48, y + 48], fill=_rgb(hair))
    # oreilles + visage
    E([52, 205, 92, 265], fill=_rgb(_shade(skin, 0.93)))
    E([268, 205, 308, 265], fill=_rgb(_shade(skin, 0.93)))
    E([70, 95, 290, 365], fill=_rgb(skin))
    # cheveux avant
    hs = p["hair_style"]
    if hs in ("court", "long", "chignon"):
        P([(72, 210), (80, 140), (120, 100), (180, 88), (240, 100), (282, 140), (290, 210), (262, 160), (200, 140), (140, 150), (98, 175)], fill=_rgb(hair))
        if hs == "chignon":
            E([140, 30, 220, 110], fill=_rgb(hair))
    elif hs == "boucle":
        for x in range(92, 280, 34):
            E([x - 30, 88, x + 30, 150], fill=_rgb(hair))
    # yeux
    eo = eyes_q / 4  # 0..1
    lk = (look_q - 2) / 2  # -1..1
    surprise = emotion == "surprise"
    eh = (28 if surprise else 22) * max(0.08, eo)
    for ex in (135, 225):
        if eo < 0.15:
            L([(ex - 18, 232), (ex + 18, 232)], 4, fill=_rgb("#2A1E18"))
        else:
            E([ex - 19, 232 - eh, ex + 19, 232 + eh], fill=(255, 255, 255, 255))
            pr = min(11, eh * 0.75)
            px = ex + lk * 7
            E([px - pr, 232 - pr, px + pr, 232 + pr], fill=_rgb(p["eye_color"]))
            E([px - pr * 0.45, 232 - pr * 0.45, px + pr * 0.45, 232 + pr * 0.45], fill=(15, 12, 10, 255))
            E([px + 2, 226, px + 6, 230], fill=(255, 255, 255, 230))
    # sourcils selon l'émotion
    brow = {"neutre": (0, 0), "joie": (-4, 4), "surprise": (-14, 0), "tristesse": (2, -10),
            "colere": (4, 12), "reflexion": (-6, -6)}[emotion]
    for sgn, ex in ((-1, 135), (1, 225)):
        y, tilt = 196 + brow[0], brow[1]  # tilt > 0 : côté intérieur abaissé (colère) ; < 0 : relevé (tristesse)
        inner_y, outer_y = y + tilt / 2, y - tilt / 2
        pts = [(ex - 20, outer_y), (ex + 20, inner_y)] if sgn < 0 else [(ex - 20, inner_y), (ex + 20, outer_y)]
        L(pts, 6, fill=_rgb(_shade(hair, 0.85)))
    # nez
    A([168, 245, 192, 280], 20, 160, 3, fill=_rgb(_shade(skin, 0.75)))
    # joues
    if emotion == "joie":
        E([98, 268, 128, 288], fill=_rgb("#FF8C8C", 90))
        E([232, 268, 262, 288], fill=_rgb("#FF8C8C", 90))
    # bouche (visème + émotion)
    mx, my = 180, 312
    lip, inner, teeth = _rgb("#7A2E2E"), _rgb("#5A1A1E"), (255, 255, 255, 255)
    curve = {"joie": 10, "tristesse": -8, "colere": -4}.get(emotion, 2)
    if viseme in ("rest", "MBP"):
        if emotion == "joie" and viseme == "rest":
            A([mx - 32, my - 26, mx + 32, my + 14], 15, 165, 5, fill=lip)
        elif curve < 0:
            A([mx - 26, my, mx + 26, my + 28], 200, 340, 5, fill=lip)
        else:
            L([(mx - 24, my), (mx, my + curve / 2), (mx + 24, my)], 5 if viseme == "rest" else 7, fill=lip)
    else:
        w, h = {"A": (30, 26), "E": (32, 15), "I": (34, 9), "O": (19, 22), "U": (13, 14), "FV": (26, 8), "L": (24, 14)}[viseme]
        E([mx - w, my - h * 0.55, mx + w, my + h], fill=inner, outline=lip, width=3 * s)
        if viseme in ("A", "E", "I", "FV", "L"):
            d.rectangle([(mx - w * 0.7) * s, (my - h * 0.45) * s, (mx + w * 0.7) * s, (my - h * 0.45 + min(7, h * 0.4)) * s], fill=teeth)
        if viseme in ("A", "L"):
            E([mx - w * 0.45, my + h * 0.35, mx + w * 0.45, my + h * 0.9], fill=_rgb("#D9666E"))
    # lunettes
    if p["glasses"]:
        for ex in (135, 225):
            d.rounded_rectangle([(ex - 30) * s, 210 * s, (ex + 30) * s, 254 * s], radius=12 * s, outline=(30, 30, 40, 255), width=4 * s)
        L([(165, 228), (195, 228)], 4, fill=(30, 30, 40, 255))
    return im.resize((W, H), Image.LANCZOS)


# ------------------------------------------------------------------------------------------- corps
@lru_cache(maxsize=256)
def body_sprite(pkey: str) -> Image.Image:
    p = json.loads(pkey)
    bw = BODIES[p["body"]]
    W, H = 520, 680
    im = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    s = SS
    cx = W / 2
    tw = 150 * bw  # demi-largeur des épaules
    # jambes et chaussures
    for sx in (-1, 1):
        x = cx + sx * 48 * bw
        d.rounded_rectangle([(x - 40 * bw) * s, 360 * s, (x + 40 * bw) * s, 640 * s], radius=26 * s, fill=_rgb(p["pants_color"]))
        d.ellipse([(x - 52 + sx * 10) * s, 615 * s, (x + 52 + sx * 10) * s, 670 * s], fill=_rgb(p["shoe_color"]))
    # cou
    d.rounded_rectangle([(cx - 30) * s, 0, (cx + 30) * s, 70 * s], radius=14 * s, fill=_rgb(_shade(p["skin"], 0.9)))
    # buste
    d.rounded_rectangle([(cx - tw) * s, 40 * s, (cx + tw) * s, 400 * s], radius=int(70 * bw) * s, fill=_rgb(p["shirt_color"]))
    d.polygon([((cx - 34) * s, 40 * s), (cx * s, 92 * s), ((cx + 34) * s, 40 * s)], fill=_rgb(_shade(p["skin"], 0.9)))
    acc = p["accessory"]
    if acc == "cravate":
        d.polygon([(cx * s, 92 * s), ((cx - 16) * s, 120 * s), ((cx - 8) * s, 260 * s), (cx * s, 280 * s), ((cx + 8) * s, 260 * s), ((cx + 16) * s, 120 * s)], fill=_rgb(p["accent_color"]))
    elif acc == "noeud":
        d.polygon([((cx - 40) * s, 70 * s), (cx * s, 90 * s), ((cx - 40) * s, 110 * s)], fill=_rgb(p["accent_color"]))
        d.polygon([((cx + 40) * s, 70 * s), (cx * s, 90 * s), ((cx + 40) * s, 110 * s)], fill=_rgb(p["accent_color"]))
    elif acc == "collier":
        d.arc([(cx - 60) * s, 20 * s, (cx + 60) * s, 130 * s], 20, 160, width=6 * s, fill=_rgb(p["accent_color"]))
    return im.resize((W, H), Image.LANCZOS)


@lru_cache(maxsize=256)
def arm_sprite(pkey: str) -> Image.Image:
    """Bras vertical, pivot (épaule) en haut au centre."""
    p = json.loads(pkey)
    bw = BODIES[p["body"]]
    W, H = 110, 360
    im = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    s = SS
    aw = 34 * bw
    d.rounded_rectangle([(W / 2 - aw) * s, 0, (W / 2 + aw) * s, 280 * s], radius=int(aw) * s, fill=_rgb(_shade(p["shirt_color"], 0.92)))
    d.ellipse([(W / 2 - 34) * s, 262 * s, (W / 2 + 34) * s, 336 * s], fill=_rgb(p["skin"]))
    return im.resize((W, H), Image.LANCZOS)


# ------------------------------------------------------------------------------------------- assemblage
def render(char: Character, pose: Pose = Pose(), scale: float = 1.0) -> Image.Image:
    """Image RGBA du personnage entier (pieds en bas au centre)."""
    k = char.key()
    p = char.params
    hgt = p["height"]
    W, H = 1000, 1080
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    body = body_sprite(k)
    breath = 1 + 0.012 * pose.breath
    bx, by = (W - body.width) // 2, H - body.height
    bdy = int(-6 * pose.breath)
    sh = BODIES[p["body"]] * 150
    arm = arm_sprite(k)
    # bras : rotation autour de l'épaule (pivot placé au centre d'un cadre carré, puis recollé à l'épaule)
    R = arm.height
    for side, ang in ((-1, pose.arm_l), (1, pose.arm_r)):
        frame = Image.new("RGBA", (2 * R, 2 * R), (0, 0, 0, 0))
        frame.alpha_composite(arm, (R - arm.width // 2, R - 20))
        if ang:
            frame = frame.rotate(side * ang, resample=Image.BICUBIC, center=(R, R))
        sx, sy = W / 2 + side * (sh - 22), by + 78 + bdy
        im.alpha_composite(frame, (int(sx - R), int(sy - R)))
    b = body if breath == 1 else body.resize((body.width, int(body.height * breath)), Image.BICUBIC)
    im.alpha_composite(b, (bx, by - (b.height - body.height) + bdy))
    head = head_sprite(k, pose.emotion, pose.viseme, int(round(pose.eyes * 4)), int(round((pose.look + 1) * 2)))
    if pose.head_tilt:
        head = head.rotate(pose.head_tilt, resample=Image.BICUBIC, center=(head.width // 2, head.height - 40))
    hx, hy = (W - head.width) // 2, by - head.height + 75 + int(pose.head_dy) + bdy
    im.alpha_composite(head, (hx, max(0, hy)))
    if pose.facing < 0:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    f = scale * hgt
    if abs(f - 1) > 1e-3:
        im = im.resize((int(W * f), int(H * f)), Image.LANCZOS)
    return im


def preview(char: Character, emotion: str = "joie", viseme: str = "A", bg: str = "#E8EEF8") -> Image.Image:
    canvas = Image.new("RGBA", (1000, 1080), _rgb(bg))
    canvas.alpha_composite(render(char, Pose(emotion=emotion, viseme=viseme, arm_r=35, look=0.3)), (0, 0))
    return canvas.convert("RGB")
