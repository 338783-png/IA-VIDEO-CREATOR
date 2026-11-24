"""Parcours complet du moteur de montage via l'API (sans Whisper ni LLM : plans visuels + image + musique)."""
import subprocess
import time
from pathlib import Path

import pytest

from app.services import transcription


def _wait(client, jid, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.25)
    raise AssertionError("tâche trop longue")


def _ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


@pytest.fixture(scope="module")
def project(client, tmp_root):
    d = tmp_root / "engine"
    d.mkdir(exist_ok=True)
    # vidéo paysage 1920x1080 avec 3 plans distincts + son, pour tester le recadrage vertical
    _ff("-f", "lavfi", "-i", "smptehdbars=s=1920x1080:r=30:d=3", "-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=3",
        "-f", "lavfi", "-i", "color=c=0x2E8B57:s=1920x1080:r=30:d=3", "-f", "lavfi", "-i", "sine=f=330:d=9",
        "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-map", "3:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(d / "rush.mov"))
    _ff("-f", "lavfi", "-i", "testsrc=s=1200x1600:d=1", "-frames:v", "1", str(d / "photo.png"))
    _ff("-f", "lavfi", "-i", "aevalsrc='0.5*sin(2*PI*60*t)*exp(-20*mod(t,0.5))':s=44100:d=12", "-c:a", "libmp3lame", str(d / "musique.mp3"))
    pid = client.post("/api/projects", json={"name": "Projet moteur", "target_format": "tiktok",
                                             "instruction": "TikTok de 12 secondes, transitions dynamiques, zooms, musique discrète"}).json()["id"]
    for kind, name, mime in [("video", "rush.mov", "video/quicktime"), ("image", "photo.png", "image/png"), ("audio", "musique.mp3", "audio/mpeg")]:
        with open(d / name, "rb") as f:
            r = client.post("/api/media/upload", data={"kind": kind, "project_id": str(pid)}, files=[("files", (name, f, mime))])
            assert r.status_code == 201, r.text
    return pid


def test_storyboard_requires_analysis(client, project):
    r = client.post(f"/api/projects/{project}/storyboard/generate", json={"use_llm": False})
    assert r.status_code == 409 and r.json()["error"] == "not_analyzed"


def test_full_pipeline(client, project, tmp_root):
    # 1. analyse
    j = _wait(client, client.post(f"/api/projects/{project}/analyze", json={"transcribe": False}).json()["id"])
    assert j["status"] == "done", j
    an = client.get(f"/api/projects/{project}/analysis").json()
    video = next(a for a in an if a["media"]["kind"] == "video")
    assert len(video["data"]["shots"]) == 3  # changements de scène détectés
    music = next(a for a in an if a["media"]["kind"] == "audio")
    assert abs(music["data"]["tempo_bpm"] - 120) < 4

    # 2. storyboard
    j = _wait(client, client.post(f"/api/projects/{project}/storyboard/generate", json={"use_llm": False}).json()["id"])
    assert j["status"] == "done", j
    sb = client.get(f"/api/projects/{project}/storyboard").json()
    data = sb["data"]
    assert sb["version"] == 1 and sb["status"] == "draft"
    assert data["parsed_instruction"]["target_duration_s"] == 12
    assert data["audio"]["music_media_id"] is not None and data["audio"]["music_volume_db"] == -22
    kinds = {s["kind"] for s in data["scenes"]}
    assert kinds == {"video", "image"}
    assert sum(s["transition"] != "cut" for s in data["scenes"][:-1]) >= 2
    assert any(s["effect"] in ("zoom_in", "zoom_out") for s in data["scenes"] if s["kind"] == "video")

    # 3. export interdit avant validation ; validation interdite avant aperçu
    assert client.post(f"/api/projects/{project}/export", json={"platform": "tiktok", "confirm": True}).status_code == 409
    assert client.post(f"/api/projects/{project}/storyboard/validate", json={"version": 1}).json()["error"] == "preview_required"

    # 4. modification manuelle : supprimer la dernière scène, inverser deux scènes, changer une durée et un effet
    scenes = data["scenes"][:-1] if len(data["scenes"]) > 2 else data["scenes"]
    scenes[0], scenes[1] = scenes[1], scenes[0]
    vid = next(s for s in scenes if s["kind"] == "video")
    vid["end"] = round(vid["start"] + 1.5, 3)
    vid["effect"] = "punch_in"
    r = client.put(f"/api/projects/{project}/storyboard", json={"base_version": 1, "scenes": scenes, "fit_mode": "blur"})
    assert r.status_code == 200, r.text
    v2 = r.json()
    assert v2["version"] == 2 and v2["status"] == "draft"
    assert [s["position"] for s in v2["data"]["scenes"]] == list(range(1, len(scenes) + 1))
    assert next(s for s in v2["data"]["scenes"] if s["id"] == vid["id"])["duration"] == 1.5
    # modification invalide refusée
    bad = [dict(scenes[0], end=999)] if scenes[0]["kind"] == "video" else [dict(vid, end=999)]
    assert client.put(f"/api/projects/{project}/storyboard", json={"scenes": bad}).status_code == 422
    assert client.put(f"/api/projects/{project}/storyboard", json={"base_version": 1, "scenes": scenes}).status_code == 409

    # 5. aperçu
    j = _wait(client, client.post(f"/api/projects/{project}/storyboard/preview").json()["id"])
    assert j["status"] == "done", j
    r = client.get(f"/api/projects/{project}/preview.mp4")
    assert r.status_code == 200 and len(r.content) > 10_000
    assert abs(j["result"]["duration"] - v2["data"]["total_duration"]) < 0.25

    # 6. validation puis export final
    assert client.post(f"/api/projects/{project}/storyboard/validate", json={"version": 2}).json()["status"] == "validated"
    assert client.post(f"/api/projects/{project}/export", json={"platform": "tiktok"}).json()["error"] == "confirmation_required"
    j = _wait(client, client.post(f"/api/projects/{project}/export", json={"platform": "tiktok", "quality": "rapide", "fps": 30, "confirm": True}).json()["id"])
    assert j["status"] == "done", j
    assert j["result"]["verification"] is True, j["result"]["checks"]
    exports = client.get(f"/api/projects/{project}/exports").json()
    assert exports and exports[0]["path"].startswith("exports/tiktok/")
    assert (tmp_root / exports[0]["path"]).exists()
    p = client.get(f"/api/projects/{project}").json()
    assert p["status"] == "exported" and p["settings"]["last_export"]["platform"] == "tiktok"
    # sauvegarde des storyboards sur disque
    assert len(list((tmp_root / "projects" / "storyboards" / f"project-{project}").glob("storyboard_v*.json"))) == 2

    # 7. originaux intacts
    for m in client.get("/api/media", params={"project_id": project}).json():
        assert (tmp_root / "storage" / m["stored_path"]).exists()

    # 8. une modification après validation repasse en brouillon
    sb = client.get(f"/api/projects/{project}/storyboard").json()
    r = client.put(f"/api/projects/{project}/storyboard", json={"base_version": sb["version"], "scenes": sb["data"]["scenes"]})
    assert r.json()["status"] == "draft"
    assert client.post(f"/api/projects/{project}/export", json={"platform": "tiktok", "confirm": True}).status_code == 409


def test_export_youtube_landscape(client, project, tmp_root):
    sb = client.get(f"/api/projects/{project}/storyboard").json()
    _wait(client, client.post(f"/api/projects/{project}/storyboard/preview").json()["id"])
    client.post(f"/api/projects/{project}/storyboard/validate", json={"version": sb["version"]})
    j = _wait(client, client.post(f"/api/projects/{project}/export", json={"platform": "youtube", "quality": "rapide", "fps": 25, "confirm": True}).json()["id"])
    assert j["status"] == "done", j
    assert j["result"]["checks"]["resolution"] and j["result"]["checks"]["fps"], j["result"]["checks"]


def test_script_import(client, project, tmp_root):
    p = tmp_root / "script.txt"
    p.write_text("Bonjour à tous ! Voici mon script.\n", encoding="utf-8")
    with open(p, "rb") as f:
        r = client.post("/api/media/upload", data={"kind": "script", "project_id": str(project)}, files=[("files", ("script.txt", f, "text/plain"))])
    assert r.status_code == 201 and r.json()[0]["probe"]["words"] == 6
    r = client.post("/api/media/upload", data={"kind": "script"}, files=[("files", ("bin.txt", b"abc\x00def", "text/plain"))])
    assert r.status_code == 415
