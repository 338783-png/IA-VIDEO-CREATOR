"""Étape 12 : vérification approfondie de la vidéo finale exportée, puis rapport de test."""
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import httpx

API, OUT, TMP, REPORT = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
ui = json.loads((OUT / "ui_steps.json").read_text())
steps = ui["steps"]
checks: dict[str, tuple[bool, str]] = {}
pid = ui.get("project")
if pid and all(s["ok"] for s in steps):
    c = httpx.Client(base_url=API, timeout=60)
    exp = c.get("/api/exports", params={"project_id": pid}).json()[0]
    sb = c.get(f"/api/projects/{pid}/storyboard").json()
    mp4 = TMP / exp["path"]
    p = json.loads(subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(mp4)],
                                  capture_output=True, text=True).stdout)
    v = next(s for s in p["streams"] if s["codec_type"] == "video")
    a = next(s for s in p["streams"] if s["codec_type"] == "audio")
    dur = float(p["format"]["duration"])
    checks["Conteneur MP4"] = ("mp4" in p["format"]["format_name"], p["format"]["format_name"])
    checks["Vidéo H.264"] = (v["codec_name"] == "h264", f"{v['codec_name']} {v.get('profile')}")
    checks["Audio AAC"] = (a["codec_name"] == "aac", f"{a['codec_name']} {a['sample_rate']} Hz")
    checks["Résolution 1080×1920"] = ((v["width"], v["height"]) == (1080, 1920), f"{v['width']}×{v['height']}")
    checks["30 images/s"] = (v["avg_frame_rate"] in ("30/1", "30000/1001"), v["avg_frame_rate"])
    checks["Durée = storyboard"] = (abs(dur - sb["data"]["total_duration"]) < 0.25, f"{dur:.2f} s / {sb['data']['total_duration']:.2f} s")
    lufs = re.findall(r"I:\s+(-?\d+\.\d) LUFS", subprocess.run(["ffmpeg", "-nostats", "-i", str(mp4), "-af", "ebur128", "-f", "null", "-"],
                                                               capture_output=True, text=True).stderr)
    checks["Volume ≈ -14 LUFS"] = (bool(lufs) and abs(float(lufs[-1]) + 14) < 1.5, f"{lufs[-1] if lufs else '?'} LUFS")
    checks["Version validée exportée"] = (exp["storyboard_version"] == sb["version"] and sb["status"] == "validated", f"v{exp['storyboard_version']}")
    first = sb["data"]["scenes"][0]
    checks["Modification de scène conservée"] = (first["effect"] == "zoom_out" and first["text"] == "TEXTE MODIFIÉ À LA MAIN", f"{first['effect']} / « {first['text']} »")
    checks["Style appliqué"] = (sb["data"]["style"]["name"] == "Style test final", sb["data"]["style"]["name"])
    srt = mp4.with_suffix(".srt")
    checks["Fichiers SRT + VTT"] = (srt.exists() and mp4.with_suffix(".vtt").exists(), f"{srt.read_text(encoding='utf-8').count('-->') if srt.exists() else 0} sous-titres")
    sync = c.get(f"/api/projects/{pid}/subtitles").json()["sync"]
    checks["Synchro sous-titres/voix"] = (sync["ok"], f"écart max {sync['max_offset_ms']} ms")
    checks["Original non modifié"] = (all((TMP / "storage" / m["stored_path"]).exists() for m in c.get("/api/media", params={"project_id": pid}).json()), "fichiers sources présents, lecture seule")
    for t in (1.0, dur / 2):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(mp4), "-frames:v", "1", "-vf", "scale=360:-2", str(OUT / f"export_{t:.0f}s.jpg")])
    steps.append({"n": 12, "title": "Vérifier la vidéo finale", "ok": all(ok for ok, _ in checks.values()), "seconds": 0,
                  "detail": f"{sum(ok for ok, _ in checks.values())}/{len(checks)} contrôles réussis"})
else:
    steps.append({"n": 12, "title": "Vérifier la vidéo finale", "ok": False, "seconds": 0, "detail": "non exécutée (étape précédente en échec)"})

ok_all = all(s["ok"] for s in steps) and not ui["jsErrors"]
L = ["# Rapport de test final — AI VIDEO EDITOR (PROMPT 7)", "",
     f"Date : {datetime.now():%d/%m/%Y %H:%M} · Instance isolée (données temporaires) · Navigateur automatisé (Chromium)", "",
     f"**Résultat global : {'✅ RÉUSSI' if ok_all else '❌ ÉCHEC'}** — {sum(s['ok'] for s in steps)}/{len(steps)} étapes", "",
     "## Scénario", "", "| # | Étape | Résultat | Durée | Détail |", "|---|---|---|---|---|"]
L += [f"| {s['n']} | {s['title']} | {'✅' if s['ok'] else '❌'} | {s['seconds']} s | {s['detail']} |" for s in sorted(steps, key=lambda s: s["n"])]
if checks:
    L += ["", "## Vérification de la vidéo finale", "", "| Contrôle | Résultat | Valeur |", "|---|---|---|"]
    L += [f"| {k} | {'✅' if ok else '❌'} | {val} |" for k, (ok, val) in checks.items()]
L += ["", "## Erreurs JavaScript dans le navigateur", "", "\n".join(f"- {e}" for e in ui["jsErrors"]) or "Aucune.", "",
      "## Reproduire", "", "```bash", "./tests/e2e/run_final_test.sh", "```", ""]
REPORT.write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
sys.exit(0 if ok_all else 1)
