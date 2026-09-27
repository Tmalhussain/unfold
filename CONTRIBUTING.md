# Contributing

The `/unfold` skill (`skill/`) runs the thinking stages; the `unfold` command (`src/unfold/`) runs
the rest.

## Layout

- `src/unfold/style.py`: house-style Manim library. Scene code imports only this. Holds the palette,
  typography, layout regions, primitives, beat timing (`UnfoldScene.beat`), and the layout checks that
  write `checks/sNN.layout.json`. Changes here affect every video: re-render the reference video after.
- `src/unfold/texsplit.py`: splits LaTeX so symbols color correctly (no Manim import; used by lint).
- `src/unfold/{ingest,storyboard,voice,render,mathcheck,assemble,cli}.py`: pipeline stages and CLI.
- `examples/reference/`: hand-written reference video; the skill copies its patterns.
- `videos/<name>/`: one folder per video (gitignored).

## Commands

- `uv run pytest` (or `.venv/bin/python -m pytest -q tests`): unit tests.
- `unfold doctor`: check dependencies. `unfold render <video> --scene sNN`: sandboxed low-res render.
- `unfold where`: repo, videos, and skill paths.
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
