import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from unfold import jobs, library, project, web
from unfold.assemble import _cues


def test_scenes_and_stages(videos):
    scenes = library.scenes(videos)
    assert [s["state"] for s in scenes] == ["coded", "planned"]
    stages = {s["key"]: s["done"] for s in library.stages(videos)}
    assert stages["paper"] and stages["storyboard"] and stages["video"]
    assert not stages["voice"] and not stages["scenes"]


def test_summary_and_transcript(videos):
    info = library.summary(videos)
    assert info["title"] == "A Tiny Video" and info["paper_title"] == "A Tiny Paper"
    assert info["duration"] == 6.0 and info["stage"] == "concepts"
    assert library.transcript(videos) == [
        {"start": 0.2, "end": 2.8, "text": "One two three."},
        {"start": 3.2, "end": 5.8, "text": "Four five six."},
    ]


def test_short_last_cue_joins_the_one_before():
    text = "Almost nothing does. The answer barely moves. So was that layer doing nothing at all?"
    cues = list(_cues(text, 0, 6))
    assert len(cues) == 1 and cues[0][1] == pytest.approx(6)


def test_job_state_and_activity_come_from_the_log(videos):
    log = videos / "logs" / "claude.jsonl"
    log.parent.mkdir()
    events = [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Starting."}]}},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Bash", "input": {"command": "unfold lint tiny"}}
                ]
            },
        },
        {
            "type": "assistant",
            "parent_tool_use_id": "x",
            "message": {"content": [{"type": "text", "text": "subagent chatter"}]},
        },
        {"type": "result", "subtype": "success", "is_error": False, "result": "Done."},
    ]
    log.write_text("".join(json.dumps(e, separators=(",", ":")) + "\n" for e in events))
    (videos / "job.json").write_text(
        json.dumps({"pid": 999999, "started": 1.0, "finished": None, "log_offset": 0})
    )
    assert jobs.status(videos)["state"] == "done"
    assert jobs.activity(videos) == [
        {"kind": "note", "text": "Starting."},
        {"kind": "step", "text": "unfold lint tiny"},
    ]


@pytest.fixture
def server(videos):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()


def request(port, method, path, headers=None, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port)
    conn.request(method, path, body=body, headers={"Host": f"localhost:{port}", **(headers or {})})
    response = conn.getresponse()
    return response.status, dict(response.getheaders()), response.read()


def test_api_lists_and_describes_videos(server):
    status, _, body = request(server, "GET", "/api/videos")
    assert status == 200 and [v["name"] for v in json.loads(body)] == ["tiny"]
    status, _, body = request(server, "GET", "/api/videos/tiny")
    assert status == 200 and json.loads(body)["review"]["scores"]["clarity"] == 4


def test_video_files_support_byte_ranges(server):
    status, headers, body = request(
        server, "GET", "/media/tiny/final/a-tiny-video.mp4", {"Range": "bytes=10-19"}
    )
    assert status == 206 and body == bytes(range(10, 20))
    assert headers["Content-Range"] == "bytes 10-19/1024"


def test_server_refuses_what_it_should(server):
    assert request(server, "GET", "/api/videos", {"Host": "evil.example"})[0] == 403
    assert request(server, "POST", "/api/videos", body=b"{}")[0] == 403
    assert request(server, "GET", "/media/tiny/video.yaml")[0] == 404
    assert request(server, "GET", "/media/tiny/../tiny/video.yaml")[0] == 404
    status, _, body = request(server, "POST", "/api/videos", {"X-Unfold": "1"}, b'{"source": ""}')
    assert status == 400 and "arXiv" in json.loads(body)["error"]


def test_background_runs_stay_on_their_video(videos, monkeypatch):
    from unfold import cli

    other = videos.parent / "other"
    other.mkdir()
    (other / "video.yaml").write_text("level: grad\n")
    monkeypatch.setenv("UNFOLD_JOB", str(videos))
    assert project.video_dir("tiny") == videos.resolve()
    with pytest.raises(SystemExit, match="only work on tiny"):
        project.video_dir("other")
    with pytest.raises(SystemExit, match="no-sandbox"):
        cli.main(["render", "tiny", "--no-sandbox"])
    with pytest.raises(SystemExit, match="already has its video"):
        cli.main(["new", "1512.03385"])


def test_background_runs_may_only_edit_their_own_folder(videos):
    rules = jobs.allowed_tools(videos)
    assert f"Edit(/{videos}/**)" in rules and f"Write(/{videos}/**)" in rules
    assert not {"Edit", "Write", "Read", "Bash"} & set(rules)


def test_only_web_links_reach_the_page(videos):
    paper = videos / "paper" / "paper.json"
    paper.write_text(json.dumps({"title": "A Tiny Paper", "url": "javascript:alert(1)"}))
    assert library.paper_info(videos)["url"] is None
    paper.write_text(
        json.dumps({"title": "A Tiny Paper", "url": "https://arxiv.org/abs/2307.15771"})
    )
    assert library.paper_info(videos)["url"] == "https://arxiv.org/abs/2307.15771"


def test_background_run_command(videos, monkeypatch):
    started = {}

    class FakeProcess:
        pid = 999999

        def __init__(self, cmd, **options):
            started.update(cmd=cmd, **options)

        def wait(self):
            return 0

    monkeypatch.setattr(jobs.shutil, "which", lambda name: "/usr/local/bin/claude")
    monkeypatch.setattr(jobs.subprocess, "Popen", FakeProcess)
    jobs.start(videos)
    cmd = started["cmd"]
    assert cmd[:3] == ["claude", "-p", "/unfold tiny autopilot"]
    assert cmd.count("--allowedTools") == 1 and cmd[
        cmd.index("--allowedTools") + 1 :
    ] == jobs.allowed_tools(videos)
    assert {"--output-format", "stream-json", "--verbose"} <= set(cmd)
    assert started["cwd"] == videos and started["env"]["UNFOLD_JOB"] == str(videos)
