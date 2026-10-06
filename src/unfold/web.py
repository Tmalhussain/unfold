"""The Unfold web app: a local library of videos, a form to start one, and live progress.

Runs on localhost only. POST requests must carry an ``X-Unfold`` header, which a
page on another site cannot add without a CORS preflight this server never grants.
"""

from __future__ import annotations

import json
import re
import shutil
import urllib.error
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import ask, jobs, keys, library
from .ingest import LEVELS, new_video
from .project import VIDEOS, all_videos, ffmpeg, final_video, slugify, video_dir
from .voice import default_voice, elevenlabs_voices, kokoro_voices, openai_voices, say_voices

STATIC = Path(__file__).parent / "static"
MEDIA = re.compile(r"final/[\w.-]+\.(mp4|srt)|frames/s\d\d/(\d\d|sheet)\.png|paper/paper\.pdf")
TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css",
    ".js": "text/javascript",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".mp4": "video/mp4",
    ".pdf": "application/pdf",
    ".srt": "text/plain; charset=utf-8",
    ".vtt": "text/vtt; charset=utf-8",
    ".json": "application/json",
}
MAX_UPLOAD = 100 * 1024 * 1024


class HTTPError(Exception):
    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status = status


def _video(name: str) -> Path:
    if not re.fullmatch(r"[\w.-]+", name):
        raise HTTPError(HTTPStatus.NOT_FOUND, "no such video")
    try:
        return video_dir(VIDEOS / name)
    except SystemExit:
        raise HTTPError(HTTPStatus.NOT_FOUND, f"no video named {name}") from None


def _poster(video: Path) -> Path:
    """A still from the middle of the video, cached next to it."""
    final = final_video(video)
    if not final:
        raise HTTPError(HTTPStatus.NOT_FOUND, "no final video yet")
    poster = video / "final" / "poster.jpg"
    if not poster.exists() or poster.stat().st_mtime < final.stat().st_mtime:
        marks = library.chapters(video)["chapters"]
        middle = marks[len(marks) // 2] if len(marks) > 1 else None
        at = max(0.0, middle["start"] - 0.6) if middle else 5.0
        still = "-frames:v 1 -vf scale=960:-2 -q:v 3".split()
        ffmpeg("-ss", f"{at:.2f}", "-i", str(final), *still, str(poster))
    return poster


def _cover(video: Path) -> Path:
    """The top of the paper's first page, shown while the video is being made."""
    pdf, cover = video / "paper" / "paper.pdf", video / "paper" / "cover.png"
    if not pdf.exists():
        raise HTTPError(HTTPStatus.NOT_FOUND, "no paper yet")
    if not cover.exists():
        import pymupdf

        with pymupdf.open(pdf) as doc:
            page = doc[0].rect
            top = pymupdf.Rect(page.x0, page.y0, page.x1, page.y0 + page.width * 9 / 16)
            doc[0].get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=top).save(cover)
    return cover


def _captions(video: Path) -> bytes:
    """The subtitles as WebVTT, which is SRT with a header and dots in the timestamps."""
    final = final_video(video)
    srt = final.with_suffix(".srt") if final else None
    if not srt or not srt.exists():
        raise HTTPError(HTTPStatus.NOT_FOUND, "no subtitles yet")
    return ("WEBVTT\n\n" + re.sub(r"(\d\d:\d\d:\d\d),(\d{3})", r"\1.\2", srt.read_text())).encode()


def _voices() -> dict:
    kokoro = [v for v in kokoro_voices() if v.startswith(("af_", "am_", "bf_", "bm_"))]
    return {
        "default": default_voice(),
        "kokoro": [f"kokoro:{v}" for v in kokoro],
        "say": [f"say:{v}" for v in say_voices()],
        "openai": [f"openai:{v}" for v in openai_voices()],
        "elevenlabs": [
            {"value": f"elevenlabs:{v['id']}", "name": v["name"]} for v in elevenlabs_voices()
        ],
    }


