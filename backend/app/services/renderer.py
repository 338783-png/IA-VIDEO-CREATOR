"""Moteur de rendu FFmpeg. Les fichiers sources sont uniquement lus ; tout le travail se fait dans storage/tmp/."""
import logging
import shutil
import subprocess
import uuid
from pathlib import Path

from app.core.config import settings
from app.core.errors import AppError
from app.services import ffmpeg_service, subtitles_ass, timeline
from app.services.jobs import JobContext

log = logging.getLogger("renderer")

QUALITY = {  # (preset, crf)
    "haute": ("medium", 18), "standard": ("veryfast", 21), "rapide": ("veryfast", 25), "apercu": ("ultrafast", 28),
}


def _run(ctx: JobContext, cmd: list[str], cwd: Path | None = None, total: float | None = None,
         prog: tuple[float, float] | None = None, msg: str = "") -> None:
    if total and prog:
        cmd = cmd[:1] + ["-progress", "pipe:1", "-nostats"] + cmd[1:]
    p = ctx.popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        if total and prog:
            for line in p.stdout:
                if line.startswith("out_time_us=") and line.strip()[12:].isdigit():
                    t = int(line.strip()[12:]) / 1e6
                    ctx.progress(prog[0] + (prog[1] - prog[0]) * min(1, t / total), msg)
        _, err = p.communicate()
    finally:
        ctx.release(p)
    ctx.check()
    if p.returncode != 0:
        log.error("FFmpeg a échoué : %s\n%s", " ".join(cmd), err[-3000:])
        raise AppError(f"Échec du rendu FFmpeg : {err.strip().splitlines()[-1] if err.strip() else 'erreur inconnue'}", 500, "render_failed")


def _fit_filter(fit: str, W: int, H: int) -> str:
    if fit == "blur":
        return (f"split[fa][fb];[fa]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=25:2[bg];"
                f"[fb]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")
    return f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=bicubic,crop={W}:{H}"


def _effect_filter(effect: str, W: int, H: int, d: float, z: float) -> str:
    d = max(d, 0.1)
    if effect == "zoom_in":
        return f"scale=w='trunc({W}*(1+{z}*t/{d:.3f})/2)*2':h=-2:eval=frame:flags=bicubic,crop={W}:{H}"
    if effect == "zoom_out":
        return f"scale=w='trunc({W}*(1+{z}*(1-t/{d:.3f}))/2)*2':h=-2:eval=frame:flags=bicubic,crop={W}:{H}"
    if effect == "punch_in":
        return f"scale=w={int(W * 1.15) // 2 * 2}:h=-2:flags=bicubic,crop={W}:{H}"
    if effect in ("pan_left", "pan_right"):
        sw = int(W * (1 + z + 0.05)) // 2 * 2
        x = f"(iw-{W})*t/{d:.3f}" if effect == "pan_left" else f"(iw-{W})*(1-t/{d:.3f})"
        return f"scale=w={sw}:h=-2:flags=bicubic,crop={W}:{H}:x='{x}':y='(ih-{H})/2'"
    return "null"


def render_scene(ctx: JobContext, sc: dict, src: Path, has_audio: bool, out: Path, W: int, H: int, fps: int,
                 fit: str, preset: str, crf: int, zoom: float) -> None:
    d = sc["duration"]
    cmd = [settings.ffmpeg_bin, "-y", "-v", "error"]
    if sc["kind"] == "image":
        cmd += ["-loop", "1", "-framerate", str(fps), "-t", f"{d:.3f}", "-i", str(src)]
    else:
        cmd += ["-ss", f"{sc['start']:.3f}", "-t", f"{d:.3f}", "-i", str(src)]
    if not has_audio or sc["kind"] == "image":
        cmd += ["-f", "lavfi", "-t", f"{d:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        a_in = "1:a"
    else:
        a_in = "0:a"
    vol = float(sc.get("volume", 1.0))
    fc = (f"[0:v]{_fit_filter(fit, W, H)}[fit];[fit]{_effect_filter(sc.get('effect', 'none'), W, H, d, zoom)},"
          f"fps={fps},setsar=1,format=yuv420p,tpad=stop_mode=clone:stop_duration=1,trim=duration={d:.3f},setpts=PTS-STARTPTS[v];"
          f"[{a_in}]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={vol:.3f},"
          f"afade=t=in:d=0.012,apad,atrim=duration={d:.3f},afade=t=out:st={max(0, d - 0.012):.3f}:d=0.012,asetpts=PTS-STARTPTS[a]")
    cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
            "-r", str(fps), "-c:a", "pcm_s16le", "-t", f"{d:.3f}", str(out)]
    _run(ctx, cmd)


