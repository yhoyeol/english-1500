#!/usr/bin/env python3
"""
GitHub Actions에서 실행되는 TTS 생성 스크립트.
*_audio.json 을 모두 스캔하여 빠진 mp3 파일을 edge-tts로 생성한다.

audio_script.json 형식:
- 단일 음성: voiceEN, voiceKO (구버전 호환)
- 다중 음성 조합: voiceCombos 배열, 각 항목 {id, voiceEN, voiceKO, label}

생성 규칙:
- 각 sentence 마다 영어 1회 + 짧은 갭 + 한국어 1회 = 1쌍
- repeats(기본 5)만큼 반복 → 한 문장당 ~30초 mp3
- 단일 음성: audio/{date}/{idx:02d}.mp3
- 다중 음성: audio/{date}/{combo_id}/{idx:02d}.mp3
- 이미 존재하면 스킵
"""
import asyncio
import json
import sys
from pathlib import Path

import edge_tts
from pydub import AudioSegment

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = REPO_ROOT / "audio"
TMP_DIR = Path("/tmp/tts_temp")

SHORT_GAP_MS = 280
PAIR_GAP_MS = 600


async def synth(text, voice, rate, out_path):
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(str(out_path))


async def make_sentence_mp3(sent, voice_en, voice_ko, repeats, rate, out_path):
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    en_path = TMP_DIR / "en.mp3"
    ko_path = TMP_DIR / "ko.mp3"

    await synth(sent["en"], voice_en, rate, en_path)
    await synth(sent["ko"], voice_ko, rate, ko_path)

    en_clip = AudioSegment.from_mp3(str(en_path))
    ko_clip = AudioSegment.from_mp3(str(ko_path))
    silence_short = AudioSegment.silent(duration=SHORT_GAP_MS)
    silence_pair = AudioSegment.silent(duration=PAIR_GAP_MS)

    final = AudioSegment.silent(duration=200)
    for r in range(repeats):
        final += en_clip + silence_short + ko_clip
        if r < repeats - 1:
            final += silence_pair

    final.export(str(out_path), format="mp3", bitrate="64k",
                 tags={"title": sent["en"][:40], "artist": "Daily English"})


async def process_combo(date, combo, sentences, repeats, rate):
    combo_id = combo["id"]
    voice_en = combo["voiceEN"]
    voice_ko = combo["voiceKO"]
    out_dir = AUDIO_DIR / date / combo_id
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"  [{combo_id}] {combo.get('label', '')}: EN={voice_en}, KO={voice_ko}")
    for i, sent in enumerate(sentences, 1):
        out_path = out_dir / f"{i:02d}.mp3"
        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"     [{i}/{len(sentences)}] skip")
            continue
        await make_sentence_mp3(sent, voice_en, voice_ko, repeats, rate, out_path)
        size_kb = round(out_path.stat().st_size / 1024)
        print(f"     [{i}/{len(sentences)}] {out_path.relative_to(REPO_ROOT)} ({size_kb} KB)")


async def process_legacy(date, voice_en, voice_ko, sentences, repeats, rate):
    """구버전 호환 (단일 voice)."""
    out_dir = AUDIO_DIR / date
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"  (legacy single voice): EN={voice_en}, KO={voice_ko}")
    for i, sent in enumerate(sentences, 1):
        out_path = out_dir / f"{i:02d}.mp3"
        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"     [{i}/{len(sentences)}] skip")
            continue
        await make_sentence_mp3(sent, voice_en, voice_ko, repeats, rate, out_path)
        size_kb = round(out_path.stat().st_size / 1024)
        print(f"     [{i}/{len(sentences)}] {out_path.relative_to(REPO_ROOT)} ({size_kb} KB)")


async def process_one(json_path):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    date = data["date"]
    rate = data.get("rate", "-5%")
    repeats = int(data.get("repeats", 5))
    sentences = data["sentences"]

    prin