def _save_key(body: dict) -> dict:
    try:
        keys.save(str(body.get("provider", "")), str(body.get("key") or "")[:500])
    except ValueError as e:
        raise HTTPError(HTTPStatus.BAD_REQUEST, str(e)) from None
    return keys.status()


def _finished(name: str) -> Path:
    video = _video(name)
    if not final_video(video):
        raise HTTPError(HTTPStatus.CONFLICT, "Questions open once the video is finished.")
    return video


def _answer(video: Path, body: dict):
    question = str(body.get("question", "")).strip()
    if not question:
        raise HTTPError(HTTPStatus.BAD_REQUEST, "Type a question first.")
    if len(question) > 1000:
        raise HTTPError(HTTPStatus.BAD_REQUEST, "Keep questions under 1,000 characters.")
    try:
        at = max(0.0, float(body.get("at") or 0))
    except (TypeError, ValueError):
        at = 0.0
    history = [
        {"q": str(h.get("q", ""))[:1000], "a": str(h.get("a", ""))[:4000]}
        for h in body.get("history") or []
        if isinstance(h, dict)
    ]
    return ask.answer(video, question, at, history)


def _create(body: dict) -> dict:
    source = str(body.get("source", "")).strip()
    if not source:
        raise HTTPError(HTTPStatus.BAD_REQUEST, "Paste an arXiv link or ID, or choose a PDF.")
    level = body.get("level", "grad")
    if level not in LEVELS:
        raise HTTPError(HTTPStatus.BAD_REQUEST, f"Level must be one of {', '.join(LEVELS)}.")
    try:
        minutes = float(body.get("minutes", 5))
    except (TypeError, ValueError):
        raise HTTPError(HTTPStatus.BAD_REQUEST, "Length must be a number of minutes.") from None
    if not 1 <= minutes <= 20:
        raise HTTPError(HTTPStatus.BAD_REQUEST, "Length must be between 1 and 20 minutes.")
    try:
        video, _ = new_video(
            source, level, minutes, body.get("focus") or None, body.get("voice") or None
        )
    except SystemExit as e:
        raise HTTPError(HTTPStatus.BAD_REQUEST, str(e)) from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise HTTPError(HTTPStatus.BAD_GATEWAY, f"Could not download the paper: {e}") from None
    try:
        return {"name": video.name, "job": jobs.start(video)}
    except jobs.JobError as e:
        return {"name": video.name, "job": None, "warning": str(e)}


