"""Décodage de flux bruts via FFmpeg (images RGB réduites, audio mono float32)."""
import subprocess
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from app.core.config import settings
from app.services.jobs import JobContext


def even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def analysis_size(width: int, height: int, short_side: int) -> tuple[int, int]:
    if width <= height:
        return even(short_side), even(short_side * height / width)
    return even(short_side * width / height), even(short_side)


def iter_frames(ctx: JobContext | None, path: Path, fps: float, w: int, h: int) -> Iterator[np.ndarray]:
    cmd = [settings.ffmpeg_bin, "-v", "error", "-i", str(path), "-an", "-sn",
           "-vf", f"fps={fps},scale={w}:{h}:flags=area,format=rgb24", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    size = w * h * 3
    p = ctx.popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) if ctx else subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        while True:
            if ctx:
                ctx.check()
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    finally:
        p.stdout.close()
        p.kill() if p.poll() is None else None
        p.wait()
        if ctx:
            ctx.release(p)


def read_audio(ctx: JobContext | None, path: Path, sr: int = 22050) -> np.ndarray:
    cmd = [settings.ffmpeg_bin, "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    p = ctx.popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) if ctx else subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    data, _ = p.communicate()
    if ctx:
        ctx.release(p)
        ctx.check()
    return np.frombuffer(data, np.float32).copy()


def gray(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
