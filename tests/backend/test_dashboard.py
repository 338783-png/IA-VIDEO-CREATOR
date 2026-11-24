"""Données du tableau de bord (Prompt 4) : cartes de projets, vue des storyboards, liste des exports."""
import time


def _wait(client, jid, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.25)
    raise AssertionError("tâche trop longue")


def test_dashboard_data(client, sample_mp4):
    pid = client.post("/api/projects", json={"name": "Carte", "project_type": "2d"}).json()["id"]
    card = next(p for p in client.get("/api/projects").json() if p["id"] == pid)
    assert card["thumbnail_media_id"] is None and card["media_count"] == 0 and card["storyboard_version"] is None

    with open(sample_mp4, "rb") as f:
        mid = client.post("/api/media/upload", data={"kind": "video", "project_id": str(pid)},
                          files=[("files", ("plan.mp4", f, "video/mp4"))]).json()[0]["id"]
    _wait(client, client.post(f"/api/projects/{pid}/analyze", json={"transcribe": False}).json()["id"])
    _wait(client, client.post(f"/api/projects/{pid}/storyboard/generate", json={"instruction": "court", "use_llm": False}).json()["id"])
    card = next(p for p in client.get("/api/projects").json() if p["id"] == pid)
    assert card["thumbnail_media_id"] == mid and card["media_count"] == 1
    assert card["storyboard_version"] == 1 and card["storyboard_status"] == "draft" and card["exports_count"] == 0

    sbs = client.get("/api/storyboards").json()
    row = next(r for r in sbs if r["project_id"] == pid)
    assert row["project_name"] == "Carte" and row["scenes"] >= 1 and row["has_preview"] is False

    _wait(client, client.post(f"/api/projects/{pid}/storyboard/preview").json()["id"])
    client.post(f"/api/projects/{pid}/storyboard/validate", json={"version": 1})
    _wait(client, client.post(f"/api/projects/{pid}/export", json={"platform": "shorts", "quality": "rapide", "fps": 30, "confirm": True}).json()["id"])
    exps = client.get("/api/exports", params={"project_id": pid}).json()
    assert len(exps) == 1 and exps[0]["project_name"] == "Carte" and exps[0]["file_exists"] and exps[0]["size_bytes"] > 0
    assert exps[0]["path"].startswith("exports/youtube/")  # les Shorts sont rangés avec YouTube
    assert client.get("/api/exports", params={"platform": "tiktok", "project_id": pid}).json() == []
    assert next(p for p in client.get("/api/projects").json() if p["id"] == pid)["exports_count"] == 1
