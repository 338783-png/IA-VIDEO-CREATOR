"""Parcours parlé réel : voix Piper -> Whisper -> storyboard (répétition, hésitation, silence écartés) -> export sous-titré.

Ignoré si le modèle Whisper ou la voix Piper ne sont pas installés.
"""
import sys
import time
from pathlib import Path

import pytest

from app.services import transcription

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video"))
import make_speech_rush  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (transcription.status()["downloaded"] and make_speech_rush.VOICE.exists()),
    reason="modèle Whisper ou voix Piper absents",
)


def _wait(client, jid, timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.5)
    raise AssertionError("tâche trop longue")


def test_speech_to_export(client, tmp_root):
    rush = make_speech_rush.make(tmp_root / "rush_parole.mp4")
    pid = client.post("/api/projects", json={"name": "Parole", "target_format": "tiktok"}).json()["id"]
    with open(rush, "rb") as f:
        assert client.post("/api/media/upload", data={"kind": "video", "project_id": str(pid)},
                           files=[("files", ("rush_parole.mp4", f, "video/mp4"))]).status_code == 201

    t0 = time.time()
    j = _wait(client, client.post(f"/api/projects/{pid}/analyze", json={"transcribe": True, "language": "fr"}).json()["id"])
    assert j["status"] == "done", j
    elapsed = time.time() - t0
    a = client.get(f"/api/projects/{pid}/analysis").json()[0]
    text = a["transcript"]["text"].lower()
    print(f"\nTranscription ({elapsed:.1f} s) : {a['transcript']['text']}")
    # homophones tolérés (la voix de synthèse varie légèrement à chaque génération)
    for variants in (("astuces",), ("relisez",), ("notes",), ("expliquez",), ("pauses", "poses")):
        assert any(v in text for v in variants), variants
    assert any(e - s >= 2.0 for s, e in a["data"]["silences"])  # le silence de 2,5 s est détecté

    j = _wait(client, client.post(f"/api/projects/{pid}/storyboard/generate",
                                  json={"instruction": "TikTok éducatif avec sous-titres animés", "use_llm": False}).json()["id"])
    assert j["status"] == "done", j
    sb = client.get(f"/api/projects/{pid}/storyboard").json()
    d = sb["data"]
    kept = " ".join(s["text"] for s in d["scenes"]).lower()
    reasons = [r["reason"] for r in d["rejected"]]
    print("Gardé :", kept)
    print("Écarté :", [(r["reason"], r["text"]) for r in d["rejected"]])
    assert any(r.startswith("répétition") for r in reasons)  # prise ratée écartée
    assert "silence" in reasons
    assert kept.count("aujourd'hui") == 1 and "simples" in kept
    assert "euh" not in kept
    assert d["subtitles"]["enabled"] and d["subtitles"]["animated"]

    _wait(client, client.post(f"/api/projects/{pid}/storyboard/preview").json()["id"])
    assert client.post(f"/api/projects/{pid}/storyboard/validate", json={"version": sb["version"]}).status_code == 200
    j = _wait(client, client.post(f"/api/projects/{pid}/export", json={"platform": "tiktok", "quality": "rapide", "fps": 30, "confirm": True}).json()["id"])
    assert j["status"] == "done" and j["result"]["verification"], j
    (tmp_root / "last_speech_export.txt").write_text(j["result"]["path"])
