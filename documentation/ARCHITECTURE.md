# Architecture

```
frontend/ (Next.js 15, React 19, TS, Tailwind 4)  ──HTTP/JSON──▶  backend/ (FastAPI, SQLAlchemy, SQLite)
                                                                     ├─ services/ffmpeg_service  → ffmpeg / ffprobe (subprocess, args en liste)
                                                                     ├─ services/ollama_service  → http://127.0.0.1:11434
                                                                     └─ services/storage_service → storage/
```

## Backend (`backend/app`)

| Module | Rôle |
|---|---|
| `core/config.py` | Paramètres (`.env`), formats autorisés, limites |
| `core/database.py` | Moteur SQLite (WAL, clés étrangères) |
| `core/security.py` | Validation extension + signature binaire, noms de stockage sûrs, anti path-traversal, originaux en lecture seule |
| `core/errors.py` | Erreurs JSON homogènes `{error, detail}` + journalisation |
| `api/system.py` | `/api/health`, `/api/system/status`, `/api/ai/test` |
| `api/projects.py` | CRUD projets (DELETE = archivage, aucun fichier supprimé) |
| `api/media.py` | Import multi-fichiers, liste, lecture, miniature |

## Chaîne d'import

1. Extension vérifiée (MP4, MOV, AVI, MP3, WAV, PNG, JPG).
2. Écriture en flux dans `storage/tmp/` avec limite de taille.
3. Signature binaire comparée à l'extension.
4. `ffprobe` doit lire le fichier et trouver la piste attendue.
5. Déplacement vers `storage/<type>/` sous un nom unique, `chmod 444`.
6. Miniature générée pour les vidéos.

En cas d'échec, seul le fichier temporaire est supprimé.

## Données

- Base : `projects/project-data/app.db`
- Journaux : `logs/backend.log`
- Exports : `exports/{tiktok,reels,youtube}/`

## Analyse de style (Prompt 2)

```
Référence importée ─▶ POST /api/references/{id}/analyze ─▶ tâche de fond (services/jobs.py)
                                                           │  progression + annulation (sous-processus FFmpeg tués)
                                                           ▼
services/analysis/reference_analyzer.py
  ├─ decode.py      FFmpeg → images RGB réduites (72 px) + audio mono 22 kHz
  ├─ scenes.py      coupes franches (variation image+histogramme, seuil adaptatif)
  │                 fondus enchaînés (test de mélange alpha), fondus au noir / flashs (creux de luminosité)
  ├─ motion.py      zoom (recherche d'échelle), panoramique (corrélation de phase), tremblement
  ├─ colors.py      palette k-means, luminosité, contraste, saturation, température
  ├─ captions.py    texte clair à contour noir → position, couleurs, cadence (police jamais devinée)
  ├─ audio.py       LUFS (ebur128), silences, attaques, tempo, coupes sur le temps, effets aux coupes
  └─ vision.py      optionnel : modèle de vision Ollama (gemma3, llava, moondream…) → descriptions JSON
          ▼
ReferenceAnalysis (SQLite) ─▶ POST /api/styles ─▶ services/style_builder.py
                                                  obligatoire / facultatif / propre à chaque scène
                                                  + config JSON moteur + STYLE-GUIDE.md
          ▼
StyleProfile (brouillon) ─▶ PATCH (ajustements) ─▶ POST /validate
                                                  → projects/styles/style-<id>-<nom>/{style.json, STYLE-GUIDE.md}
                                                  → documentation/STYLE-GUIDE.md (style officiel)
```

Chaque mesure incertaine porte une `confidence` (élevée / moyenne / faible) et sa méthode.
Une règle de confiance « faible » n'est jamais classée obligatoire.
Les références ne sont jamais réutilisées : seules des mesures et des miniatures internes
(`storage/thumbnails/ref_<id>/`) sont conservées.

Vérification : `tests/video/make_reference.py` génère une vidéo dont tout est connu (coupes, fondus,
zoom, panoramique, sous-titres, 120 BPM) ; `tests/backend/test_style_analysis.py` compare l'analyse à cette vérité.

## Moteur de montage (Prompt 3)

