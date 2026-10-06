import shutil
import subprocess
import sys
import textwrap

import pytest

from unfold.render import CodeError, check_code, inputs_hash


GOOD = """
from unfold.style import *

class S01(UnfoldScene):
    scene_id = "s01"
    def construct(self):
        with self.beat("b1"):
            self.play(Write(M("x")), run_time=self.share(0.5))
"""


def _write(tmp_path, body):
    p = tmp_path / "s01.py"
    p.write_text(textwrap.dedent(body))
    return p


def test_code_check_accepts_house_style(tmp_path):
    assert check_code(_write(tmp_path, GOOD), "s01") == "S01"


@pytest.mark.parametrize(
    "bad",
    [
        "import os\n",
        "from subprocess import run\n",
        "x = open('/etc/passwd')\n",
        "y = (1).__class__\n",
        "z = getattr(M, 'x')\n",
        "import random\nr = random._os\n",
        "g = (i for i in ()).gi_frame.f_globals\n",
        "b = {}['__builtins__']\n",
        "import manim\nm = manim.utils\n",
        "c = capture(['id'])\n",
        "a = np.load('x.npy', allow_pickle=True)\n",
        "r = list(map(exec, ['print(1)']))\n",
        "s = __loader__\n",
        "match M:\n    case object(__class__=c):\n        pass\n",
    ],
)
def test_code_check_rejects_escapes(tmp_path, bad):
    with pytest.raises(CodeError):
        check_code(_write(tmp_path, GOOD + "\n" + bad), "s01")


def test_code_check_requires_matching_scene_id(tmp_path):
    with pytest.raises(CodeError):
        check_code(_write(tmp_path, GOOD), "s02")


PROBE = """
import subprocess, sys
from pathlib import Path
v, keys = Path(sys.argv[1]), Path(sys.argv[2])
for attempt in (
    lambda: (v / "CLAUDE.md").write_text("x"),
    lambda: (v / ".Claude").mkdir(),
    lambda: (keys.parent / "outside.txt").write_text("x"),
    lambda: keys.read_text(),
    lambda: subprocess.run(["/usr/bin/open", "-g", "-a", "TextEdit"], check=True),
):
    try:
        attempt()
        print("allowed")
    except Exception:
        print("blocked")
(v / "out.txt").write_text("ok")
"""


@pytest.mark.skipif(not shutil.which("sandbox-exec"), reason="macOS only")
def test_sandbox_keeps_renders_away_from_config_keys_and_other_apps(tmp_path, monkeypatch):
    from unfold import keys, render

    monkeypatch.setattr(keys, "FILE", tmp_path / "keys.json")
    keys.FILE.write_text("{}")
    video = tmp_path / "video"
    video.mkdir()
    cmd = [sys.executable, "-c", PROBE, str(video), str(keys.FILE)]
    out = subprocess.run(render._sandboxed(cmd, video, video), capture_output=True, text=True)
    assert out.stdout.split() == ["blocked"] * 5
    assert (video / "out.txt").read_text() == "ok"


def test_keyframes_cover_every_animation_and_beat_end():
    from unfold.render import keyframe_times

    report = {
        "beats": [{"id": "b1", "start": 0, "end": 5}, {"id": "b2", "start": 5, "end": 9}],
        "plays": [
            {"beat": "b1", "end": 1.0},
            {"beat": "b1", "end": 3.0},
            {"beat": "b2", "end": 7.0},
        ],
    }
    labels = [label for label, _ in keyframe_times(report)]
    assert labels == ["b1.1", "b1.2", "b1 end", "b2.1", "b2 end"]


def test_inputs_hash_tracks_code_shared_code_audio_and_fps(tmp_path):
    (tmp_path / "scenes").mkdir()
    (tmp_path / "audio").mkdir()
    (tmp_path / "scenes" / "s01.py").write_text("a")
    (tmp_path / "audio" / "s01_b1.wav").write_bytes(b"1")
    first = inputs_hash(tmp_path, "s01", 30)
    assert inputs_hash(tmp_path, "s01", 30) == first
    assert inputs_hash(tmp_path, "s01", 60) != first
    (tmp_path / "audio" / "s02_b1.wav").write_bytes(b"other scene")
    assert inputs_hash(tmp_path, "s01", 30) == first
    (tmp_path / "scenes" / "common.py").write_text("shared")
    second = inputs_hash(tmp_path, "s01", 30)
    assert second != first
    (tmp_path / "audio" / "s01_b1.wav").write_bytes(b"2")
    assert inputs_hash(tmp_path, "s01", 30) != second
