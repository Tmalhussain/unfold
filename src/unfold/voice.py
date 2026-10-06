"""Voice every beat and record how long each clip runs.

Voices are named ``backend:voice``:
  kokoro:af_heart         local neural voice, the default once installed
  kokoro:af_heart@1.1     ...with a speed factor
  say:Samantha@175        macOS built-in, with an optional words-per-minute rate
  openai:alloy            needs OPENAI_API_KEY
  elevenlabs:<voice_id>   needs ELEVENLABS_API_KEY
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from . import keys
from .project import ffmpeg, settings, ssl_context, storyboard

FALLBACK_VOICE = "say:Samantha@175"
KOKORO_VOICE = "kokoro:af_heart"
KOKORO_DIR = Path.home() / ".cache" / "unfold" / "kokoro"
KOKORO_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
KOKORO_FILES = ("kokoro-v1.0.onnx", "voices-v1.0.bin")
OPENAI_VOICES = tuple("alloy ash ballad coral echo fable nova onyx sage shimmer verse".split())
NOVELTY_VOICES = set(
    "Albert, Bad News, Bahh, Bells, Boing, Bubbles, Cellos, Good News, Jester, Junior, Organ, "
    "Superstar, Trinoids, Whisper, Wobble, Zarvox, Fred, Kathy, Ralph, Eddy, Flo, Grandma, "
    "Grandpa, Reed, Rocko, Sandy, Shelley".split(", ")
)

_kokoro = None
_elevenlabs_cache: tuple[float, str, list] = (0.0, "", [])


def kokoro_status() -> str:
    try:
        import kokoro_onnx  # noqa: F401
    except ImportError:
        return "package not installed"
    if any(not (KOKORO_DIR / f).exists() for f in KOKORO_FILES):
        return "model files not downloaded"
    return "ready"


def install_kokoro() -> None:
    """Download the Kokoro model (about 340 MB) into ~/.cache/unfold/kokoro."""
    KOKORO_DIR.mkdir(parents=True, exist_ok=True)
    for name in KOKORO_FILES:
        dest = KOKORO_DIR / name
        if dest.exists():
            print(f"have {name}")
            continue
        print(f"downloading {name} ...", flush=True)
        part = dest.with_suffix(".part")
        req = urllib.request.Request(f"{KOKORO_RELEASE}/{name}", headers={"User-Agent": "unfold"})
        with (
            urllib.request.urlopen(req, timeout=120, context=ssl_context()) as r,
            open(part, "wb") as f,
        ):
            shutil.copyfileobj(r, f, 1 << 20)
        part.rename(dest)


def default_voice() -> str:
    return KOKORO_VOICE if kokoro_status() == "ready" else FALLBACK_VOICE


def kokoro_voices() -> list[str]:
    if kokoro_status() != "ready":
        return []
    import numpy as np

    with np.load(KOKORO_DIR / "voices-v1.0.bin") as voices:
        return sorted(voices.files)


def say_voices() -> list[str]:
    """English macOS voices, minus the novelty ones."""
    if not shutil.which("say"):
        return []
    listing = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    names = []
    for line in listing.splitlines():
        m = re.match(r"^(.+?)\s+(en_[A-Z]{2})\b", line)
        if m and m.group(1).split(" (")[0] not in NOVELTY_VOICES:
            names.append(m.group(1))
    return names


def openai_voices() -> list[str]:
    return list(OPENAI_VOICES) if keys.get("openai") else []


def elevenlabs_voices() -> list[dict]:
    """The voices in your ElevenLabs account, as {id, name}; checked at most every ten minutes."""
    global _elevenlabs_cache
    key = keys.get("elevenlabs")
    if not key:
        return []
    fetched, cached_key, voices = _elevenlabs_cache
    if cached_key == key and time.time() - fetched < 600:
        return voices
    req = urllib.request.Request("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=10, context=ssl_context()) as r:
            voices = [
                {"id": v["voice_id"], "name": v["name"]} for v in json.load(r).get("voices", [])
            ]
    except (OSError, ValueError, KeyError):
        voices = []
    _elevenlabs_cache = (time.time(), key, voices)
    return voices


def duration(path: Path) -> float:
    cmd = "ffprobe -v error -show_entries format=duration -of csv=p=0".split()
    return float(
        subprocess.run([*cmd, str(path)], capture_output=True, text=True, check=True).stdout
    )


def _to_wav(src: Path, dst: Path) -> None:
    # Trim silence at both ends so a beat lasts exactly as long as the speech.
    trim = "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.05"
    both_ends = f"{trim},areverse,{trim},areverse"
    ffmpeg("-i", str(src), "-af", both_ends, "-ar", "48000", "-ac", "2", str(dst))


def _from_bytes(data: bytes, suffix: str, out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / f"raw{suffix}"
        raw.write_bytes(data)
        _to_wav(raw, out)


def _say(text: str, voice: str, out: Path) -> None:
    name, _, rate = voice.partition("@")
    with tempfile.TemporaryDirectory() as tmp:
        aiff = Path(tmp) / "raw.aiff"
        cmd = ["say", "-v", name or "Samantha", "-o", str(aiff)] + (["-r", rate] if rate else [])
        subprocess.run([*cmd, text], check=True)
        _to_wav(aiff, out)


def _kokoro_say(text: str, voice: str, out: Path) -> None:
    global _kokoro
    status = kokoro_status()
    if status != "ready":
        raise SystemExit(
            f"kokoro voice: {status}. Run `uv sync --extra kokoro` and `unfold voices --install kokoro`."
        )
    import soundfile
    from kokoro_onnx import Kokoro

    if _kokoro is None:
        _kokoro = Kokoro(*(str(KOKORO_DIR / f) for f in KOKORO_FILES))
    name, _, speed = voice.partition("@")
    samples, rate = _kokoro.create(
        text, voice=name or "af_heart", speed=float(speed or 1), lang="en-us"
    )
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.wav"
        soundfile.write(raw, samples, rate)
        _to_wav(raw, out)


def _post(url: str, headers: dict, body: dict) -> bytes:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    with urllib.request.urlopen(req, timeout=120, context=ssl_context()) as r:
        return r.read()


def _api_key(provider: str) -> str:
    key = keys.get(provider)
    if not key:
        raise SystemExit(
            f"no {keys.NAMES[provider]} key: run `unfold keys set {provider}` or add it in the web app"
        )
    return key


def _openai(text: str, voice: str, out: Path, style: str | None) -> None:
    body = {
        "model": "gpt-4o-mini-tts",
        "voice": voice or "alloy",
        "input": text,
        "response_format": "wav",
    }
    if style:
        body["instructions"] = style
    data = _post(
        "https://api.openai.com/v1/audio/speech",
        {"Authorization": f"Bearer {_api_key('openai')}"},
        body,
    )
    _from_bytes(data, ".wav", out)


def _elevenlabs(text: str, voice: str, out: Path) -> None:
    data = _post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
        {"xi-api-key": _api_key("elevenlabs")},
        {"text": text, "model_id": "eleven_multilingual_v2"},
    )
    _from_bytes(data, ".mp3", out)


def speak(text: str, voice: str, out: Path, style: str | None = None) -> None:
    backend, _, name = voice.partition(":")
    if backend == "say":
        _say(text, name, out)
    elif backend == "kokoro":
        _kokoro_say(text, name, out)
    elif backend == "openai":
        _openai(text, name, out, style)
    elif backend == "elevenlabs":
        _elevenlabs(text, name, out)
    else:
        raise SystemExit(
            f"unknown voice backend {backend!r} (use kokoro:, say:, openai:, or elevenlabs:)"
        )


def apply_pronunciations(text: str, table: dict) -> str:
    for word, spoken in (table or {}).items():
        text = re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", spoken, text)
    return text


def _beats(video: Path):
    """(scene id, beat id, spoken text, clip hash) for every beat, using the video's voice settings."""
    sb, cfg = storyboard(video), settings(video)
    voice = cfg.get("voice") or default_voice()
    style = cfg.get("voice_style")
    for scene in sb.get("scenes", []):
        for beat in scene.get("beats", []):
            text = apply_pronunciations(str(beat.get("say", "")).strip(), sb.get("pronounce"))
            digest = hashlib.sha1(f"{voice}|{style}|{text}".encode()).hexdigest()[:12]
            yield scene["id"], beat["id"], text, digest


