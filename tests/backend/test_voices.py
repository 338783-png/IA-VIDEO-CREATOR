"""Voix off locale (Piper) : voix, vitesse, pauses, volume, écoute, génération, intégration au montage."""
import io
import time
import wave

import numpy as np
import pytest

from app.services import tts

VOICE = "fr_FR-siwis-medium"
pytestmark = pytest.mark.skipif(not any(v["id"] == VOICE for v in tts.list_voices()), reason="voix Piper absente")
TEXT = "Bonjour à tous ! Aujourd'hui, on découvre comment fonctionne l'intelligence artificielle."


def _wav(b: bytes):
    with wave.open(io.BytesIO(b)) as w:
        sr, n = w.getframerate(), w.getnframes()
        a = np.frombuffer(w.readframes(n), np.int16).astype(np.float32) / 32768
    return sr, a


def _wait(client, jid, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.25)
    raise AssertionError("tâche trop longue")


def test_list_voices(client):
    r = client.get("/api/voices").json()
    v = next(x for x in r["voices"] if x["id"] == VOICE)
    assert r["installed"] and v["license"] and "CC" in v["license"] and not v["excluded"]


def test_speed_pause_volume():
    base = tts.synthesize(TEXT, VOICE, speed=1.0, pause_s=0.0)
    fast = tts.synthesize(TEXT, VOICE, speed=1.5, pause_s=0.0)
    paused = tts.synthesize(TEXT, VOICE, speed=1.0, pause_s=1.0)
    quiet = tts.synthesize(TEXT, VOICE, speed=1.0, pause_s=0.0, volume_db=-12)
    assert fast["duration"] < base["duration"] * 0.8
    # 2 phrases -> 2 pauses de 1 s (Piper varie légèrement le rythme d'une génération à l'autre)
    assert 1.7 < paused["duration"] - base["duration"] < 2.3
    rms = lambda r: float(np.sqrt((_wav(r["wav_bytes"])[1] ** 2).mean()))  # noqa: E731
    assert rms(quiet) < rms(base) * 0.4
    words = [w["word"] for w in base["words"]]
    assert words[0] == "Bonjour" and "l'intelligence" in words and len(words) == 10
    assert all(a["end"] <= b["start"] + 1e-3 for a, b in zip(base["words"], base["words"][1:]))
    assert len(base["phonemes"]) > 30


def test_preview_and_validation(client):
    r = client.post("/api/voices/preview", json={"text": "Petit essai de voix.", "voice_id": VOICE, "speed": 1.2})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    sr, a = _wav(r.content)
    assert sr == 22050 and len(a) / sr > 0.5
    assert client.post("/api/voices/preview", json={"text": "x", "voice_id": "../../etc/passwd"}).status_code == 400
    assert client.post("/api/voices/preview", json={"text": "x", "voice_id": "fr_FR-inconnue"}).status_code == 404
    assert client.post("/api/voices/preview", json={"text": "x" * 500, "voice_id": VOICE}).status_code == 422
    assert client.post("/api/voices/preview", json={"text": "x", "voice_id": VOICE, "speed": 5}).status_code == 422


def test_voiceover_in_montage(client, tmp_root, sample_mp4):
    pid = client.post("/api/projects", json={"name": "Voix off", "target_format": "tiktok"}).json()["id"]
    with open(sample_mp4, "rb") as f:
        client.post("/api/media/upload", data={"kind": "video", "project_id": str(pid)}, files=[("files", ("plan.mp4", f, "video/mp4"))])
    j = _wait(client, client.post(f"/api/projects/{pid}/voiceover",
                                  json={"text": TEXT, "voice_id": VOICE, "speed": 1.1, "name": "narration"}).json()["id"])
    assert j["status"] == "done", j
    mid = j["result"]["media_id"]
    track = client.get(f"/api/voice-tracks/{mid}").json()
    assert track["voice_id"] == VOICE and len(track["words"]) == 10 and track["duration"] > 3
    media = client.get("/api/media", params={"project_id": pid}).json()
    assert any(m["id"] == mid and m["kind"] == "audio" and m["stored_path"].startswith("audio/") for m in media)

    # montage : un plan vidéo bouclé sur la durée de la voix + voix off + sous-titres depuis la voix off
    _wait(client, client.post(f"/api/projects/{pid}/analyze", json={"transcribe": False}).json()["id"])
    _wait(client, client.post(f"/api/projects/{pid}/storyboard/generate", json={"instruction": "short avec sous-titres", "use_llm": False}).json()["id"])
    sb = client.get(f"/api/projects/{pid}/storyboard").json()
    vid = next(m for m in media if m["kind"] == "video")
    n = int(track["duration"] // 2) + 1
    scenes = [{"id": f"s{i}", "media_id": vid["id"], "start": 0, "end": 1.9, "text": "", "effect": "zoom_in" if i % 2 else "none",
               "transition": "cut"} for i in range(n)]
    r = client.put(f"/api/projects/{pid}/storyboard", json={
        "base_version": sb["version"], "scenes": scenes,
        "audio": {"voiceover_media_id": mid, "original_volume": 0.2},
        "subtitles": {**sb["data"]["subtitles"], "enabled": True, "mode": "word", "animated": True}})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["subtitles"]["source"] == "voiceover" and len(d["audio"]["voiceover_words"]) == 10
    j = _wait(client, client.post(f"/api/projects/{pid}/storyboard/preview").json()["id"])
    assert j["status"] == "done", j
    assert not any("plus longue" in w for w in j["result"]["warnings"])
