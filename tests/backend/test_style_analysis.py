import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video"))
from make_reference import GROUND_TRUTH, make  # noqa: E402


def _wait(client, job_id, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.2)
    raise AssertionError("tâche trop longue")


def _upload_ref(client, path):
    with open(path, "rb") as f:
        r = client.post("/api/media/upload", data={"kind": "reference"}, files=[("files", (path.name, f, "video/mp4"))])
    assert r.status_code == 201, r.text
    return r.json()[0]["id"]


@pytest.fixture(scope="module")
def ref_id(client, tmp_root):
    mid = _upload_ref(client, make(tmp_root / "reference_test.mp4"))
    job = client.post(f"/api/references/{mid}/analyze").json()
    j = _wait(client, job["id"])
    assert j["status"] == "done", j
    return mid


@pytest.fixture(scope="module")
def analysis(client, ref_id):
    return client.get(f"/api/references/{ref_id}/analysis").json()


def test_format(analysis):
    assert analysis["format"]["aspect"] == "9:16" and analysis["format"]["fps"] == 30


def test_shot_boundaries_match_ground_truth(analysis):
    starts = [s["start"] for s in analysis["scenes"][1:]]
    types = [s["transition_in"]["type"] for s in analysis["scenes"][1:]]
    assert len(starts) == len(GROUND_TRUTH["boundaries"])
    for got, want in zip(starts, GROUND_TRUTH["boundaries"]):
        assert abs(got - want) <= 0.1, (got, want)
    assert types == GROUND_TRUTH["types"]


def test_motion(analysis):
    sc = analysis["scenes"]
    z = sc[GROUND_TRUTH["zoom_scene"] - 1]["motion"]
    assert z["type"] == "zoom_avant" and 1.25 < z["zoom_total"] < 1.42
    assert sc[GROUND_TRUTH["pan_scene"] - 1]["motion"]["type"] == "panoramique"
    assert sc[0]["motion"]["type"] == "statique"


def test_captions(analysis):
    c = analysis["captions"]
    assert c["detected"] and c["position"] == "bas"
    assert c["fill_color"].startswith("#F") and c["outline_color"].startswith("#0")
    assert c["change_interval_s"] < 0.8
    assert c["font"] is None  # ne prétend pas identifier la police


def test_audio(analysis):
    a = analysis["audio"]
    assert abs(a["tempo_bpm"] - GROUND_TRUTH["bpm"]) < 3
    assert a["sync"]["cuts_on_beat_ratio"] >= 0.8


def test_colors_contain_orange_and_blue(analysis):
    hexes = [p["hex"] for p in analysis["colors"]["palette"]]
    rgb = [tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) for h in hexes]
    assert any(r > 200 and 100 < g < 180 and b < 60 for r, g, b in rgb), hexes  # orange
    assert any(b > 200 and r < 60 for r, g, b in rgb), hexes  # bleu


def test_keyframe_served_and_traversal_blocked(client, ref_id):
    assert client.get(f"/api/references/{ref_id}/keyframes/scene_01.jpg").status_code == 200
    assert client.get(f"/api/references/{ref_id}/keyframes/..%2F..%2Fapp.db").status_code in (400, 404)
    assert client.get(f"/api/references/{ref_id}/keyframes/x.jpg").status_code == 400


def test_no_false_positives_on_plain_footage(client, tmp_root):
    """Plan continu sans texte ni coupe : rien ne doit être inventé."""
    p = tmp_root / "plain.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "mandelbrot=s=540x960:r=30", "-t", "6",
                    "-f", "lavfi", "-i", "anoisesrc=d=6:a=0.05", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(p)], check=True)
    mid = _upload_ref(client, p)
    j = _wait(client, client.post(f"/api/references/{mid}/analyze").json()["id"])
    assert j["status"] == "done", j
    a = client.get(f"/api/references/{mid}/analysis").json()
    assert a["rhythm"]["shot_count"] == 1
    assert a["captions"]["detected"] is False
    assert a["audio"]["tempo_bpm"] is None or a["audio"]["music"]["likely"] is False


def test_style_lifecycle(client, ref_id, tmp_root):
    r = client.post("/api/styles", json={"name": "Style test", "reference_media_ids": [ref_id]})
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["status"] == "draft" and not s["is_official"]
    keys_m = [x["key"] for x in s["summary"]["mandatory"]]
    keys_o = [x["key"] for x in s["summary"]["optional"]]
    assert {"format", "rhythm", "subtitles", "cut_on_beat"} <= set(keys_m)
    assert "transition_crossfade" in keys_o and "zoom" in keys_o
    assert len(s["summary"]["per_scene"]) == 6
    assert "BROUILLON" in s["markdown"] and "Police non identifiée" in s["markdown"]
    for section in ("Palette de couleurs", "Polices", "Règles de sous-titrage", "Transitions", "Animations", "Effets", "Rythme", "Règles de synchronisation"):
        assert f"## {section}" in s["markdown"]

    # validation refusée tant que la police n'est pas choisie
    r = client.post(f"/api/styles/{s['id']}/validate")
    assert r.status_code == 409 and r.json()["error"] == "font_required"

    r = client.patch(f"/api/styles/{s['id']}", json={"config_patch": {"subtitles": {"font": {"family": "Montserrat ExtraBold"}}}})
    assert r.json()["config"]["subtitles"]["font"]["family"] == "Montserrat ExtraBold"
    assert r.json()["config"]["subtitles"]["position"] == "bas"  # fusion partielle

    r = client.post(f"/api/styles/{s['id']}/validate")
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["status"] == "validated" and v["is_official"] and "VALIDÉ" in v["markdown"]
    folder = tmp_root / "projects" / "styles"
    files = list(folder.glob("style-*/style.json"))
    assert files and json.loads(files[0].read_text())["subtitles"]["font"]["family"] == "Montserrat ExtraBold"

    # une modification repasse le style en brouillon
    r = client.patch(f"/api/styles/{s['id']}", json={"user_notes": "Plus de zooms"})
    assert r.json()["status"] == "draft" and not r.json()["is_official"]

    assert client.patch(f"/api/styles/{s['id']}", json={"config_patch": {"provenance": {}}}).status_code == 422


def test_style_requires_analysis(client, tmp_root, sample_mp4):
    with open(sample_mp4, "rb") as f:
        mid = client.post("/api/media/upload", data={"kind": "reference"}, files=[("files", ("x.mp4", f, "video/mp4"))]).json()[0]["id"]
    r = client.post("/api/styles", json={"name": "x", "reference_media_ids": [mid]})
    assert r.status_code == 409


def test_cancel_job(client, tmp_root):
    p = tmp_root / "long.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30", "-t", "60",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(p)], check=True)
    mid = _upload_ref(client, p)
    job = client.post(f"/api/references/{mid}/analyze").json()
    time.sleep(0.8)
    r = client.post(f"/api/jobs/{job['id']}/cancel")
    assert r.status_code in (200, 409)
    j = _wait(client, job["id"])
    assert j["status"] == "cancelled", j
    assert client.get(f"/api/references/{mid}/analysis").status_code == 404
