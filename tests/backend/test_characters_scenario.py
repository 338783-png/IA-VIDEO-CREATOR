"""Module 2D.1 : bibliothèque de personnages et scénarios dialogués (génération IA + édition manuelle)."""
import json
import os
import time

import pytest

from app.services import ollama_service, scenario, tts


def _wait(client, jid, timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.5)
    raise AssertionError("tâche trop longue")


@pytest.fixture(scope="module")
def cast(client):
    voice = next((v for v in tts.list_voices() if not v["excluded"]), None)
    v = {"voice_id": voice["id"], "speaker": voice["speakers"][0]["id"] if voice["speakers"] else None, "speed": 1.05} if voice else None
    a = client.post("/api/characters", json={"name": "Prof Léa", "description": "professeure enthousiaste", "voice": v,
                                             "appearance": {"skin": "#F2C9A0", "hair": "#3B2A20"}}).json()
    b = client.post("/api/characters", json={"name": "Max", "description": "élève curieux"}).json()
    return a, b


def test_character_library(client, cast):
    a, b = cast
    names = [c["name"] for c in client.get("/api/characters").json()]
    assert "Prof Léa" in names and "Max" in names
    r = client.patch(f"/api/characters/{b['id']}", json={"name": "Maxime"}).json()
    assert r["name"] == "Maxime"
    dup = client.post(f"/api/characters/{a['id']}/duplicate").json()
    assert dup["name"] == "Prof Léa (copie)" and dup["appearance"] == a["appearance"] and dup["id"] != a["id"]
    assert client.delete(f"/api/characters/{dup['id']}").json()["archived"]
    assert client.get(f"/api/characters/{dup['id']}").status_code == 404
    assert client.post("/api/characters", json={"name": "X", "voice": {"voice_id": "inconnue"}}).status_code == 422
    assert client.post("/api/characters", json={"name": "X", "kind": "4d"}).status_code == 422
    assert client.post("/api/characters", json={"name": "X", "appearance": {"a": "x" * 30000}}).status_code == 422


def test_manual_scenario(client, cast):
    a, b = cast
    pid = client.post("/api/projects", json={"name": "Dessin animé IA", "project_type": "2d"}).json()["id"]
    assert client.get(f"/api/projects/{pid}/scenario").status_code == 404
    data = {"title": "L'IA expliquée", "scenes": [
        {"title": "Accroche", "setting": "salle de classe", "camera": "plan_moyen", "lines": [
            {"character_id": a["id"], "text": "Savais-tu qu'une IA apprend avec des exemples ?", "emotion": "enthousiaste", "intention": "accrocher"},
            {"character_id": b["id"], "text": "Comme moi avec mes exercices ?", "emotion": "surpris"},
            {"character_id": b["id"], "text": "   ", "emotion": "neutre"}]},
        {"camera": "camera_inexistante", "lines": [{"character_id": a["id"], "text": "Exactement !", "emotion": "émotion inconnue", "pause_after": 9}]}]}
    s = client.put(f"/api/projects/{pid}/scenario", json=data).json()
    assert s["version"] == 1 and s["status"] == "draft"
    d = s["data"]
    assert d["lines_count"] == 3  # réplique vide supprimée
    assert d["scenes"][1]["camera"] == "plan_moyen" and d["scenes"][1]["lines"][0]["emotion"] == "neutre"
    assert d["scenes"][1]["lines"][0]["pause_after"] == 3.0 and d["estimated_seconds"] > 3
    bad = json.loads(json.dumps(data))
    bad["scenes"][0]["lines"][0]["character_id"] = 99999
    assert client.put(f"/api/projects/{pid}/scenario", json=bad).json()["error"] == "bad_character"
    assert client.put(f"/api/projects/{pid}/scenario", json={"scenes": []}).status_code == 422
    assert client.put(f"/api/projects/{pid}/scenario", json={**data, "base_version": 0}).json()["error"] == "version_conflict"
    s2 = client.put(f"/api/projects/{pid}/scenario", json={**s["data"], "base_version": 1}).json()
    assert s2["version"] == 2
    assert client.post(f"/api/projects/{pid}/scenario/validate", json={"version": 1}).status_code == 409
    assert client.post(f"/api/projects/{pid}/scenario/validate", json={"version": 2}).json()["status"] == "validated"


def test_generation_with_mocked_llm(client, cast, monkeypatch):
    a, b = cast
    answers = iter(["pas du json", json.dumps({"title": "IA", "scenes": [{"id": "sc1", "setting": "labo", "camera": "zoom_avant", "lines": [
        {"character_id": a["id"], "text": "Une IA, c'est un programme qui apprend.", "emotion": "joyeux"},
        {"character_id": b["id"], "text": "Et elle apprend comment ?", "emotion": "pensif"}]}]})])
    monkeypatch.setattr(ollama_service, "status", lambda: {"model_ready": True, "available": True})
    monkeypatch.setattr(ollama_service, "generate", lambda *a_, **k: next(answers))
    pid = client.post("/api/projects", json={"name": "Généré", "project_type": "2d"}).json()["id"]
    j = _wait(client, client.post(f"/api/projects/{pid}/scenario/generate",
                                  json={"topic": "l'intelligence artificielle", "character_ids": [a["id"], b["id"]], "target_seconds": 30}).json()["id"])
    assert j["status"] == "done", j  # 2e tentative réussie après un JSON invalide
    s = client.get(f"/api/projects/{pid}/scenario").json()
    assert s["data"]["generated"] and s["data"]["scenes"][0]["camera"] == "zoom_avant" and s["data"]["topic"] == "l'intelligence artificielle"


def test_generation_without_ollama(client, cast, monkeypatch):
    monkeypatch.setattr(ollama_service, "status", lambda: {"model_ready": False, "available": False})
    pid = client.post("/api/projects", json={"name": "Sans IA"}).json()["id"]
    j = _wait(client, client.post(f"/api/projects/{pid}/scenario/generate", json={"topic": "les volcans", "character_ids": [cast[0]["id"]]}).json()["id"])
    assert j["status"] == "failed" and "à la main" in j["error"]


@pytest.mark.skipif(os.environ.get("RUN_LLM_TESTS") != "1" or not ollama_service.status()["model_ready"],
                    reason="lent (~5 min sur CPU) : RUN_LLM_TESTS=1 pour l'exécuter, Ollama requis")
def test_generation_real_llm():
    s = scenario.generate("comment fonctionne l'intelligence artificielle", [{"id": 1, "name": "Prof Léa", "description": "professeure"},
                          {"id": 2, "name": "Max", "description": "élève curieux"}], 40, "pédagogique")
    print("\n", json.dumps(s, ensure_ascii=False, indent=1)[:1500])
    assert s["lines_count"] >= 3 and {ln["character_id"] for sc in s["scenes"] for ln in sc["lines"]} <= {1, 2}
    assert 10 < s["estimated_seconds"] < 120
