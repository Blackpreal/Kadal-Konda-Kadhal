"""Kadal Konda Kadhal - Short maker (Gemini app images + Gemini TTS + FFmpeg).

    python tools/short.py prompts shorts/<name>          # PROMPTS.md for the Gemini app
    python tools/short.py tts     shorts/<name>          # audio/<id>.wav via Gemini TTS
    python tools/short.py build   shorts/<name>          # out/short.mp4 (1080x1920)
    python tools/short.py build   shorts/<name> --placeholder   # preview before images exist

Everything for one Short lives in its folder: shots.json, images/, audio/, out/.
Needs: Python 3.9+, ffmpeg + ffprobe on PATH, GEMINI_API_KEY (env or .env) for tts.
"""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "tools" / "fonts"
TTS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
W, H, FPS = 1080, 1920, 30
ZOOM = 0.12  # how far zoom/pan moves over one shot


# ---------- shared ----------

def load(short_dir):
    path = short_dir / "shots.json"
    if not path.exists():
        sys.exit(f"shots.json illa: {path}")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    ids = [s["id"] for s in cfg["shots"]]
    if len(ids) != len(set(ids)):
        sys.exit("shots.json-la duplicate id irukku")
    return cfg


def audio_path(short_dir, shot):
    if shot.get("audio"):
        return short_dir / shot["audio"]
    return short_dir / "audio" / f"{shot['id']}.wav"


def image_path(short_dir, shot):
    return short_dir / shot.get("image", f"images/{shot['id']}.png")


def need(tool):
    if not shutil.which(tool):
        sys.exit(f"{tool} PATH-la illa. Windows: winget install Gyan.FFmpeg")


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"ffmpeg fail:\n{' '.join(map(str, cmd))}\n{r.stderr[-2000:]}")
    return r.stdout


def duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(path)])
    return float(out.strip())


# ---------- prompts ----------

def cmd_prompts(short_dir, cfg, args):
    chars = cfg.get("characters", {})
    style = cfg.get("image_style", "").strip()
    lines = [f"# Gemini app image prompts - {cfg.get('title', short_dir.name)}", "",
             "Each prompt: open a NEW Gemini chat, attach the listed character sheets,",
             f"paste the prompt, save the result into `{short_dir.name}/images/` with the given name.", ""]
    for s in cfg["shots"]:
        if not s.get("image_prompt"):
            continue
        img = image_path(short_dir, s).relative_to(short_dir).as_posix()
        lines.append(f"## {s['id']} -> `{img}`")
        refs = [chars[c] for c in s.get("characters", []) if c in chars]
        missing = [c for c in s.get("characters", []) if c not in chars]
        lines.append("Attach: " + (", ".join(f"`{r}`" for r in refs) or "nothing"))
        if missing:
            lines.append(f"(characters map-la illa: {', '.join(missing)})")
        prompt = " ".join(p for p in [style, s["image_prompt"].strip(),
                                      "Vertical 9:16 frame. No text, no watermark."] if p)
        lines += ["", "```text", prompt, "```", ""]
    out = short_dir / "PROMPTS.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"ok -> {out}")


# ---------- tts ----------

def api_key():
    key = os.environ.get("GEMINI_API_KEY")
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            if k.strip() == "GEMINI_API_KEY":
                key = v.strip().strip('"').strip("'")
    if not key:
        sys.exit("GEMINI_API_KEY illa. Repo root-la .env file-la GEMINI_API_KEY=... podunga")
    return key


