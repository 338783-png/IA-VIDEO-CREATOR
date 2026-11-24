# Rapport de test final — AI VIDEO EDITOR (PROMPT 7)

Date : 22/11/2026 00:57 · Instance isolée (données temporaires) · Navigateur automatisé (Chromium)

**Résultat global : ✅ RÉUSSI** — 12/12 étapes

## Scénario

| # | Étape | Résultat | Durée | Détail |
|---|---|---|---|---|
| 1 | Créer un projet | ✅ | 3.5 s | 1 |
| 2 | Importer une vidéo | ✅ | 0 s | rush_astuces.mp4 présent dans les médias du projet |
| 3 | Importer une référence | ✅ | 10.8 s | référence analysée, style créé |
| 4 | Analyser le contenu | ✅ | 37.7 s | plans, silences et transcription Whisper |
| 5 | Générer les sous-titres | ✅ | 0 s | « Aujourd'hui, je vais vous montrer trois astuces. Aujourd'hui, je vais vous montrer trois |
| 6 | Préparer un storyboard (avec le style) | ✅ | 44.7 s | 7 scènes, style « Style test final » appliqué |
| 7 | Appliquer un style (validation du style) | ✅ | 2.5 s | police choisie, style validé comme officiel |
| 8 | Prévisualiser | ✅ | 8.1 s | aperçu lisible dans le lecteur (12.6 s) |
| 9 | Modifier une scène | ✅ | 8.3 s | effet « zoom arrière » + texte corrigé → version 2, aperçu régénéré |
| 10 | Valider | ✅ | 0.2 s | version 2 validée |
| 11 | Exporter en MP4 | ✅ | 18 s | export TikTok 1080×1920, qualité standard, 30 i/s |
| 12 | Vérifier la vidéo finale | ✅ | 0 s | 13/13 contrôles réussis |

## Vérification de la vidéo finale

| Contrôle | Résultat | Valeur |
|---|---|---|
| Conteneur MP4 | ✅ | mov,mp4,m4a,3gp,3g2,mj2 |
| Vidéo H.264 | ✅ | h264 High |
| Audio AAC | ✅ | aac 48000 Hz |
| Résolution 1080×1920 | ✅ | 1080×1920 |
| 30 images/s | ✅ | 30/1 |
| Durée = storyboard | ✅ | 12.58 s / 12.58 s |
| Volume ≈ -14 LUFS | ✅ | -14.5 LUFS |
| Version validée exportée | ✅ | v2 |
| Modification de scène conservée | ✅ | zoom_out / « TEXTE MODIFIÉ À LA MAIN » |
| Style appliqué | ✅ | Style test final |
| Fichiers SRT + VTT | ✅ | 31 sous-titres |
| Synchro sous-titres/voix | ✅ | écart max 0 ms |
| Original non modifié | ✅ | fichiers sources présents, lecture seule |

## Erreurs JavaScript dans le navigateur

Aucune.

## Reproduire

```bash
./tests/e2e/run_final_test.sh
```
## Corrections apportées grâce au test final

| Problème trouvé | Correction | Test de non-régression |
|---|---|---|
| « 2e astuce. » pris pour une prise ratée de « 3e astuce. » | les phrases de moins de 4 mots ne sont jamais des répétitions | `test_short_sentences_never_repetitions` |
| Titre « Première astuce. » séparé de son contenu par Whisper | phrase ≤ 3 mots collée à la suivante si elles s'enchaînent (< 0,8 s) | `test_short_headings_kept_and_merged` |
| L'IA retirait une astuce alors que tout tenait dans la durée | si le contenu utile ≤ durée visée : tout est gardé, dans l'ordre | `test_keep_everything_when_content_fits` |
| Contrôle de synchro faussé par un arrondi (499 ms affichés à tort) | chaque sous-titre comparé au mot qu'il affiche | `test_sync_report_ignores_previous_word_rounding` |

Remarque : lors d'une exécution, l'export a semblé durer 2 h 16 ; la tâche a été suspendue avec le PC
(mise en veille). Mesure refaite : 18 s.
