import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

# IMPORTANT : fixé au chargement de conftest, avant que les modules de test n'importent l'application,
# pour que les tests n'écrivent JAMAIS dans les vrais dossiers du projet.
_TMP = Path(tempfile.mkdtemp(prefix="aive-tests-"))
os.environ.update({
    "STORAGE_DIR": str(_TMP / "storage"), "EXPORTS_DIR": str(_TMP / "exports"),
    "PROJECTS_DIR": str(_TMP / "projects"), "LOGS_DIR": str(_TMP / "logs"),
    "DATABASE_URL": f"sqlite:///{_TMP / 'test.db'}", "MAX_IMAGE_MB": "1",
})

from app.core.config import settings  # noqa: E402

assert str(settings.storage_dir).startswith(str(_TMP)), "Les tests doivent utiliser un stockage temporaire"
assert str(settings.exports_dir).startswith(str(_TMP))
assert "test.db" in settings.database_url


@pytest.fixture(scope="session")
def tmp_root():
    return _TMP


@pytest.fixture(scope="session")
def client(tmp_root):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def sample_mp4(tmp_root) -> Path:
    out = tmp_root / "sample.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(out)], check=True)
    return out
