"""Tests unitaires du planificateur (transcription simulée, sans Whisper ni LLM)."""
from app.services import planner, subtitles_ass, timeline


def W(word, s, e):
    return {"word": word, "start": s, "end": e, "prob": 0.95}


def fake_transcript():
    # prise ratée puis reprise, hésitation, puis phrases utiles
    words = [
        W("Aujourd'hui", 0.5, 1.0), W("je", 1.0, 1.1), W("vais", 1.1, 1.3), W("vous", 1.3, 1.5), W("montrer", 1.5, 2.0), W("trois", 2.0, 2.3), W("astuces.", 2.3, 2.9),
        W("Aujourd'hui", 4.0, 4.5), W("je", 4.5, 4.6), W("vais", 4.6, 4.8), W("vous", 4.8, 5.0), W("montrer", 5.0, 5.5), W("trois", 5.5, 5.8), W("astuces", 5.8, 6.2), W("simples.", 6.2, 6.8),
        W("Euh...", 8.0, 8.6),
        W("Première", 10.0, 10.5), W("astuce", 10.5, 11.0), W(":", 11.0, 11.05), W("toujours", 11.1, 11.6), W("préparer", 11.6, 12.1), W("son", 12.1, 12.3), W("plan", 12.3, 12.6),
        W("avant", 12.6, 13.0), W("de", 13.0, 13.1), W("filmer", 13.1, 13.5), W("pour", 13.5, 13.7), W("gagner", 13.7, 14.0), W("du", 14.0, 14.1), W("temps", 14.1, 14.5),
        W("au", 14.5, 14.6), W("montage", 14.6, 15.0), W("et", 15.0, 15.1), W("éviter", 15.1, 15.5), W("les", 15.5, 15.6), W("oublis.", 15.6, 16.2),
    ]
    return {"words": words, "segments": []}


def test_sentences_and_repetitions():
    sents = planner.sentences_from_transcript(1, fake_transcript(), 20.0)
    assert len(sents) == 4
    planner.mark_repetitions(sents)
    assert sents[0].get("reject", "").startswith("répétition")  # première prise ratée
    assert "reject" not in sents[1]
    assert sents[2].get("reject") == "hésitation seule"
    assert sents[0]["end"] <= sents[1]["start"]  # pas de chevauchement


def test_split_long_keeps_audio_contiguous():
    sents = planner.sentences_from_transcript(1, fake_transcript(), 20.0)
    long = sents[3]
    parts = planner.split_long(long, max_shot=3.0, target_shot=2.5)
    assert len(parts) >= 2
    assert parts[0]["start"] == long["start"] and parts[-1]["end"] == long["end"]
    for a, b in zip(parts, parts[1:]):
        assert a["end"] == b["start"]  # découpe aux frontières de mots, sans trou


def _media():
    return [{"id": 1, "kind": "video", "category": "video", "original_name": "talk.mp4", "probe": {"duration": 20.0, "audio": {}}}]


def test_build_storyboard_rules_only():
    sb = planner.build({"id": 1, "target_format": "tiktok"}, _media(), {1: {"duration": 20.0, "silences": [[7.0, 9.9]]}},
                       {1: fake_transcript()}, None, {"id": None, "name": "défaut"},
                       "TikTok de 15 secondes avec sous-titres animés et zooms", {}, use_llm=False)
    assert sb["format"] == {"platform": "tiktok", "width": 1080, "height": 1920, "fps": 30}
    texts = " ".join(s["text"] for s in sb["scenes"])
    assert "simples." in texts and "Première" in texts
    assert not any(r["reason"].startswith("répétition") is False and r["reason"] == "" for r in sb["rejected"])
    assert any(r["reason"].startswith("répétition") for r in sb["rejected"])
    for s in sb["scenes"]:
        assert set(s) >= {"id", "media_id", "start", "end", "duration", "text", "effect", "transition", "position"}
    # transitions uniquement entre passages non contigus
    for a, b in zip(sb["scenes"], sb["scenes"][1:]):
        if a["media_id"] == b["media_id"] and abs(a["end"] - b["start"]) < 0.05:
            assert a["transition"] == "cut"
    assert sb["subtitles"]["enabled"] and sb["subtitles"]["animated"]
    assert any(s["effect"] != "none" for s in sb["scenes"])  # zooms demandés


def test_timeline_and_ass_mapping():
    scenes = [
        {"id": "a", "start": 10.0, "end": 12.0, "duration": 2.0, "transition": "crossfade", "transition_duration": 0.5, "text": "un deux", "text_auto": True,
         "words": [{"word": "un", "start": 10.2, "end": 10.6}, {"word": "deux", "start": 11.0, "end": 11.4}]},
        {"id": "b", "start": 3.0, "end": 5.0, "duration": 2.0, "transition": "cut", "text": "trois", "text_auto": True,
         "words": [{"word": "trois", "start": 3.5, "end": 4.0}]},
    ]
    starts, total = timeline.compute(scenes)
    assert starts == [0.0, 1.5] and total == 3.5
    sb = {"scenes": scenes, "format": {"width": 1080, "height": 1920},
          "subtitles": {"enabled": True, "mode": "word", "position": "bas", "font": "DejaVu Sans", "animated": True, "uppercase": True}}
    words = subtitles_ass.timeline_words(sb)
    assert [round(w["start"], 2) for w in words] == [0.2, 1.0, 2.0]  # 1.5 + (3.5 - 3.0)
    ass = subtitles_ass.build_ass(sb)
    assert "TROIS" in ass and "PlayResY: 1920" in ass and r"\fscx" in ass