def render(ctx: JobContext, storyboard: dict, media_paths: dict[int, Path], media_audio: dict[int, bool], out_path: Path,
           mode: str = "preview", quality: str = "standard", fps: int | None = None,
           progress_range: tuple[float, float] = (0.0, 1.0)) -> dict:
    scenes = storyboard["scenes"]
    if not scenes:
        raise AppError("Le storyboard ne contient aucune scène.", 400, "empty_storyboard")
    fmt = storyboard["format"]
    W, H = fmt["width"], fmt["height"]
    fps = int(fps or fmt.get("fps") or 30)
    if mode == "preview":
        W, H = W // 2 // 2 * 2, H // 2 // 2 * 2
        preset, crf = QUALITY["apercu"]
        fps = min(fps, 30)
    else:
        preset, crf = QUALITY.get(quality, QUALITY["standard"])
    fit = storyboard.get("fit_mode", "cover")
    zoom = 0.12
    style_zoom = ((storyboard.get("style") or {}).get("zoom_max_scale"))
    if style_zoom:
        zoom = max(0.05, min(0.35, float(style_zoom) - 1))
    warnings: list[str] = []
    a, b = progress_range
    work = settings.tmp_dir / f"render_{uuid.uuid4().hex[:10]}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        # --- 1. scènes ---------------------------------------------------------------------
        clips = []
        for i, sc in enumerate(scenes):
            ctx.progress(a + (b - a) * 0.6 * i / len(scenes), f"Rendu de la scène {i + 1}/{len(scenes)}…", force=True)
            src = media_paths.get(sc["media_id"])
            if not src or not src.exists():
                raise AppError(f"Média source introuvable pour la scène {sc['id']} ({sc.get('source')}).", 410, "missing_source")
            out = work / f"scene_{i:03d}.mkv"
            render_scene(ctx, sc, src, media_audio.get(sc["media_id"], False), out, W, H, fps, fit, preset if mode == "preview" else "veryfast",
                         crf if mode == "preview" else 14, zoom)
            clips.append(out)

        # --- 2. assemblage -------------------------------------------------------------------
        starts, total = timeline.compute(scenes)
        sub = storyboard.get("subtitles") or {}
        has_subs = sub.get("enabled") and any(s.get("text") for s in scenes)
        if has_subs:
            (work / "subs.ass").write_text(subtitles_ass.build_ass(storyboard, warnings), encoding="utf-8")
        cmd = [settings.ffmpeg_bin, "-y", "-v", "error"]
        for c in clips:
            cmd += ["-i", c.name]
        audio = storyboard.get("audio") or {}
        idx = len(clips)
        vo_idx = mu_idx = None
        vo_id, mu_id = audio.get("voiceover_media_id"), audio.get("music_media_id")
        if vo_id and media_paths.get(vo_id) and media_paths[vo_id].exists():
            cmd += ["-i", str(media_paths[vo_id])]
            vo_idx, idx = idx, idx + 1
            vo_dur = (ffmpeg_service.probe(media_paths[vo_id]).get("duration") or 0)
            if vo_dur > total + 0.5:
                warnings.append(f"La voix off ({vo_dur:.1f} s) est plus longue que le montage ({total:.1f} s) : elle sera coupée. "
                                "Ajoutez des scènes ou allongez-les.")
        elif vo_id:
            warnings.append("Fichier de voix off introuvable : ignoré.")
        if mu_id and media_paths.get(mu_id) and media_paths[mu_id].exists():
            cmd += ["-stream_loop", "-1", "-i", str(media_paths[mu_id])]
            mu_idx, idx = idx, idx + 1
        elif mu_id:
            warnings.append("Fichier musical introuvable : ignoré.")

        # base de temps commune (concat et xfade exigent des entrées homogènes)
        parts = [f"[{i}:v]fps={fps},settb=AVTB[in{i}v]" for i in range(len(clips))]
        parts += [f"[{i}:a]asettb=AVTB[in{i}a]" for i in range(len(clips))]
        cur_v, cur_a, cur_len = "[in0v]", "[in0a]", scenes[0]["duration"]
        for i in range(1, len(scenes)):
            td = timeline.transition_duration(scenes, i - 1)
            xf = timeline.TRANSITIONS.get(scenes[i - 1].get("transition", "cut"))
            nv, na = f"[v{i}]", f"[a{i}]"
            if xf and td > 0:
                parts.append(f"{cur_v}[in{i}v]xfade=transition={xf}:duration={td:.3f}:offset={cur_len - td:.3f}{nv}")
                parts.append(f"{cur_a}[in{i}a]acrossfade=d={td:.3f}{na}")
                cur_len += scenes[i]["duration"] - td
            else:
                parts.append(f"{cur_v}{cur_a}[in{i}v][in{i}a]concat=n=2:v=1:a=1[c{i}v][c{i}a];[c{i}v]fps={fps},settb=AVTB{nv};[c{i}a]asettb=AVTB{na}")
                cur_len += scenes[i]["duration"]
            cur_v, cur_a = nv, na
        if has_subs:
            parts.append(f"{cur_v}subtitles=subs.ass[vout]")
        else:
            parts.append(f"{cur_v}null[vout]")
        orig_vol = float(audio.get("original_volume", 1.0))
        parts.append(f"{cur_a}volume={orig_vol:.3f}[orig]")
        speech = "[orig]"
        if vo_idx is not None:
            parts.append(f"[{vo_idx}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=duration={total:.3f}[vo]")
            parts.append("[orig][vo]amix=inputs=2:normalize=0:duration=first[speech]")
            speech = "[speech]"
        if mu_idx is not None:
            mdb = float(audio.get("music_volume_db", -16))
            parts.append(f"[{mu_idx}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=duration={total:.3f},volume={mdb}dB,"
                         f"afade=t=in:d=0.5,afade=t=out:st={max(0, total - 1.2):.3f}:d=1.2[mus]")
            if audio.get("ducking", True):
                parts.append(f"{speech}asplit=2[sp1][sp2]")
                parts.append("[mus][sp2]sidechaincompress=threshold=0.015:ratio=12:attack=15:release=400:makeup=1[duck]")
                parts.append("[sp1][duck]amix=inputs=2:normalize=0:duration=first[mix]")
            else:
                parts.append(f"{speech}[mus]amix=inputs=2:normalize=0:duration=first[mix]")
            speech = "[mix]"
        lufs = float(audio.get("target_lufs", -14.0))
        parts.append(f"{speech}loudnorm=I={lufs}:TP=-1.5:LRA=11,aresample=48000[aout]")
        out_tmp = work / "final.mp4"
        cmd += ["-filter_complex", ";".join(parts), "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p", "-r", str(fps),
                "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart",
                "-t", f"{total:.3f}", out_tmp.name]
        _run(ctx, cmd, cwd=work, total=total, prog=(a + (b - a) * 0.6, a + (b - a) * 0.98), msg="Assemblage, sous-titres et mixage audio…")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(out_tmp, out_path)
        info = ffmpeg_service.probe(out_path)
        return {"path": str(out_path), "duration": info.get("duration"), "expected_duration": total, "width": W, "height": H,
                "fps": fps, "warnings": warnings, "probe": info}
    finally:
        shutil.rmtree(work, ignore_errors=True)  # fichiers temporaires uniquement


def verify(path: Path, expected: dict) -> dict:
    """Contrôle de l'export final : conteneur, codecs, résolution, fréquence, durée."""
    p = ffmpeg_service.probe(path)
    v, a = p.get("video") or {}, p.get("audio") or {}
    checks = {
        "mp4": "mp4" in (p.get("format_name") or ""),
        "h264": v.get("codec") == "h264",
        "aac": a.get("codec") == "aac",
        "resolution": (v.get("width"), v.get("height")) == (expected["width"], expected["height"]),
        "fps": abs((v.get("fps") or 0) - expected["fps"]) < 0.5,
        "duration": abs((p.get("duration") or 0) - expected["duration"]) < 0.25,
    }
    return {"ok": all(checks.values()), "checks": checks, "probe": p}
