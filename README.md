# Unfold

Turn a research paper into a narrated, animated explainer video in the style of 3Blue1Brown.

Give Unfold an arXiv link or a PDF. Claude reads the paper, plans a story around one question, writes a
storyboard, records the narration, and writes animation code for every scene. A separate reviewer
critiques each rendered scene until it passes, and the result is an MP4 with chapters and subtitles.
A local web app lets you start videos, watch them being made, and watch the results with chapters
and a synced transcript.

## Requirements

- macOS (the narration, render sandbox, and fonts use macOS features)
- [uv](https://docs.astral.sh/uv/), ffmpeg, a TeX Live install, and dvisvgm:
  `brew install uv ffmpeg texlive dvisvgm`
- [Claude Code](https://claude.com/claude-code), signed in

## Install

```bash
git clone https://github.com/Tmalhussain/unfold.git
cd unfold
./setup.sh
```

`setup.sh` installs the Python environment, puts the `unfold` command in `~/.local/bin`, links the
`/unfold` skill into `~/.claude/skills`, and runs `unfold doctor` to check everything. For a natural,
free, offline narration voice, then run `unfold voices --install kokoro` (downloads about 340 MB).

## Use

**In the browser.** Run `unfold web`. Paste an arXiv link or drop a PDF, say who it is for and how long
it should be, and press **Make video**. The page shows each step as Claude works through it in the
background, with every scene's latest frame as it renders. Finished videos play with chapters and a
transcript you can click to jump around.

**In Claude Code.** Open Claude Code in this folder and run:

```
/unfold 1412.6980 level=grad minutes=5
```

Claude shows you the plan before anything is rendered, then voices, codes, renders, critiques, and
assembles the video in `videos/<name>/final/`. `/unfold <video name>` picks a stopped video back up.

OpenAI and ElevenLabs voices read their keys from `OPENAI_API_KEY` and `ELEVENLABS_API_KEY`.

## Commands

| Command | What it does |
| --- | --- |
| `unfold web [--port 8765]` | The web app |
| `unfold new <arxiv id or pdf>` | Create `videos/<name>/` and ingest the paper |
| `unfold lint <video>` | Check `storyboard.yaml` against the visual grammar rules |
| `unfold voice <video>` | Record one clip per beat |
| `unfold render <video> [--scene s03] [-j 4]` | Sandboxed render, layout report, contact sheet |
| `unfold mathcheck <video>` | Check on-screen math against the paper and with SymPy |
| `unfold assemble <video> [--fps 60]` | Full-quality renders joined into the MP4, subtitles, chapters |
| `unfold status <video>` | Where each scene stands |
| `unfold list` / `unfold open <video>` | List videos / open a finished one |
| `unfold clean <video> [--all]` | Delete render caches (keeps plan, audio, code, final video) |
| `unfold voices [--preview V] [--install kokoro]` | List voices, preview one, or install the local voice |
| `unfold where` | Print where the repo, videos, and skill are |
| `unfold doctor` | Check that everything is installed |

Tests: `uv run pytest`.

## License

[MIT](LICENSE)
