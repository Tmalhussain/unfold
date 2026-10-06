"""API keys people plug in: Anthropic to make videos and answer questions, OpenAI and ElevenLabs
for narration voices.

Keys are saved outside the repo, in ~/.config/unfold/keys.json, readable only by you, so they can
never end up in a commit. A key set in the environment wins over a saved one.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

PROVIDERS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
}
NAMES = {"anthropic": "Anthropic", "openai": "OpenAI", "elevenlabs": "ElevenLabs"}
PREFIXES = {"anthropic": "sk-ant-", "openai": "sk-"}
FILE = Path(os.environ.get("UNFOLD_KEYS", Path.home() / ".config" / "unfold" / "keys.json"))


def _saved() -> dict:
    try:
        return json.loads(FILE.read_text())
    except (OSError, ValueError):
        return {}


def get(provider: str) -> str | None:
    return os.environ.get(PROVIDERS[provider]) or _saved().get(provider)


def save(provider: str, key: str | None) -> None:
    """Save a key, or remove the saved one when ``key`` is empty."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}. Use one of: {', '.join(PROVIDERS)}.")
    key = (key or "").strip()
    if key and not key.startswith(PREFIXES.get(provider, "")):
        raise ValueError(
            f"That does not look like an {NAMES[provider]} key: it should start with {PREFIXES[provider]}"
        )
    keys = _saved()
    if key:
        keys[provider] = key
    else:
        keys.pop(provider, None)
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.touch(mode=0o600, exist_ok=True)
    FILE.chmod(0o600)
    FILE.write_text(json.dumps(keys, indent=2))


def status() -> dict:
    """Which keys are set and where from, showing only the last four characters."""
    saved = _saved()
    found = {}
    for provider, var in PROVIDERS.items():
        key = os.environ.get(var) or saved.get(provider)
        source = "environment" if os.environ.get(var) else "saved" if key else None
        found[provider] = {"set": bool(key), "source": source, "ends": key[-4:] if key else None}
    return found


def env() -> dict:
    """This process's environment plus every saved key, for the programs that need them."""
    merged = dict(os.environ)
    for provider, var in PROVIDERS.items():
        if not merged.get(var) and (key := _saved().get(provider)):
            merged[var] = key
    return merged