class Handler(BaseHTTPRequestHandler):
    server_version = "unfold"

    def log_message(self, *args):
        pass

    def do_GET(self):
        self._dispatch(self._get)

    def do_HEAD(self):
        self._dispatch(self._get)

    def do_POST(self):
        self._dispatch(self._post)

    def _dispatch(self, route):
        host = self.headers.get("Host", "").rsplit(":", 1)[0]
        try:
            if host not in ("localhost", "127.0.0.1"):
                raise HTTPError(HTTPStatus.FORBIDDEN, "unfold only answers on localhost")
            route(unquote(urlparse(self.path).path))
        except HTTPError as e:
            self._json({"error": str(e)}, e.status)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _get(self, path: str):
        if path == "/":
            return self._file(STATIC / "index.html")
        if m := re.fullmatch(r"/static/([\w.-]+)", path):
            return self._file(STATIC / m[1])
        if path == "/api/videos":
            videos = sorted((library.summary(v) for v in all_videos()), key=lambda v: -v["updated"])
            return self._json(videos)
        if m := re.fullmatch(r"/api/videos/([^/]+)", path):
            return self._json(library.detail(_video(m[1])))
        if m := re.fullmatch(r"/api/videos/([^/]+)/questions", path):
            return self._json(ask.suggestions(_video(m[1])))
        if path == "/api/voices":
            return self._json(_voices())
        if path == "/api/keys":
            return self._json(keys.status())
        if m := re.fullmatch(r"/media/([^/]+)/(.+)", path):
            video, rel = _video(m[1]), m[2]
            if rel == "poster.jpg":
                return self._file(_poster(video))
            if rel == "cover.png":
                return self._file(_cover(video))
            if rel == "captions.vtt":
                return self._bytes(_captions(video), TYPES[".vtt"])
            if MEDIA.fullmatch(rel):
                return self._file(video / rel)
        raise HTTPError(HTTPStatus.NOT_FOUND, "not found")

    def _post(self, path: str):
        if self.headers.get("X-Unfold") != "1":
            raise HTTPError(HTTPStatus.FORBIDDEN, "missing X-Unfold header")
        if path == "/api/papers":
            return self._json(self._upload())
        if path == "/api/videos":
            return self._json(_create(self._body()), HTTPStatus.CREATED)
        if path == "/api/keys":
            return self._json(_save_key(self._body()))
        if m := re.fullmatch(r"/api/videos/([^/]+)/questions", path):
            return self._json(ask.suggest(_finished(m[1])))
        if m := re.fullmatch(r"/api/videos/([^/]+)/ask", path):
            return self._stream(_answer(_finished(m[1]), self._body()))
        if m := re.fullmatch(r"/api/videos/([^/]+)/(start|stop)", path):
            try:
                action = jobs.start if m[2] == "start" else jobs.stop
                return self._json(action(_video(m[1])))
            except jobs.JobError as e:
                raise HTTPError(HTTPStatus.CONFLICT, str(e)) from None
        raise HTTPError(HTTPStatus.NOT_FOUND, "not found")

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            raise HTTPError(HTTPStatus.BAD_REQUEST, "the request body is not JSON") from None

    def _upload(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_UPLOAD:
            raise HTTPError(HTTPStatus.BAD_REQUEST, "Choose a PDF under 100 MB.")
        data = self.rfile.read(length)
        if not data.startswith(b"%PDF"):
            raise HTTPError(HTTPStatus.BAD_REQUEST, "That file is not a PDF.")
        stem = slugify(Path(unquote(self.headers.get("X-Filename", "paper"))).stem)
        dest = VIDEOS / ".uploads" / f"{stem}.pdf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return {"source": str(dest)}

    def _stream(self, events):
        """Send events as JSON lines while they are produced, so answers appear as they are written."""
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            for event in events:
                self.wfile.write(json.dumps(event).encode() + b"\n")
                self.wfile.flush()
        finally:
            events.close()  # stops Claude if the viewer cancels or leaves

    def _json(self, data, status: HTTPStatus = HTTPStatus.OK):
        self._bytes(json.dumps(data).encode(), TYPES[".json"], status, cache="no-store")

    def _bytes(
        self, data: bytes, kind: str, status: HTTPStatus = HTTPStatus.OK, cache: str = "no-cache"
    ):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _file(self, path: Path):
        """Serve a file, honoring a single byte range so video can seek (Safari insists on it)."""
        if not path.is_file():
            raise HTTPError(HTTPStatus.NOT_FOUND, "not found")
        size = path.stat().st_size
        start, end = 0, size - 1
        wanted = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        partial = bool(wanted and (wanted[1] or wanted[2]))
        if partial:
            if wanted[1]:
                start, end = int(wanted[1]), min(int(wanted[2] or end), end)
            else:
                start = max(0, size - int(wanted[2]))
            if start > end:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
        self.send_response(HTTPStatus.PARTIAL_CONTENT if partial else HTTPStatus.OK)
        self.send_header("Content-Type", TYPES.get(path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(1 << 16, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


def serve(port: int = 8765, open_browser: bool = True) -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is missing: brew install ffmpeg")
    VIDEOS.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    url = f"http://localhost:{port}"
    print(f"Unfold is running at {url}  (Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