def test_manual_text_is_spread_evenly():
    sb = {"scenes": [{"id": "a", "start": 0, "end": 3, "duration": 3.0, "transition": "cut", "text": "mon texte corrigé", "text_auto": False, "words": []}],
          "format": {"width": 1080, "height": 1920}, "subtitles": {"enabled": True, "mode": "chunk"}}
    words = subtitles_ass.timeline_words(sb)
    assert [w["word"] for w in words] == ["mon", "texte", "corrigé"] and words[-1]["end"] == 3.0


def test_merge_whisper_tokens():
    toks = [W("Aujourd", 0, 0.3), W("'hui", 0.3, 0.5), W("quelqu", 0.6, 0.8), W("'un", 0.8, 0.9), W("d'", 1.0, 1.1), W("autre", 1.1, 1.4), W("peut", 1.5, 1.6), W("-être", 1.6, 1.9)]
    assert planner.join_words(toks) == "Aujourd'hui quelqu'un d'autre peut-être"
    assert planner.merge_word_tokens(toks)[0]["end"] == 0.5


def test_short_headings_kept_and_merged():
    """Régression (test final) : « 2e astuce. » n'est pas une prise ratée ; un titre court reste collé à son contenu."""
    words = [W("Première", 0.0, 0.4), W("astuce.", 0.4, 0.8), W("Relisez", 1.0, 1.4), W("vos", 1.4, 1.5), W("notes.", 1.5, 1.9),
             W("2e", 3.0, 3.2), W("astuce.", 3.2, 3.6), W("Expliquez", 3.8, 4.3), W("la", 4.3, 4.4), W("leçon.", 4.4, 4.8),
             W("3e", 6.0, 6.2), W("astuce.", 6.2, 6.6), W("Faites", 6.8, 7.1), W("des", 7.1, 7.2), W("pauses.", 7.2, 7.7)]
    sents = planner.sentences_from_transcript(1, {"words": words}, 10.0)
    assert [s["text"] for s in sents] == ["Première astuce. Relisez vos notes.", "2e astuce. Expliquez la leçon.", "3e astuce. Faites des pauses."]
    planner.mark_repetitions(sents)
    assert not any(s.get("reject") for s in sents)


def test_short_sentences_never_repetitions():
    words = [W("2e", 0.0, 0.2), W("astuce.", 0.2, 0.6), W("Bonjour", 3.0, 3.4), W("à", 3.4, 3.5), W("tous", 3.5, 3.8), W("ici.", 3.8, 4.0),
             W("3e", 6.0, 6.2), W("astuce.", 6.2, 6.6)]
    sents = planner.sentences_from_transcript(1, {"words": words}, 10.0)
    planner.mark_repetitions(sents)
    assert not any(s.get("reject") for s in sents)


def test_keep_everything_when_content_fits():
    """Régression (test final) : avec 14 s utiles pour 20 s demandées, aucune astuce ne doit disparaître."""
    words = [W("Voici", 0.0, 0.3), W("trois", 0.3, 0.6), W("astuces", 0.6, 1.0), W("utiles.", 1.0, 1.5),
             W("Première", 2.0, 2.4), W("astuce,", 2.4, 2.8), W("relisez", 2.9, 3.3), W("vos", 3.3, 3.4), W("notes.", 3.4, 3.9),
             W("Deuxième", 4.5, 4.9), W("astuce,", 4.9, 5.3), W("expliquez", 5.4, 5.9), W("la", 5.9, 6.0), W("leçon.", 6.0, 6.5),
             W("Troisième", 7.0, 7.5), W("astuce,", 7.5, 7.9), W("faites", 8.0, 8.3), W("des", 8.3, 8.4), W("pauses.", 8.4, 9.0)]
    media = [{"id": 1, "kind": "video", "category": "video", "original_name": "r.mp4", "probe": {"duration": 10.0, "audio": {}}}]
    sb = planner.build({"id": 1, "target_format": "tiktok"}, media, {1: {"duration": 10.0}}, {1: {"words": words}},
                       None, {"id": None, "name": "d"}, "TikTok de 20 secondes", {}, use_llm=True)
    text = " ".join(s["text"] for s in sb["scenes"])
    for w in ("Voici", "Première", "Deuxième", "Troisième"):
        assert w in text, w
    assert sb["llm"]["used"] is False and "aucun passage" in sb["llm"]["note"]
