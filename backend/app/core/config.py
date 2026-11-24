"""Configuration centrale. Valeurs surchargées par le fichier .env à la racine."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]  # AI-VIDEO-EDITOR/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    app_name: str = "AI VIDEO EDITOR – PROF IA"
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    frontend_origin: str = "http://localhost:3000"

    database_url: str = f"sqlite:///{ROOT_DIR / 'projects' / 'project-data' / 'app.db'}"

    storage_dir: Path = ROOT_DIR / "storage"
    exports_dir: Path = ROOT_DIR / "exports"
    projects_dir: Path = ROOT_DIR / "projects"
    logs_dir: Path = ROOT_DIR / "logs"

    max_video_mb: int = 2048
    max_audio_mb: int = 300
    max_image_mb: int = 30
    max_script_mb: int = 2

    blender_bin: str = ""  # vide = recherche automatique (ai/tools/blender-*/blender, puis PATH)
    blender_threads: int = 0  # 0 = tous les cœurs
    render_3d_engine: str = ""  # vide = choisi d'après le banc d'essai (workbench | eevee | cycles)

    whisper_model: str = "small"
    whisper_compute_type: str = "int8"
    whisper_threads: int = 0  # 0 = automatique

    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"

    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.1:8b"

    @property
    def tmp_dir(self) -> Path:
        return self.storage_dir / "tmp"

    @property
    def models_dir(self) -> Path:
        return ROOT_DIR / "ai" / "models"


settings = Settings()

# Catégorie -> extensions autorisées
ALLOWED_EXTENSIONS: dict[str, set[str]] = {
    "video": {".mp4", ".mov", ".avi"},
    "audio": {".mp3", ".wav"},
    "image": {".png", ".jpg", ".jpeg"},
    "script": {".txt", ".md", ".srt"},
}

# Catégorie d'usage -> sous-dossier de storage/
KIND_DIRS = {"video": "uploads", "audio": "audio", "image": "images", "reference": "references", "script": "scripts"}