```
Médias du projet ──▶ POST /api/projects/{id}/analyze  (tâche annulable)
                      services/media_analyzer.py
                        ├─ plans (détection des coupes, 10 i/s), mouvement et énergie par seconde
                        ├─ silences relatifs à la parole, tempo des musiques
                        └─ services/transcription.py : faster-whisper (mots horodatés, VAD)
                    ──▶ MediaAnalysis (SQLite)

Consigne + style ──▶ POST /storyboard/generate
                      services/instruction_parser.py : règles FR (durée, plateforme, voix off, négations…) + Ollama (facultatif)
                      services/planner.py
                        ├─ phrases à partir des mots, marges sans chevauchement
                        ├─ répétitions (prise reprise → on garde la dernière), hésitations seules, silences → écartés
                        ├─ score (débit, clarté, énergie, mots-clés, accroche) ; plans visuels si pas de parole
                        ├─ sélection : Ollama (réponse vérifiée) sinon glouton + ordre chronologique
                        ├─ découpe des longues phrases aux frontières de mots + recadrage alterné (jump cut)
                        ├─ transitions jamais au milieu d'une phrase ; zooms/transitions répartis selon le style
                        └─ musique / voix off / sous-titres selon la consigne
                    ──▶ Storyboard v1 (JSON + projects/storyboards/project-<id>/storyboard_v001.json)

Modifications ──▶ PUT /storyboard  → validation stricte → nouvelle version (historique conservé)
Aperçu        ──▶ POST /storyboard/preview  → services/renderer.py (demi-résolution, ultrafast)
Validation    ──▶ POST /storyboard/validate (exige l'aperçu de la version courante)
Export        ──▶ POST /export {confirm: true} (exige la validation) → exports/<plateforme>/… + vérification ffprobe
```

### Rendu (services/renderer.py)

1. Chaque scène est rendue isolément dans `storage/tmp/render_*/` : découpe précise, recadrage
   (remplir ou image entière + fond flou), effet (zoom avant/arrière, punch-in, panoramique), audio sans clic.
2. Assemblage : `concat` pour les coupes, `xfade`/`acrossfade` pour les transitions, sous-titres ASS (libass),
   voix off, musique en boucle baissée sous la voix (`sidechaincompress`), normalisation −14 LUFS (`loudnorm`).
3. Export : H.264 High + AAC 192 kb/s, `+faststart`, puis vérification (codecs, résolution, fps, durée).

Les fichiers temporaires sont supprimés après chaque rendu ; les sources ne sont jamais modifiées
et un export n'écrase jamais un fichier existant (horodatage dans le nom).

### Choix techniques

- **faster-whisper** plutôt que `openai-whisper` : mêmes modèles Whisper, sans PyTorch (~150 Mo au lieu
  de 1-2 Go), ~4× plus rapide sur CPU. Modèle par défaut `small` (`WHISPER_MODEL` dans `.env` : tiny, base,
  small, medium). Modèles stockés dans `ai/models/whisper/`.
- **Remotion non utilisé dans cette version** : tout le montage (effets, transitions, sous-titres animés) est
  réalisable avec FFmpeg + libass, sans navigateur Chromium à télécharger et sans question de licence.
  Remotion reste envisageable plus tard pour des animations graphiques complexes (sa licence est gratuite
  pour les particuliers et petites structures, payante au-delà : à vérifier avant tout usage commercial).
- FFmpeg de ce poste : pas de `drawtext`, mais `libass` → tous les textes passent par des sous-titres ASS.

## Voix off (Prompt 6)

- `services/tts.py` : Piper chargé en mémoire une fois par voix, avec **alignements de phonèmes**
  (`include_alignments`, nécessite le paquet `onnx`). Chaque mot reçoit ses horaires réels :
  sous-titres mot à mot exacts et, plus tard, synchronisation labiale 2D/3D.
- Vitesse = `length_scale` (1/vitesse), pauses insérées entre phrases, volume en dB.
- `POST /api/voices/preview` : extrait de 400 caractères max, renvoyé en WAV, **non enregistré** (écoute avant validation).
- `POST /api/projects/{id}/voiceover` (tâche) : WAV enregistré comme média audio du projet (lecture seule)
  + table `voice_tracks` (texte, voix, paramètres, mots, phonèmes).
- Montage : `audio.voiceover_media_id` → la voix off est mixée (son original baissé) et
  `subtitles.source = "voiceover"` affiche ses mots. Une voix off plus longue que le montage déclenche un avertissement.

| Voix installée | Locuteurs | Licence |
|---|---|---|
| fr_FR-siwis-medium | 1 | CC-BY 4.0 |
| fr_FR-upmc-medium | 2 | CC-BY-SA 4.0 |
| fr_FR-mls-medium | 125 | CC-BY 4.0 |
| fr_FR-gilles-low | 1 | CC0 |

Les licences CC-BY imposent de **citer la voix** si la vidéo est diffusée (texte d'attribution fourni dans l'interface).
Les voix sous AGPL (ex. `tom`) sont refusées par défaut. **Piper lui-même est sous GPL-3.0** : sans incidence
pour un usage personnel, à étudier avant toute distribution publique de l'application.

## Sous-titres (Prompt 5)

