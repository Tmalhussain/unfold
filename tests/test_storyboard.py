import copy
from pathlib import Path

import pytest
import yaml

from unfold.storyboard import lint


def _video(tmp_path, sb):
    (tmp_path / "storyboard.yaml").write_text(yaml.safe_dump(sb))
    (tmp_path / "video.yaml").write_text("minutes: 0.2\n")
    return tmp_path


BASE = {
    "title": "t",
    "guiding_question": "q",
    "key_insight": "k",
    "symbols": {"x": "sky"},
    "scenes": [
        {
            "id": "s01",
            "title": "one",
            "beats": [
                {
                    "id": "b1",
                    "say": "Here is x.",
                    "show": "x appears",
                    "introduces": ["x"],
                    "transform": True,
                    "math": [{"tex": "x = 1", "illustration": True}],
                },
            ],
        }
    ],
}


def test_reference_storyboard_is_clean():
    ref = Path(__file__).parents[1] / "examples" / "reference"
    assert not [i for i in lint(ref) if i.level == "error"]


def test_lint_clean_minimal(tmp_path):
    assert not [i for i in lint(_video(tmp_path, BASE)) if i.level == "error"]


THIRTEEN_WORDS = "one two three four five six seven eight nine ten eleven twelve thirteen"


@pytest.mark.parametrize(
    "mutate,needle",
    [
        (lambda beat, sb: beat.update(say=r"Here is $x^2$."), "LaTeX"),
        (lambda beat, sb: beat.pop("introduces"), "before any beat"),
        (lambda beat, sb: beat.update(transform=False), "continuous transform"),
        (lambda beat, sb: beat.update(text=[THIRTEEN_WORDS]), "on-screen text"),
        (
            lambda beat, sb: beat["math"].extend([{"tex": "y", "illustration": True}] * 2),
            "equations on screen",
        ),
        (lambda beat, sb: beat.update(hard=True, pause=0.5), "1.5 s"),
        (lambda beat, sb: sb["symbols"].update(y="teal"), "pick one of"),
        (lambda beat, sb: beat["math"][0].update(derived=True), "exactly one of"),
    ],
)
def test_lint_catches(tmp_path, mutate, needle):
    sb = copy.deepcopy(BASE)
    mutate(sb["scenes"][0]["beats"][0], sb)
    msgs = [i.message for i in lint(_video(tmp_path, sb)) if i.level == "error"]
    assert any(needle in m for m in msgs), msgs
