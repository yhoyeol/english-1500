"""English Reading 전용 TTS. EN만, 원속/-15% 두 종류, 반복 없음."""
import json, asyncio
from pathlib import Path
import edge_tts

ROOT = Path(__file__).resolve().parent.parent
AUDIO = ROOT / "reading" / "audio"

async def say(text, out, voice, rate):
    if out.exists() and out.stat().st_size > 0:
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    await edge_tts.Communicate(text, voice, rate=rate).save(str(out))
    print("made", out.relative_to(ROOT))

async def main():
    for jf in sorted(AUDIO.glob("*.json")):
        meta = json.loads(jf.read_text(encoding="utf-8"))
        eid = jf.stem
        voice = meta.get("voiceEN", "en-US-AriaNeural")
        d = AUDIO / eid
        sents = meta["sentences"]
        for i, s in enumerate(sents, 1):
            await say(s["en"], d / f"{i:02d}.mp3", voice, "+0%")
            await say(s["en"], d / f"{i:02d}_slow.mp3", voice, "-15%")
        full = " ".join(s["en"] for s in sents)
        await say(full, d / "full.mp3", voice, "+0%")
        await say(full, d / "full_slow.mp3", voice, "-15%")

asyncio.run(main())