def tts_request(key, model, text, voice, style):
    item = {"type": "text", "text": text}
    if style:
        item["annotations"] = [{"type": "speech_metadata", "style": style}]
    body = {
        "model": model,
        "input": [{"type": "user_input", "content": [item]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voice}]},
    }
    req = urllib.request.Request(TTS_URL, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    for wait in (10, 30, 60, None):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")
            found = re.search(r'"message":\s*"([^"]+)"', msg)
            msg = found.group(1) if found else msg[:500]
            if e.code in (429, 500, 503) and wait:
                print(f"  {e.code}, {wait}s wait panren...")
                time.sleep(wait)
                continue
            sys.exit(f"Gemini TTS error {e.code}: {msg}")
    audio = [c for st in data.get("steps", []) if st.get("type") == "model_output"
             for c in st.get("content", []) if c.get("type") == "audio"]
    if not audio:
        sys.exit(f"Response-la audio illa: {json.dumps(data)[:500]}")
    return base64.b64decode(audio[-1]["data"])


def cmd_tts(short_dir, cfg, args):
    key = api_key()
    model = cfg.get("tts_model", "gemini-3.8-flash-tts")
    voices = cfg.get("voices", {})
    base_style = cfg.get("voice_style", "")
    for s in cfg["shots"]:
        if not s.get("text") or (args.only and s["id"] not in args.only):
            continue
        out = audio_path(short_dir, s)
        if out.exists() and not args.force:
            print(f"{s['id']}: irukku, skip")
            continue
        speaker = s.get("speaker", "narrator")
        if speaker not in voices:
            sys.exit(f"{s['id']}: voices-la '{speaker}' illa")
        style = ", ".join(p for p in [base_style, s.get("style", "")] if p)
        print(f"{s['id']}: {speaker} ({voices[speaker]}) ...")
        wav = tts_request(key, model, s["text"], voices[speaker], style)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(wav)
    print("tts done")


# ---------- build ----------

def motion_filter(motion, frames):
    t = f"on/{max(frames - 1, 1)}"
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    z, x, y = {
        "zoom_in":   (f"1+{ZOOM}*{t}", cx, cy),
        "zoom_out":  (f"{1 + ZOOM}-{ZOOM}*{t}", cx, cy),
        "pan_left":  (f"{1 + ZOOM}", f"(iw-iw/zoom)*(1-{t})", cy),
        "pan_right": (f"{1 + ZOOM}", f"(iw-iw/zoom)*{t}", cy),
        "pan_up":    (f"{1 + ZOOM}", cx, f"(ih-ih/zoom)*(1-{t})"),
        "pan_down":  (f"{1 + ZOOM}", cx, f"(ih-ih/zoom)*{t}"),
        "static":    ("1", "0", "0"),
    }[motion]
    # 2x upscale first so zoompan's integer crop steps don't jitter
    return (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={FPS},"
            f"setsar=1,format=yuv420p")


def chunks(text, max_len=34, min_len=14):
    """Split a line into subtitle-sized pieces, preferring breaks after punctuation."""
    out, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > max_len:
            out.append(cur)
            cur = ""
        cur = f"{cur} {word}".strip()
        if len(cur) >= min_len and re.search(r"[.!?,;:…]$", cur):
            out.append(cur)
            cur = ""
    if cur:
        if out and len(cur) < min_len and len(out[-1]) + 1 + len(cur) <= max_len:
            out[-1] = f"{out[-1]} {cur}"
        else:
            out.append(cur)
    return out


def ass_time(sec):
    cs = int(round(sec * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def write_ass(path, events, cfg):
    sub = cfg.get("subtitles", {})
    size, margin = sub.get("size", 66), sub.get("margin_bottom", 430)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans Tamil,{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,5,2,2,90,90,{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    body = []
    for start, end, text in events:
        text = text.replace("\\", "").replace("{", "(").replace("}", ")")
        body.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{text}")
    path.write_text(head + "\n".join(body) + "\n", encoding="utf-8-sig")


def cmd_build(short_dir, cfg, args):
    need("ffmpeg")
    need("ffprobe")
    out_dir = short_dir / "out"
    seg_dir = out_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    pause = cfg.get("pause", 0.35)

    # 1. timing from the voice files
    plan, missing = [], []
    for s in cfg["shots"]:
        img, aud = image_path(short_dir, s), audio_path(short_dir, s)
        if not img.exists() and not args.placeholder:
            missing.append(str(img.relative_to(short_dir)))
        if s.get("text") and not aud.exists():
            missing.append(str(aud.relative_to(short_dir)))
        speech = duration(aud) if s.get("text") and aud.exists() else 0.0
        dur = max(speech + s.get("pause", pause), s.get("duration", 0), 1.5)
        frames = round(dur * FPS)
        plan.append((s, img, aud, speech, frames))
    if missing:
        sys.exit("Ivanga innum illa:\n  " + "\n  ".join(missing)
                 + "\n(images illama preview-ku --placeholder podunga)")

    # 2. one silent video segment per shot
    concat, events, voice_parts, t = [], [], [], 0.0
    for i, (s, img, aud, speech, frames) in enumerate(plan):
        seg = seg_dir / f"{i:02d}_{s['id']}.mp4"
        dur = frames / FPS
        if img.exists():
            src = ["-i", str(img)]
            vf = motion_filter(s.get("motion", "zoom_in"), frames)
        else:
            src = ["-f", "lavfi", "-i", f"color=c=0x14213d:s={W}x{H}:r={FPS}:d={dur}"]
            font = os.path.relpath(FONTS / "NotoSansTamil-Bold.ttf", seg_dir).replace("\\", "/")
            vf = (f"drawtext=fontfile='{font}'"
                  f":text='{s['id']}':fontsize=160:fontcolor=white@0.5:x=(w-tw)/2:y=(h-th)/2,"
                  f"setsar=1,format=yuv420p")
        run(["ffmpeg", "-y", "-v", "error", *src, "-vf", vf, "-frames:v", str(frames),
             "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
             "-pix_fmt", "yuv420p", "-an", str(seg)], cwd=seg_dir)
        concat.append(f"file '{seg.name}'")
        voice_parts.append((aud if s.get("text") else None, dur))
        if s.get("text") and speech:
            pieces = chunks(s["text"])
            total = sum(len(p) for p in pieces)
            at = t
            for p in pieces:
                step = speech * len(p) / total
                events.append((at, at + step, p))
                at += step
        t += dur
        print(f"  {s['id']}: {dur:.2f}s")
    (seg_dir / "list.txt").write_text("\n".join(concat) + "\n", encoding="utf-8")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "list.txt",
         "-c", "copy", str(out_dir / "video.mp4")], cwd=seg_dir)

    # 3. voice track: each shot's audio padded to its shot length
    inputs, filt = [], []
    for k, (aud, dur) in enumerate(voice_parts):
        if aud:
            inputs += ["-i", str(aud)]
        else:
            inputs += ["-f", "lavfi", "-t", f"{dur}", "-i", "anullsrc=r=48000:cl=stereo"]
        filt.append(f"[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                    f"apad=whole_dur={dur},atrim=0:{dur},asetpts=N/SR/TB[a{k}]")
    n = len(voice_parts)
    filt.append("".join(f"[a{k}]" for k in range(n)) + f"concat=n={n}:v=0:a=1[out]")
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filt),
         "-map", "[out]", "-c:a", "pcm_s16le", str(out_dir / "voice.wav")])

    # 4. subtitles + music + final mux
    write_ass(out_dir / "subs.ass", events, cfg)
    fonts_rel = os.path.relpath(FONTS, out_dir).replace("\\", "/")
    total = t
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", "video.mp4", "-i", "voice.wav"]
    afilt = "[1:a]anull[voice]"
    amap = "[voice]"
    music = cfg.get("music")
    if music:
        mpath = (short_dir / music) if (short_dir / music).exists() else (ROOT / music)
        if not mpath.exists():
            sys.exit(f"music file illa: {music}")
        cmd += ["-stream_loop", "-1", "-i", str(mpath)]
        vol = cfg.get("music_volume", 0.12)
        fade = max(total - 1.5, 0)
        afilt += (f";[2:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={vol},"
                  f"atrim=0:{total},afade=t=out:st={fade}:d=1.5[m];"
                  f"[voice][m]amix=inputs=2:duration=first:normalize=0[mix]")
        amap = "[mix]"
    # YouTube plays at about -14 LUFS; match it so the voice isn't quiet next to other Shorts
    afilt += f";{amap}loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]"
    amap = "[aout]"
    vfilt = f"[0:v]ass='subs.ass':fontsdir='{fonts_rel}':shaping=complex[vid]"
    final = cfg.get("output", "short.mp4")
    cmd += ["-filter_complex", f"{vfilt};{afilt}", "-map", "[vid]", "-map", amap,
            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-t", f"{total}", "-movflags", "+faststart", final]
    run(cmd, cwd=out_dir)
    print(f"ok -> {out_dir / final}  ({total:.1f}s)")
    if total > 60:
        print("warning: 60s-ku mela. Shorts 3 min varai allow, aana 60s kulla vachaa nalladhu.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["prompts", "tts", "build"])
    ap.add_argument("short", help="short folder, e.g. shorts/ep01-s1")
    ap.add_argument("--force", action="store_true", help="tts: redo existing audio")
    ap.add_argument("--only", nargs="*", help="tts: only these shot ids")
    ap.add_argument("--placeholder", action="store_true", help="build: dark cards for missing images")
    args = ap.parse_args()
    short_dir = Path(args.short).resolve()
    cfg = load(short_dir)
    {"prompts": cmd_prompts, "tts": cmd_tts, "build": cmd_build}[args.step](short_dir, cfg, args)


if __name__ == "__main__":
    main()