def _timings(video: Path) -> dict:
    path = video / "audio" / "timings.json"
    return json.loads(path.read_text()) if path.exists() else {}


def voice_video(
    video: Path, scene: str | None = None, force: bool = False, voice: str | None = None
) -> dict:
    cfg = settings(video)
    if voice and voice != cfg.get("voice"):
        cfg["voice"] = voice
        import yaml

        (video / "video.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    voice = cfg.get("voice") or default_voice()
    audio = video / "audio"
    audio.mkdir(exist_ok=True)
    timings = _timings(video)
    beats = [b for b in _beats(video) if not scene or b[0] == scene]
    for sid in {b[0] for b in beats}:
        keep = {b[1] for b in beats if b[0] == sid}
        timings[sid] = {k: v for k, v in timings.get(sid, {}).items() if k in keep}

    voiced = cached = 0
    for sid, bid, text, digest in beats:
        out = audio / f"{sid}_{bid}.wav"
        old = timings[sid].get(bid)
        if not force and old and old.get("hash") == digest and out.exists():
            cached += 1
            continue
        speak(text, voice, out, cfg.get("voice_style"))
        timings[sid][bid] = {
            "file": f"audio/{out.name}",
            "duration": round(duration(out), 3),
            "hash": digest,
            "voice": voice,
        }
        voiced += 1
        (audio / "timings.json").write_text(json.dumps(timings, indent=2))
    (audio / "timings.json").write_text(json.dumps(timings, indent=2))
    return {"voiced": voiced, "cached": cached, "voice": voice}


def voiced_scenes(video: Path) -> set[str]:
    """Scenes whose every beat has a clip matching its current narration."""
    timings = _timings(video)
    scenes, stale = set(), set()
    for sid, bid, _, digest in _beats(video):
        scenes.add(sid)
        if timings.get(sid, {}).get(bid, {}).get("hash") != digest:
            stale.add(sid)
    return scenes - stale
