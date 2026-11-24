import os
import stat


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["database"] == "ok"


def test_system_status_ffmpeg(client):
    s = client.get("/api/system/status").json()
    assert s["ffmpeg"]["available"] is True
    assert "available" in s["ollama"]


def test_project_crud_and_archive(client):
    r = client.post("/api/projects", json={"name": "Test", "target_format": "tiktok"})
    assert r.status_code == 201
    pid = r.json()["id"]
    assert client.patch(f"/api/projects/{pid}", json={"instruction": "60 s TikTok"}).json()["instruction"] == "60 s TikTok"
    assert any(p["id"] == pid for p in client.get("/api/projects").json())
    assert client.delete(f"/api/projects/{pid}").json()["archived"] is True
    assert not any(p["id"] == pid for p in client.get("/api/projects").json())
    assert client.get(f"/api/projects/{pid}").status_code == 200  # toujours récupérable


def test_invalid_format_rejected(client):
    r = client.post("/api/projects", json={"name": "x", "target_format": "vine"})
    assert r.status_code == 422


def test_upload_video_ok_and_protected(client, sample_mp4, tmp_root):
    pid = client.post("/api/projects", json={"name": "Upload"}).json()["id"]
    with open(sample_mp4, "rb") as f:
        r = client.post("/api/media/upload", data={"kind": "video", "project_id": str(pid)},
                        files=[("files", ("ma vidéo ../../evil.mp4", f, "video/mp4"))])
    assert r.status_code == 201, r.text
    m = r.json()[0]
    assert m["probe"]["video"]["width"] == 320
    assert ".." not in m["stored_path"] and m["stored_path"].startswith("uploads/")
    stored = tmp_root / "storage" / m["stored_path"]
    mode = os.stat(stored).st_mode
    assert not (mode & stat.S_IWUSR) and not (mode & stat.S_IXUSR)  # lecture seule, non exécutable
    assert client.get(f"/api/media/{m['id']}/file").status_code == 200
    assert client.get(f"/api/media/{m['id']}/thumbnail").status_code == 200
    # archiver le projet ne supprime pas l'original
    client.delete(f"/api/projects/{pid}")
    assert stored.exists()


def test_reject_bad_extension(client):
    r = client.post("/api/media/upload", data={"kind": "video"}, files=[("files", ("run.exe", b"MZ....", "application/octet-stream"))])
    assert r.status_code == 415 and r.json()["error"] == "unsupported_format"


def test_reject_renamed_file(client):
    r = client.post("/api/media/upload", data={"kind": "video"}, files=[("files", ("fake.mp4", b"#!/bin/sh\necho hi\n" * 10, "video/mp4"))])
    assert r.status_code == 415 and r.json()["error"] == "signature_mismatch"


def test_reject_kind_mismatch(client, sample_mp4):
    with open(sample_mp4, "rb") as f:
        r = client.post("/api/media/upload", data={"kind": "audio"}, files=[("files", ("a.mp4", f, "video/mp4"))])
    assert r.status_code == 415


def test_reject_too_large(client, tmp_root):
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (2 * 1024 * 1024)
    r = client.post("/api/media/upload", data={"kind": "image"}, files=[("files", ("big.png", big, "image/png"))])
    assert r.status_code == 413
    assert not any((tmp_root / "storage" / "tmp").iterdir())  # temporaire nettoyé


def test_reference_upload(client, sample_mp4):
    with open(sample_mp4, "rb") as f:
        r = client.post("/api/media/upload", data={"kind": "reference"}, files=[("files", ("ref.mp4", f, "video/mp4"))])
    assert r.status_code == 201 and r.json()[0]["stored_path"].startswith("references/")
