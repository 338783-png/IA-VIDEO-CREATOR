# AI VIDEO EDITOR – PROF IA

Application web locale de montage vidéo assisté par IA (TikTok, Reels, Shorts, YouTube).
Fonctionne sans Claude Code et sans API payante.

## Démarrage rapide (WSL / Linux)

```bash
./scripts/install.sh   # dépendances Python + Node (une seule fois)
./scripts/start.sh     # http://localhost:3000  (API : http://127.0.0.1:8000/docs)
./scripts/stop.sh
```

Sous Windows natif : `scripts\install.ps1`, `scripts\start.ps1`, `scripts\stop.ps1`.

## Tests

```bash
cd backend && .venv/bin/python -m pytest ../tests/backend -q   # backend (stockage temporaire isolé)
./tests/frontend/run_isolated.sh                                 # instance isolée + captures d'écran (Playwright)
./tests/e2e/run_final_test.sh                                    # PROMPT 7 : scénario complet + rapport
./tests/e2e/run_final_test.sh                                    # PROMPT 7 : scénario complet dans l'interface + rapport
```

## État d'avancement

| Phase | Statut |
|---|---|
| Prompt 1 – socle (frontend, backend, SQLite, import sécurisé, FFmpeg, client Ollama) | ✅ |
| Prompt 2 – analyse de style des références, STYLE-GUIDE.md, config JSON, validation | ✅ |
| Prompt 3 – moteur de montage (analyse, Whisper, storyboard, rendu FFmpeg, aperçu, validation, export MP4) | ✅ |
| Prompt 6 – voix off locale (Piper : 4 modèles, 129 locuteurs, vitesse, pauses, volume, écoute, intégration) | ✅ |
| Prompt 5 – sous-titres (Whisper/TTS, SRT, VTT, incrustés animés, édition manuelle, contrôle de synchro) | ✅ |
| Prompt 4 – tableau de bord (menu latéral, Accueil, Nouveau projet, Bibliothèque, Références, Storyboard, Éditeur, Exportations) | ✅ |
| Prompt 7 – test final (12 étapes dans l'interface, 13 contrôles de la vidéo) — voir documentation/TEST-REPORT.md | ✅ |
| Module 2D « personnages animés » : 2D.1 personnages + scénarios ✅, 2D.2 synchronisation labiale ✅, 2D.3 → 2D.6 | en cours |
| Module 3D – Blender : V2.1 (installation + banc d'essai) ✅, V2.2 → V3.0 | à faire |

Voir [documentation/](documentation/).
