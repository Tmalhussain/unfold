import json

import pytest
import yaml

from unfold import project, web

STORYBOARD = {
    "title": "A Tiny Video",
    "guiding_question": "Why?",
    "key_insight": "Because.",
    "scenes": [
        {"id": "s01", "title": "First", "beats": [{"id": "b1", "say": "One two three."}]},
        {"id": "s02", "title": "Second", "beats": [{"id": "b1", "say": "Four five six."}]},
    ],
}


@pytest.fixture
def videos(tmp_path, monkeypatch):
    monkeypatch.setattr(project, "VIDEOS", tmp_path)
    monkeypatch.setattr(web, "VIDEOS", tmp_path)
    video = tmp_path / "tiny"
    for sub in ("scenes", "checks", "final", "paper"):
        (video / sub).mkdir(parents=True)
    (video / "video.yaml").write_text(
        yaml.safe_dump({"level": "grad", "minutes": 1, "voice": "say:Samantha"})
    )
    (video / "storyboard.yaml").write_text(yaml.safe_dump(STORYBOARD))
    (video / "paper" / "paper.json").write_text(
        json.dumps({"title": "A Tiny Paper", "authors": ["A. Author"]})
    )
    (video / "scenes" / "s01.py").write_text("# scene")
    (video / "checks" / "review.json").write_text(json.dumps({"scores": {"clarity": 4}}))
    (video / "final" / "a-tiny-video.mp4").write_bytes(bytes(range(256)) * 4)
    (video / "final" / "chapters.json").write_text(
        json.dumps(
            {
                "duration": 6.0,
                "chapters": [{"start": 0, "title": "First"}, {"start": 3.0, "title": "Second"}],
            }
        )
    )
    for sid in ("s01", "s02"):
        (video / "checks" / f"{sid}.layout.json").write_text(
            json.dumps(
                {"defects": [], "beats": [{"id": "b1", "start": 0.2, "end": 2.8, "audio": 2.4}]}
            )
        )
    return video
