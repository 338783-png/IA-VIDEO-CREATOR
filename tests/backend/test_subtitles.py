"""Sous-titres (Prompt 5) : SRT / VTT, synchronisation avec la voix, édition manuelle, fichiers à l'export."""
import re
import time
from pathlib import Path

import pytest

from app.services import subtitles_export, tts

VOICE = "fr_FR-siwis-medium"
TEXT = "Bonjour à tous ! Aujourd'hui, on découvre comment fonctionne l'intelligence artificielle. C'est parti."


def _wait(client, jid, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.25)
    raise AssertionError("tâche trop longue")


def test_srt_vtt_format():
    cs = [{"start": 0.0, "end": 1.25, "text": "Bonjour"}, {"start": 3661.5, "end": 3662.004, "text": "fin --> ici"}]
    srt = subtitles_export.to_srt(cs)
    assert srt.startswith("1\n00:00:00,000 --> 00:00:01,250\nBonjour\n")
    assert "2\n01:01:01,500 --> 01:01:02,004\nfin → ici\n" in srt
    vtt = subtitles_export.to_vtt(cs)
    assert vtt.startswith("WEBVTT\n\n00:00:00.000 --> 00:00:01.250\nBonjour\n")


def test_manual_validation():
    ok = subtitles_export.validate_manual([{"start": 2, "end": 3, "text": " b "}, {"start": 0, "end": 1, "text": "a"}, {"start": 4, "end": 5, "text": ""}], 10)
    assert [c["text"] for c in ok] == ["a", "b"]  # trié, vide supprimé
    with pytest.raises(Exception):
        subtitles_export.validate_manual([{"start": 0, "end": 2, "text": "a"}, {"start": 1, "end": 3, "text": "b"}], 10)


@pytest.mark.skipif(not any(v["id"] == VOICE for v in tts.list_voices()), reason="voix Piper absente")
def test_subtitles_pipeline(client, tmp_root, sample_mp4):
    pid = client.post("/api/projects", json={"name": "Sous-titres", "target_format": "tiktok"}).json()["id"]
    with open(sample_mp4, "rb") as f:
        client.post("/api/media/upload", data={"kind": "video", "project_id": str(pid)}, files=[("files", ("plan.mp4", f, "video/mp4"))])
    vo = _wait(client, client.post(f"/api/projects/{pid}/voiceover", json={"text": TEXT, "voice_id": VOICE}).json()["id"])["result"]
    _wait(client, client.post(f"/api/projects/{pid}/analyze", json={"transcribe": False}).json()["id"])
    _wait(client, client.post(f"/api/projects/{pid}/storyboard/generate", json={"instruction": "short", "use_llm": False}).json()["id"])
    sb = client.get(f"/api/projects/{pid}/storyboard").json()
    vid = sb["data"]["scenes"][0]["media_id"]
    n = int(vo["duration"] // 1.9) + 1
    scenes = [{"id": f"s{i}", "media_id": vid, "start": 0, "end": 1.9, "text": "", "transition": "cut", "effect": "none"} for i in range(n)]
    sb = client.put(f"/api/projects/{pid}/storyboard", json={"base_version": sb["version"], "scenes": scenes,
        "audio": {"voiceover_media_id": vo["media_id"]}, "subtitles": {**sb["data"]["subtitles"], "enabled": True, "mode": "chunk"}}).json()

    # automatique : calé sur les mots de la voix
    r = client.get(f"/api/projects/{pid}/subtitles").json()
    assert not r["manual"] and len(r["cues"]) >= 4
    assert r["sync"]["ok"] and r["sync"]["max_offset_ms"] <= 50, r["sync"]
    words = client.get(f"/api/voice-tracks/{vo['media_id']}").json()["words"]
    assert abs(r["cues"][0]["start"] - words[0]["start"]) < 0.01
    srt = client.get(f"/api/projects/{pid}/subtitles", params={"format": "srt"})
    assert srt.status_code == 200 and "attachment" in srt.headers["content-disposition"]
    assert re.search(r"^1\n00:00:00,\d{3} --> 00:00:0\d,\d{3}\nBonjour", srt.text)
    assert client.get(f"/api/projects/{pid}/subtitles", params={"format": "vtt"}).text.startswith("WEBVTT")

    # manuel : correction de texte et d'horaires
    manual = [dict(c, text=c["text"].upper()) for c in r["cues"]]
    manual[0]["text"] = "SALUT À TOUS !"
    sb2 = client.put(f"/api/projects/{pid}/storyboard", json={"base_version": sb["version"], "scenes": sb["data"]["scenes"],
                                                              "subtitles": {**sb["data"]["subtitles"], "manual_cues": manual}}).json()
    r2 = client.get(f"/api/projects/{pid}/subtitles").json()
    assert r2["manual"] and r2["cues"][0]["text"] == "SALUT À TOUS !"
    bad = [dict(manual[0], end=manual[1]["start"] + 0.5), *manual[1:]]
    assert client.put(f"/api/projects/{pid}/storyboard", json={"base_version": sb2["version"], "scenes": sb2["data"]["scenes"],
                                                               "subtitles": {**sb2["data"]["subtitles"], "manual_cues": bad}}).json()["error"] == "cue_overlap"

    # aperçu (sous-titres manuels incrustés), validation, export avec .srt / .vtt
    assert _wait(client, client.post(f"/api/projects/{pid}/storyboard/preview").json()["id"])["status"] == "done"
    client.post(f"/api/projects/{pid}/storyboard/validate", json={"version": sb2["version"]})
    j = _wait(client, client.post(f"/api/projects/{pid}/export", json={"platform": "reels", "quality": "rapide", "fps": 30, "confirm": True}).json()["id"])
    assert j["status"] == "done", j
    mp4 = tmp_root / j["result"]["path"]
    assert mp4.with_suffix(".srt").read_text(encoding="utf-8").count("-->") == len(manual)
    assert "SALUT À TOUS !" in mp4.with_suffix(".vtt").read_text(encoding="utf-8")

    # retour à l'automatique
    sb3 = client.get(f"/api/projects/{pid}/storyboard").json()
    client.put(f"/api/projects/{pid}/storyboard", json={"base_version": sb3["version"], "scenes": sb3["data"]["scenes"],
                                                       "subtitles": {**sb3["data"]["subtitles"], "manual_cues": None}})
    assert not client.get(f"/api/projects/{pid}/subtitles").json()["manual"]


def test_sync_report_ignores_previous_word_rounding():
    """Régression (test final) : un mot qui finit exactement quand le suivant commence ne compte pas comme décalage."""
    sb = {"scenes": [{"id": "a", "start": 0, "end": 3, "duration": 3.0, "transition": "cut", "text": "Expliquez la leçon", "text_auto": True,
                      "words": [{"word": "Expliquez", "start": 0.1, "end": 0.6000000000000001}, {"word": "la", "start": 0.6, "end": 0.7},
                                {"word": "leçon", "start": 0.7, "end": 1.1}]}],
          "format": {"width": 1080, "height": 1920}, "subtitles": {"enabled": True, "mode": "word"}}
    r = subtitles_export.sync_report(sb)
    assert r["ok"] and r["max_offset_ms"] == 0 and r["checked"] == 3
    sb["subtitles"]["manual_cues"] = [{"start": 0.9, "end": 1.5, "text": "la leçon"}]  # décalé de 300 ms à la main
    r = subtitles_export.sync_report(sb)
    assert not r["ok"] and r["max_offset_ms"] == 300
