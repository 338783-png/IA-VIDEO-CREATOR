"""Calcul des positions sur la timeline finale (prise en compte du chevauchement des transitions)."""

TRANSITIONS = {  # nom -> filtre xfade (None = coupe franche)
    "cut": None, "crossfade": "fade", "fade_black": "fadeblack", "flash_white": "fadewhite",
    "slide_left": "slideleft", "slide_up": "slideup", "wipe_left": "wipeleft", "zoom_in": "zoomin", "circle_open": "circleopen",
}
TRANSITION_LABELS = {
    "cut": "Coupe franche", "crossfade": "Fondu enchaîné", "fade_black": "Fondu au noir", "flash_white": "Flash blanc",
    "slide_left": "Glissement gauche", "slide_up": "Glissement haut", "wipe_left": "Balayage", "zoom_in": "Zoom transition",
    "circle_open": "Ouverture en cercle",
}
EFFECTS = {"none": "Aucun", "zoom_in": "Zoom avant progressif", "zoom_out": "Zoom arrière progressif",
           "punch_in": "Recadrage serré (punch-in)", "pan_left": "Panoramique vers la gauche", "pan_right": "Panoramique vers la droite"}


def transition_duration(scenes: list[dict], i: int) -> float:
    """Durée effective de la transition entre la scène i et i+1 (0 pour une coupe ou la dernière scène)."""
    if i >= len(scenes) - 1:
        return 0.0
    t = scenes[i].get("transition", "cut")
    if TRANSITIONS.get(t) is None:
        return 0.0
    d = float(scenes[i].get("transition_duration") or 0.3)
    return max(0.0, min(d, scenes[i]["duration"] / 2, scenes[i + 1]["duration"] / 2))


def compute(scenes: list[dict]) -> tuple[list[float], float]:
    """Retourne le début de chaque scène sur la timeline et la durée totale."""
    starts, t = [], 0.0
    for i, sc in enumerate(scenes):
        starts.append(round(t, 3))
        t += sc["duration"] - transition_duration(scenes, i)
    return starts, round(t, 3)
