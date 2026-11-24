"""Remplit une instance ISOLÉE de l'application avec un projet de démonstration complet (via l'API).

Usage : python seed_demo.py http://127.0.0.1:8100 <dossier_de_travail>
"""
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "video"))
import make_reference  # noqa: E402
import make_speech_rush  # noqa: E402

API, WORK = sys.argv[1], Path(sys.argv[2])
WORK.mkdir(parents=True, exist_ok=True)
c = httpx.Client(base_url=API, timeout=120)


def wait(job, timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = c.get(f"/api/jobs/{job['id']}").json()
        if j["status"] not in ("queued", "running"):
            assert j["status"] == "done", j
            return j
        time.sleep(0.5)
    raise TimeoutError(job)


def upload(path, kind, pid=None, mime="application/octet-stream"):
    with open(path, "rb") as f:
        data = {"kind": kind} | ({"project_id": str(pid)} if pid else {})
        r = c.post("/api/media/upload", data=data, files=[("files", (path.name, f, mime))])
    r.raise_for_status()
    return r.json()[0]


def ff(*a):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *a], check=True)


# --- référence + style validé
ref = upload(make_reference.make(WORK / "reference_tiktok.mp4"), "reference", mime="video/mp4")
wait(c.post(f"/api/references/{ref['id']}/analyze").json())
style = c.post("/api/styles", json={"name": "Style TikTok éducatif", "reference_media_ids": [ref["id"]]}).json()
c.patch(f"/api/styles/{style['id']}", json={"config_patch": {"subtitles": {"font": {"family": "DejaVu Sans"}}}})
c.post(f"/api/styles/{style['id']}/validate").raise_for_status()

# --- projet 2D complet
pid = c.post("/api/projects", json={"name": "3 astuces pour mieux apprendre", "target_format": "tiktok", "project_type": "2d",
                                    "instruction": "TikTok éducatif de 30 secondes, sous-titres animés, zooms, transitions dynamiques, musique discrète"}).json()["id"]
upload(make_speech_rush.make(WORK / "rush_astuces.mp4"), "video", pid, "video/mp4")
ff("-f", "lavfi", "-i", "aevalsrc='0.4*sin(2*PI*60*t)*exp(-20*mod(t,0.5))+0.05*sin(2*PI*330*t)':s=44100:d=40", "-c:a", "libmp3lame", str(WORK / "musique_libre.mp3"))
upload(WORK / "musique_libre.mp3", "audio", pid, "audio/mpeg")
ff("-f", "lavfi", "-i", "testsrc2=s=1080x1350:d=1", "-frames:v", "1", str(WORK / "schema.png"))
upload(WORK / "schema.png", "image", pid, "image/png")
wait(c.post(f"/api/projects/{pid}/analyze", json={"transcribe": True}).json())
wait(c.post(f"/api/projects/{pid}/storyboard/generate", json={"style_id": style["id"], "use_llm": False}).json())
wait(c.post(f"/api/projects/{pid}/voiceover", json={"text": "Voici trois astuces simples pour mieux apprendre.", "voice_id": "fr_FR-siwis-medium", "name": "accroche"}).json())
sb = c.get(f"/api/projects/{pid}/storyboard").json()
wait(c.post(f"/api/projects/{pid}/storyboard/preview").json())
c.post(f"/api/projects/{pid}/storyboard/validate", json={"version": sb["version"]}).raise_for_status()
wait(c.post(f"/api/projects/{pid}/export", json={"platform": "tiktok", "quality": "rapide", "fps": 30, "confirm": True}).json())

# --- personnages et scénario dialogué (module 2D)
lea = c.post("/api/characters", json={"name": "Prof Léa", "description": "professeure enthousiaste",
                                      "voice": {"voice_id": "fr_FR-siwis-medium", "speed": 1.05}}).json()
max_ = c.post("/api/characters", json={"name": "Max", "description": "élève curieux",
                                       "voice": {"voice_id": "fr_FR-upmc-medium", "speaker": "pierre", "speed": 1.0}}).json()
c.put(f"/api/projects/{pid}/scenario", json={"title": "L'IA expliquée", "scenes": [
    {"title": "Accroche", "setting": "salle de classe", "camera": "plan_moyen", "lines": [
        {"character_id": lea["id"], "text": "Savais-tu qu'une IA apprend grâce à des exemples ?", "emotion": "enthousiaste"},
        {"character_id": max_["id"], "text": "Comme moi avec mes exercices ?", "emotion": "surpris"}]},
    {"title": "Explication", "setting": "tableau", "camera": "zoom_avant", "lines": [
        {"character_id": lea["id"], "text": "Exactement ! Plus elle voit d'exemples, plus elle s'améliore.", "emotion": "joyeux"}]}]}).raise_for_status()

# --- deux projets supplémentaires (cartes du tableau de bord)
p2 = c.post("/api/projects", json={"name": "Présentation YouTube", "target_format": "youtube"}).json()["id"]
upload(WORK / "reference_tiktok.mp4", "video", p2, "video/mp4")
c.post("/api/projects", json={"name": "Dessin animé : l'IA expliquée", "target_format": "tiktok", "project_type": "3d"})
print(f"OK projet={pid} style={style['id']}")
