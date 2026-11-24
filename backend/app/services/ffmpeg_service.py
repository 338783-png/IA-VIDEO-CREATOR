"""Accès à FFmpeg/FFprobe. Les arguments sont toujours passés en liste (jamais via un shell)."""
import json
import shutil
import subprocess
from pathlib import Path

from app.core.config import settings
from app.core.errors import AppError


def _version(binary: str) -> str | None:
    if not shutil.which(binary):
        return None
    out = subprocess.run([binary, "-version"], capture_output=True, text=True, timeout=10)
    return out.stdout.splitlines()[0] if out.returncode == 0 and out.stdout else None


def status() -> dict:
    ff, fp = _version(settings.ffmpeg_bin), _version(settings.ffprobe_bin)
    return {"available": bool(ff and fp), "ffmpeg": ff, "ffprobe": fp}


def probe(path: Path) -> dict:
    """Retourne les métadonnées utiles ; lève AppError si le fichier n'est pas un média lisible."""
    cmd = [settings.ffprobe_bin, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError as e:
        raise AppError("ffprobe introuvable : installez FFmpeg.", 503, "ffmpeg_missing") from e
    if res.returncode != 0:
        raise AppError("Fichier média illisible ou corrompu.", 422, "probe_failed")
    data = json.loads(res.stdout or "{}")
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)

    def _fps(rate: str | None) -> float | None:
        try:
            n, d = (rate or "0/0").split("/")
            return round(int(n) / int(d), 3) if int(d) else None
        except ValueError:
            return None

    return {
        "duration": float(fmt["duration"]) if fmt.get("duration") else None,
        "format_name": fmt.get("format_name"),
        "bit_rate": int(fmt["bit_rate"]) if fmt.get("bit_rate") else None,
        "video": {"codec": v.get("codec_name"), "width": v.get("width"), "height": v.get("height"), "fps": _fps(v.get("avg_frame_rate"))} if v else None,
        "audio": {"codec": a.get("codec_name"), "sample_rate": a.get("sample_rate"), "channels": a.get("channels")} if a else None,
    }


def make_thumbnail(src: Path, dest: Path, at_seconds: float = 1.0) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [settings.ffmpeg_bin, "-y", "-v", "error", "-ss", str(at_seconds), "-i", str(src), "-frames:v", "1", "-vf", "scale=480:-2", str(dest)]
    res = subprocess.run(cmd, capture_output=True, timeout=60)
    if res.returncode != 0 and at_seconds > 0:  # vidéo plus courte que at_seconds
        return make_thumbnail(src, dest, 0)
    return res.returncode == 0 and dest.exists()
