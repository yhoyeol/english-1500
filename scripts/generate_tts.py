#!/usr/bin/env python3
"""
GitHub Actions에서 실행되는 TTS 생성 스크립트.
Repo의 *_audio.json 을 모두 스캔하여, 빠진 mp3 파일을 edge-tts로 생성한다.

생성 규칙:
- 각 sentence 마다 영어 1회 + 짧은 갭 + 한국어 1회 = 1쌍 (~3~4초)
- repeats(기본 5)만큼 반복 → 한 문장당 ~30초 mp3
- audio/{date}/{idx:02d}.mp3 로 저장 (idx: 1~5)
- 이미 존재하면 스킵 (재생성 안 함)
"""
import asyncio
import json
import os
import sys
from pathlib import Path

import edge_tts
from pydub import AudioSegment

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = REPO_ROOT / "audio"
TMP_DIR = Path("/tmp/tts_temp")

SHORT_GAP_MS = 280   # 영어와 한국어 사이
PAIR_GAP_MS = 600    # 쌍과 쌍 사이


async def synth(text, voice, rate, out_path):
    """단일 문장을 mp3로 합성."""
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(str(out_path))


async def make_sentence_mp3(sent, voice_en, voice_ko, repeats, rate, out_path):
    """한 문장의 영-한 N쌍 mp3를 생성."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    en_path = TMP_DIR / "en.mp3"
    ko_path = TMP_DIR / "ko.mp3"

    await synth(sent["en"], voice_en, rate, en_path)
    await synth(sent["ko"], voice_ko, rate, ko_path)

    en_clip = AudioSegment.from_mp3(str(en_path))
    ko_clip = AudioSegment.from_mp3(str(ko_path))
    silence_short = AudioSegment.silent(duration=SHORT_GAP_MS)
    silence_pair = AudioSegment.silent(duration=PAIR_GAP_MS)

    final = AudioSegment.silent(duration=200)  # 짧은 리딩 패드
    for r in range(repeats):
        final += en_clip + silence_short + ko_clip
        if r < repeats - 1:
            final += silence_pair

    final.export(str(out_path), format="mp3", bitrate="64k",
                 tags={"title": sent["en"][:40], "artist": "Daily English"})


async def process_one(json_path):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    date = data["date"]
    voice_en = data.get("voiceEN", "en-US-AriaNeural")
    voice_ko = data.get("voiceKO", "ko-KR-SunHiNeural")
    rate = data.get("rate", "-5%")
    repeats = int(data.get("repeats", 5))
    sentences = data["sentences"]

    out_dir = AUDIO_DIR / date
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n== Processing {date} ({len(sentences)} sentences) ==")
    print(f"   voices: EN={voice_en}, KO={voice_ko}, rate={rate}, repeats={repeats}")

    for i, sent in enumerate(sentences, 1):
        out_path = out_dir / f"{i:02d}.mp3"
        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"   [{i}/{len(sentences)}] skip (exists): {out_path.name}")
            continue
        await make_sentence_mp3(sent, voice_en, voice_ko, repeats, rate, out_path)
        size_kb = round(out_path.stat().st_size / 1024)
        print(f"   [{i}/{len(sentences)}] generated: {out_path.name} ({size_kb} KB)")


async def main():
    json_files = sorted(REPO_ROOT.glob("*_audio.json"))
    print(f"Found {len(json_files)} audio metadata files")
    if not json_files:
        print("Nothing to do.")
        return

    for j in json_files:
        try:
            await process_one(j)
        except Exception as e:
            print(f"ERROR processing {j.name}: {e}", file=sys.stderr)
            # 한 파일 실패해도 다른 파일은 계속 처리
            continue

    # tmp 정리
    if TMP_DIR.exists():
        for f in TMP_DIR.glob("*.mp3"):
            try:
                f.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
