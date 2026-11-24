# Banc d'essai du rendu 3D (V2.1) — 21/11/2026

Machine : Intel Core i7-13620H (16 threads), Intel UHD Graphics (pas de GPU NVIDIA), 32 Go (WSL : 23 Go).
Blender 4.5.16 LTS. Scène : personnage stylisé, décor (sol, mur, tableau, bureau), 2 lumières, ~26 000 triangles.
Script : `video-engine/blender/benchmark.py`.

## Résultats (rendu d'animation, secondes par image)

| Moteur | Où | 1080×1920 | 60 s de vidéo à 30 i/s (1 800 images) |
|---|---|---|---|
| Workbench | WSL (OpenGL logiciel) | 1,1 s | ≈ 33 min |
| Workbench | Windows (Intel UHD) | 2,2 s | ≈ 65 min |
| **Eevee** (16 échantillons) | **Windows (Intel UHD)** | **6,1 s** | ≈ 3 h |
| Eevee | WSL (OpenGL logiciel) | 22 s | ≈ 11 h ❌ |
| Cycles CPU (16 éch. + débruitage) | WSL | 23 s | ≈ 11 h ❌ |

- Dans WSL, Blender ne peut pas utiliser la puce Intel : le pilote d3d12 échoue en mode sans interface (EGL_BAD_MATCH),
  OpenGL bascule en émulation logicielle (llvmpipe).
- Blender **pour Windows** (portable, `C:\Users\jorda\ProfIA-tools\`) utilise la puce Intel : Eevee y est 3,6× plus rapide.
- Qualité : Eevee ≈ Cycles sur ce type de scène stylisée ; Workbench = aplats sans ombres portées.

## Décision

| Usage | Moteur | Réglages |
|---|---|---|
| Aperçu | Workbench (WSL) | 540×960, couleurs des matériaux, ~0,3-1 s/image |
| Export « rapide » | Workbench (WSL) | 1080×1920 |
| Export « qualité » | Eevee (Blender Windows) | 1080×1920, 8-16 échantillons ; animation des personnages « en deux » (12-15 i/s, style dessin animé) |
| Cycles | non utilisé (trop lent sans GPU NVIDIA) | — |

Pistes d'accélération à mesurer en V2.9 : échantillons Eevee réduits (8), rendu 720×1280 + mise à l'échelle,
images d'animation doublées (15 i/s affichées à 30 i/s), un seul rendu lourd à la fois.