- Source des mots : transcription Whisper des scènes **ou** horaires exacts de la voix off TTS (`subtitles.source`).
- `services/subtitles_export.py` : segments automatiques (mêmes regroupements que l'incrustation : mot à mot,
  2-3 mots, phrases), export **SRT** et **WebVTT**, contrôle de synchronisation (écart entre chaque sous-titre et
  le premier mot prononcé ; ≤ 150 ms = OK).
- Édition manuelle : `subtitles.manual_cues` (texte et horaires) remplace l'automatique, y compris dans la vidéo
  incrustée ; chevauchements refusés ; `null` = retour à l'automatique.
- `GET /api/projects/{id}/subtitles?format=json|srt|vtt` ; à chaque export MP4, des fichiers `.srt` et `.vtt`
  du même nom sont écrits à côté de la vidéo.
- Polices, couleurs (texte, mot surligné, contour), taille, position, majuscules et animation (pop mot à mot,
  karaoké) : réglages du storyboard, rendus par libass.

## Tableau de bord (Prompt 4)

- `components/Sidebar.tsx` : menu latéral commun (barre horizontale défilante sur mobile) — Accueil, Nouveau projet,
  Bibliothèque, Références, Storyboard, Éditeur, Exportations.
- Pages : `/` (cartes de projets, état du système, derniers exports), `/new` (2D/3D, format, consigne, import direct),
  `/library` (tous les médias, filtres, aperçu), `/references`, `/storyboard` (dernière version par projet),
  `/editor` (choix du projet → `/projects/[id]`), `/exports` (lecture, vérifications, MP4/SRT/VTT).
- API ajoutées : `GET /api/projects` enrichi (miniature, nombre de médias, version du storyboard, exports),
  `GET /api/storyboards`, `GET /api/exports?project_id=&platform=`.
- L'espace disque affiché tient compte de WSL : c'est l'espace libre du disque Windows C: qui limite réellement.
- Contrôle visuel : `tests/frontend/run_isolated.sh` lance une instance isolée (ports 8100/3100, données temporaires),
  la remplit (`seed_demo.py`), prend des captures PC et mobile (`screenshots.mjs`) et signale les erreurs JavaScript
  et les débordements horizontaux.

## Module 2D — étape 2D.1 : personnages et scénarios (communs 2D/3D)

- Table `characters` : nom, type (2d/3d), description, apparence (JSON), voix (voix Piper, locuteur, vitesse), paramètres.
  Suppression = archivage (les projets qui l'utilisent restent intacts). Page **Personnages** : créer, modifier,
  dupliquer, supprimer, écouter la voix.
- Table `scenarios` (versionnée) : titre, sujet, scènes (décor, cadrage), répliques (personnage, texte, émotion,
  intention, pause). `services/scenario.py` valide strictement (personnages existants, émotions/cadrages connus,
  limites de taille) et estime la durée (≈ 2,6 mots/s).
- Génération : `POST /api/projects/{id}/scenario/generate` (tâche annulable) → Ollama avec `ai/prompts/scenario_dialogue.md`,
  2 tentatives, réponse toujours validée. Sans Ollama : message clair, écriture manuelle possible.
  Durée observée sur ce PC : ~5 min pour un scénario de 40 s.
- Édition manuelle : `PUT /api/projects/{id}/scenario` (nouvelle version) puis `POST …/scenario/validate`.
- `services/cartoon/character.py` : dessinateur de personnages 2D (Pillow) préparé pour l'étape 2D.2.

## Synchronisation labiale (module 2D.2, commune 2D/3D)

`services/lipsync.py` transforme la parole en **visèmes** canoniques :
`rest` (repos), `MBP` (lèvres fermées), `A`, `E`, `I`, `O`, `U`, `FV` (lèvre sur les dents), `L` (langue).

| Source | Fonction | Précision |
|---|---|---|
| Voix Piper (horaires de phonèmes) | `track_from_phonemes` | exacte (alignements du modèle) |
| Enregistrement + mots Whisper | `track_from_words` | phonèmes répartis dans chaque mot |
| Son seul | `track_from_audio` | ouverture selon le volume |

- Anticipation de 30 ms (la bouche se forme juste avant le son).
- Anti-scintillement : 40 ms minimum par forme, 35 ms pour une fermeture ; une voyelle n'est jamais
  avalée par une fermeture voisine (« m-a-p »).
- `adapt(visème, formes_disponibles)` : couche d'adaptation par personnage (2D ou rig 3D VRM / ARKit / mâchoire
  simple) — forme la plus proche, sinon ouvert/fermé.
- Vérifié : chaque « m/b/p » prononcé par Piper ferme les lèvres à l'instant correspondant (`tests/backend/test_lipsync.py`).
