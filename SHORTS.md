# Shorts pipeline (Gemini only, ₹0)

Images = Gemini app (free daily limit, manual). Voice = Gemini TTS API (free tier, auto).
Video = `tools/short.py` (FFmpeg, auto). Upload = manual for now.

## One-time setup (laptop)
1. FFmpeg: `winget install Gyan.FFmpeg` (new terminal-la `ffmpeg -version` check pannunga).
2. Python 3.9+ (extra packages venaam).
3. API key: aistudio.google.com → Get API key. Repo root-la `.env` file:
   `GEMINI_API_KEY=xxxx`  (git-la pogaadhu, `.gitignore`-la irukku. Chat-la paste pannaadheenga.)
4. Character sheets (once): Gemini app-la generate panni `characters/maaran_sheet.png`,
   `characters/nila_sheet.png`-ah save pannunga.

## Oru Short (~30-45 min)
1. `shorts/_template`-ah copy panni rename pannunga, e.g. `shorts/ep01-s1`.
2. `shots.json`-la lines, speaker, image_prompt edit pannunga (Claude ezhudhum).
3. `python tools/short.py prompts shorts/ep01-s1` → `PROMPTS.md`.
   Ovvoru prompt-um: puthu Gemini chat → sheets attach → prompt paste → `images/01.png` mari save.
4. `python tools/short.py tts shorts/ep01-s1` → `audio/*.wav`. Oru line pidikkalana:
   `python tools/short.py tts shorts/ep01-s1 --only 03 --force`
5. `python tools/short.py build shorts/ep01-s1` → `out/short.mp4`.
   Images varaadhukku munnaadi timing paakka: `... build shorts/ep01-s1 --placeholder`.

## shots.json fields
- `voices`: speaker → Gemini voice. AI Studio-la kettu pick pannunga. Ippo irukkura defaults:
  Sulafat (warm), Algenib (gravelly), Leda (youthful).
- `voice_style` + shot `style`: English-la tone (e.g. "soft, longing").
- `motion`: zoom_in, zoom_out, pan_left, pan_right, pan_up, pan_down, static.
- `music`: BGM file path (optional, loops, fades out). `music_volume` default 0.12.
- `pause`: oru shot-oda voice mudinja apram evlo second gap vidanum (default 0.35).
- Optional per shot: `audio` (unga own recording path), `duration` (minimum seconds).

## Notes
- Subtitles: Noto Sans Tamil (OFL, `tools/fonts/`). Tamil shaping-ku `ass` filter `shaping=complex` use pannrom.
- Audio -14 LUFS-ku normalize aagudhu (YouTube level).
- Free tier-la Google unga TTS input-ah product improve panna use pannalaam.
