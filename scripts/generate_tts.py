#!/usr/bin/env python3
"""GitHub Actions TTS 생성 스크립트."""
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
    print(f"\n== {date} ({len(sentences)} sentences, repeats={repeats}, rate={rate}) ==")
    if "voiceCombos" in data and data["voiceCombos"]:
        for combo in data["voiceCombos"]:
            await process_combo(date, combo, sentences, repeats, rate)
    else:
        voice_en = data.get("voiceEN", "en-US-AriaNeural")
        voice_ko = data.get("voiceKO", "ko-KR-SunHiNeural")
        await process_legacy(date, voice_en, voice_ko, sentences, repeats, rate)


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
            continue
    if TMP_DIR.exists():
        for f in TMP_DIR.glob("*.mp3"):
            try: f.unlink()
            except Exception: pass


if __name__ == "__main__":
    asyncio.run(main())
