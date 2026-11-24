"""Exécution de Blender en arrière-plan (programme séparé), sans interface et SANS exécution automatique de scripts.

Protocole : le script bpy écrit des lignes « @@PROFIA {json} » sur la sortie standard.
"""
import json
import logging
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from app.core.config import ROOT_DIR, settings
from app.core.errors import AppError
from app.services.jobs import JobContext

log = logging.getLogger("blender")
SCRIPTS = ROOT_DIR / "video-engine" / "blender"


def find_blender() -> Path | None:
    if settings.blender_bin:
        p = Path(settings.blender_bin)
        return p if p.exists() else None
    local = sorted((ROOT_DIR / "ai" / "tools").glob("blender-*/blender"))
    if local:
        return local[-1]
    found = shutil.which("blender")
    return Path(found) if found else None


def status() -> dict:
    b = find_blender()
    if not b:
        return {"available": False, "path": None, "version": None}
    try:
        out = subprocess.run([str(b), "-b", "--factory-startup", "--version"], capture_output=True, text=True, timeout=60).stdout
        version = next((ln.strip() for ln in out.splitlines() if ln.startswith("Blender")), None)
    except (OSError, subprocess.SubprocessError):
        version = None
    return {"available": True, "path": str(b), "version": version}


def run(ctx: JobContext | None, script: str, params: dict, on_event: Callable[[dict], None] | None = None,
        timeout: float | None = None) -> list[dict]:
    """Lance un script de video-engine/blender et renvoie les évènements JSON émis."""
    b = find_blender()
    if not b:
        raise AppError("Blender n'est pas installé (dossier ai/tools/ ou variable BLENDER_BIN).", 503, "blender_missing")
    path = (SCRIPTS / script).resolve()
    if path.parent != SCRIPTS.resolve() or not path.exists():
        raise AppError("Script Blender inconnu.", 400, "bad_script")
    cmd = [str(b), "-b", "-Y", "--factory-startup", "--python-exit-code", "1", "--python", str(path), "--", json.dumps(params)]
    env = {**os.environ, "PYTHONNOUSERSITE": "1"}
    if settings.blender_threads:
        cmd[1:1] = ["-t", str(settings.blender_threads)]
    p = ctx.popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env) if ctx else \
        subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    events, tail = [], []
    try:
        for line in p.stdout:
            if line.startswith("@@PROFIA "):
                ev = json.loads(line[9:])
                events.append(ev)
                if on_event:
                    on_event(ev)
            else:
                tail = (tail + [line.rstrip()])[-40:]
        p.wait(timeout=timeout)
    finally:
        if ctx:
            ctx.release(p)
    if ctx:
        ctx.check()
    if p.returncode != 0:
        log.error("Blender a échoué (%s) :\n%s", script, "\n".join(tail))
        err = next((ev.get("message") for ev in events if ev.get("type") == "error"), None) or (tail[-1] if tail else "erreur inconnue")
        raise AppError(f"Échec de Blender : {err}", 500, "blender_failed")
    return events
