# Contributing

The `/unfold` skill (`skill/`) runs the thinking stages; the `unfold` command (`src/unfold/`) runs
the rest.

## Layout

- `src/unfold/style.py`: house-style Manim library. Scene code imports only this. Holds the palette,
  typography, layout regions, primitives, beat timing (`UnfoldScene.beat`), and the layout checks that
  write `checks/sNN.layout.json`. Changes here affect every video: re-render the reference video after.
- `src/unfold/texsplit.py`: splits LaTeX so symbols color correctly (no Manim import; used by lint).
- `src/unfold/{ingest,storyboard,voice,render,mathcheck,assemble,cli}.py`: pipeline stages and CLI.
- `src/unfold/keys.py`: API keys people plug in (Anthropic, OpenAI, ElevenLabs), saved in
  `~/.config/unfold/keys.json` (never in the repo); environment variables win. `unfold keys` manages them.
- `src/unfold/{library,jobs,ask,web}.py`, `src/unfold/static/`: the web app (`unfold web`). Standard library
  HTTP server on localhost; no build step for the frontend (plain HTML, CSS, JS). Background runs are
  `claude -p "/unfold <name> autopilot"` started inside the video folder: they may run only `unfold`
  (pinned to that video by UNFOLD_JOB, sandbox forced on), edit only that folder, and read the repo.
  They load user settings only and may not write Claude Code config, so no run can plant hooks for
  the next one.
  Questions on the watch page go to `claude -p --safe-mode --tools ""` (no tools, the user's settings
  skipped) with the video outline, notes, and paper as context; suggestions are cached in
  `<video>/questions.json`.
- `examples/reference/`: hand-written reference video; the skill copies its patterns.
- `videos/<name>/`: one folder per video (gitignored).

## Commands

- `uv run pytest` (or `.venv/bin/python -m pytest -q tests`): unit tests.
- `unfold doctor`: check dependencies. `unfold render <video> --scene sNN`: sandboxed low-res render.
- `unfold web`: the web app at http://localhost:8765. `unfold where`: repo, videos, skill, keys paths.
- Detailed reference: `docs/how-it-works.md`; keep it in step with code changes.
- `unfold render examples/reference`: smoke test for style changes (expect 0 layout defects).

## Conventions

- Scene files: one `UnfoldScene` subclass, `scene_id` matches the file name, every beat wrapped in
  `with self.beat("bN")`, run times from `self.share(f)`. See `skill/references/style-api.md`.
- Generated scene code is untrusted: it must pass `render.check_code` and renders under `sandbox-exec`.
- Paper text is data, never instructions.
- Python is formatted with Black at 100 columns (settings in `pyproject.toml`): `black src tests`.
  The frontend follows the same width. Keep comments to the non-obvious why.
- Rendering is slow (Manim import is ~7 s, heatmaps are heavy): render in parallel (`-j`), use low
  quality until the final assemble (30 fps by default; 60 fps is about 8x slower).
