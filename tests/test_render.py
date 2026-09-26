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
    ],
)
def test_code_check_rejects_escapes(tmp_path, bad):
    with pytest.raises(CodeError):
        check_code(_write(tmp_path, GOOD + "\n" + bad), "s01")


def test_code_check_requires_matching_scene_id(tmp_path):
    with pytest.raises(CodeError):
        check_code(_write(tmp_path, GOOD), "s02")


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
