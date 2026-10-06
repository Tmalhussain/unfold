import json
import stat

import pytest

from unfold import keys, voice

ANTHROPIC = "sk-ant-test-0000-abcd"


@pytest.fixture(autouse=True)
def keyfile(tmp_path, monkeypatch):
    monkeypatch.setattr(keys, "FILE", tmp_path / "config" / "keys.json")
    for var in keys.PROVIDERS.values():
        monkeypatch.delenv(var, raising=False)
    return keys.FILE


def test_saved_keys_are_private_and_only_their_ends_are_shown(keyfile):
    keys.save("anthropic", ANTHROPIC)
    assert stat.S_IMODE(keyfile.stat().st_mode) == 0o600
    assert keys.get("anthropic") == ANTHROPIC
    assert keys.status()["anthropic"] == {"set": True, "source": "saved", "ends": "abcd"}
    assert ANTHROPIC not in json.dumps(keys.status())


def test_environment_wins_and_saved_keys_reach_subprocesses(monkeypatch):
    keys.save("openai", "sk-saved")
    assert keys.env()["OPENAI_API_KEY"] == "sk-saved"
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
    assert keys.get("openai") == "sk-from-env"
    assert keys.status()["openai"]["source"] == "environment"


def test_removing_and_rejecting_keys():
    keys.save("elevenlabs", "anything")
    keys.save("elevenlabs", "")
    assert keys.get("elevenlabs") is None
    with pytest.raises(ValueError, match="Anthropic"):
        keys.save("anthropic", "not-a-key")
    with pytest.raises(ValueError, match="Unknown provider"):
        keys.save("someone", "x")


def test_paid_voices_use_saved_keys():
    with pytest.raises(SystemExit, match="unfold keys set openai"):
        voice._api_key("openai")
    keys.save("openai", "sk-voice")
    assert voice._api_key("openai") == "sk-voice"
    assert "alloy" in voice.openai_voices()
