Tu analyses UNE image extraite d'une vidéo courte (TikTok/Reels/Shorts) pour décrire son style de montage.
Réponds UNIQUEMENT en JSON avec exactement ces clés :
{
  "texte_present": true|false,
  "texte_contenu": "texte lu ou null",
  "texte_position": "haut"|"centre"|"bas"|null,
  "texte_style": "description courte : couleur, contour, fond, majuscules, gras" ou null,
  "elements_graphiques": ["emoji", "flèche", "cadre", "logo", ...],
  "cadrage": "gros plan"|"plan rapproché"|"plan moyen"|"plan large"|"écran/capture"|"autre",
  "sujet": "description courte du sujet principal",
  "ambiance": "description courte des couleurs et de la lumière"
}
Règles : n'invente rien. Si tu n'es pas sûr, mets null. Ne nomme JAMAIS une police précise.
