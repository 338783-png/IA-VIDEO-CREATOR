# Installation

## Prérequis (vérifiés le 2026-11-21)

| Outil | Version détectée | Statut |
|---|---|---|
| Ubuntu 24.04 (WSL2 sous Windows 11) | — | ✅ |
| Node.js | 22.23 | ✅ |
| Python | 3.12.3 (+ venv) | ✅ |
| Git | 2.43 | ✅ |
| FFmpeg / FFprobe | 7.0.2 (static) | ✅ |
| Ollama | — | ❌ non installé |

Machine : 15 Go RAM, i7-13620H (16 threads), ~939 Go libres, pas de GPU NVIDIA visible depuis WSL.

## Installer Ollama (optionnel, recommandé)

Dans WSL :
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b     # ~4,9 Go, adapté à 16 Go de RAM en CPU
```
Ou installez Ollama pour Windows (https://ollama.com/download/windows) ; il est alors joignable
depuis WSL si le mode réseau « mirrored » est activé, sinon renseignez `OLLAMA_URL` dans `.env`.

Sans Ollama, l'application démarre et le panneau « État du système » l'indique.

## Installer le projet

```bash
./scripts/install.sh
```
