# Guide utilisateur

1. Lancer `./scripts/start.sh` puis ouvrir http://localhost:3000.
2. Vérifier le panneau **État du système** (vert = prêt, orange = partiel, rouge = absent).
3. **Nouveau projet** : nom + format cible.
4. Ouvrir le projet, importer vidéos / audio / images (glisser-déposer).
5. Cliquer un média pour le prévisualiser.
6. Écrire l'instruction de montage et **Enregistrer**.

## Créer un style à partir de références

1. Menu **Références & styles** → importez une ou plusieurs vidéos dont vous aimez le montage.
2. Cliquez **Analyser** (barre de progression, bouton **Annuler** disponible).
3. **Détails** : plans détectés, transitions, zooms, couleurs, sous-titres, audio, avec un niveau de confiance.
4. Cochez les références analysées → **Analyser le style**.
5. Sur la page du style : relisez les règles obligatoires / facultatives et le STYLE-GUIDE.md.
6. Choisissez la **police** (jamais devinée automatiquement), ajustez couleurs, position, transitions.
7. **Valider** : le style devient officiel (fichiers dans `projects/styles/` et `documentation/STYLE-GUIDE.md`).
   Toute modification ultérieure le repasse en brouillon.

## Monter une vidéo

Sur la page d'un projet, suivez les étapes numérotées :

1. **Médias** : importez vos vidéos (MP4, MOV, AVI), musiques/voix (MP3, WAV), images (PNG, JPG), scripts (TXT, MD, SRT).
2. **Analyse** : détection des plans, des silences et transcription Whisper (en français). Annulable.
3. **Consigne** : décrivez la vidéo voulue, par exemple
   « TikTok éducatif de 60 s, sous-titres animés, zooms, transitions dynamiques, musique discrète ».
   Choisissez un style validé (sinon le style officiel ou le style par défaut est utilisé), puis **Générer le storyboard**.
4. **Storyboard** : chaque scène a un début, une fin, une durée, un texte, un effet et une transition.
   Réordonnez (↑ ↓), supprimez (✕), changez les bornes, corrigez le texte, choisissez effets et transitions,
   réglez sous-titres, musique, voix off et cadrage, puis **Enregistrer** (nouvelle version, l'ancienne est conservée).
   Les passages écartés (répétitions, hésitations, silences) sont listés pour contrôle.
5. **Aperçu** : rendu rapide en basse résolution, lisible dans le lecteur.
6. **Validation** : obligatoire avant l'export ; toute modification ultérieure demande une nouvelle validation.
7. **Export** : TikTok / Reels / Shorts (1080×1920) ou YouTube (1920×1080), qualité et images/s au choix.
   Le fichier est vérifié automatiquement et rangé dans `exports/`. **Rien n'est jamais publié automatiquement.**

**Sous-titres** : sous le storyboard, le tableau des sous-titres permet de corriger le texte et les horaires,
de télécharger les fichiers SRT / VTT et de vérifier la synchronisation (badge « synchro ± ms »).
À l'export, les fichiers `.srt` et `.vtt` sont créés à côté de la vidéo.

Remarques :
- Sans Ollama, la sélection des passages se fait par règles (débit, clarté, énergie, mots-clés).
- La musique n'est jamais téléchargée : importez un fichier libre de droits.
- **Voix off** (panneau de gauche) : écrivez ou reprenez le texte, choisissez une voix (et un locuteur),
  la vitesse, les pauses et le volume, cliquez **Écouter un extrait**, puis **Générer**. Réécoutez le résultat,
  puis **Utiliser dans le montage** : la voix off est mixée et les sous-titres suivent ses mots.
  Pensez à citer la voix (attribution affichée) si vous publiez la vidéo.
Vos fichiers originaux ne sont jamais modifiés ni supprimés.
