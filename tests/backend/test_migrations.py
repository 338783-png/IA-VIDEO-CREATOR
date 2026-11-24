"""La mise à jour du schéma ajoute les colonnes manquantes sans perdre les données existantes."""
import sqlite3

from sqlalchemy import create_engine, text

from app.core import migrations


def test_add_project_type_keeps_data(tmp_path):
    db = tmp_path / "ancien.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY, name VARCHAR(200), target_format VARCHAR(20))")
    con.execute("INSERT INTO projects (name, target_format) VALUES ('Mon ancien projet', 'reels')")
    con.commit()
    con.close()
    eng = create_engine(f"sqlite:///{db}")
    assert migrations.apply(eng) == ["projects.project_type"]
    assert migrations.apply(eng) == []  # idempotent
    with eng.connect() as c:
        row = c.execute(text("SELECT name, target_format, project_type FROM projects")).one()
    assert tuple(row) == ("Mon ancien projet", "reels", "2d")


def test_create_3d_project(client):
    r = client.post("/api/projects", json={"name": "Dessin animé", "project_type": "3d"})
    assert r.status_code == 201 and r.json()["project_type"] == "3d"
    assert client.post("/api/projects", json={"name": "x"}).json()["project_type"] == "2d"
    assert client.post("/api/projects", json={"name": "x", "project_type": "4d"}).status_code == 422
