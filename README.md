# Unfold

Turn a research paper into a narrated, animated explainer video in the style of 3Blue1Brown.

Give Unfold an arXiv link or a PDF. Claude reads the paper, plans a story around one question, writes a
storyboard, records the narration, and writes animation code for every scene. A separate reviewer
critiques each rendered scene until it passes, and the result is an MP4 with chapters and subtitles.
A local web app lets you start videos, watch them being made, and watch the results with a synced
transcript and a question bar that answers questions about the part of the video you are in.

How it works, in depth: [docs/how-it-works.md](docs/how-it-works.md).

## Requirements

- macOS (the narration, render sandbox, and fonts use macOS features)
- [uv](https://docs.astral.sh/uv/), ffmpeg, a TeX Live install, and dvisvgm:
  `brew install uv ffmpeg texlive dvisvgm`
- [Claude Code](https://claude.com/claude-code), signed in, or your own Anthropic API key

## Install

```bash
git clone https://github.com/Tmalhussain/unfold.git
cd unfold
./setup.sh
```

`setup.sh` installs the Python environment, puts the `unfold` command in `~/.local/bin`, links the
`/unfold` skill into `~/.claude/skills`, and runs `unfold doctor` to check everything. For a natural,
free, offline narration voice, then run `unfold voices --install kokoro` (downloads about 340 MB).

## Keys

Unfold runs on your own accounts. Add keys on the web app's **Keys** page or with `unfold keys set`:

| Key | What it is for |
| --- | --- |
| Anthropic | Making videos and answering questions. Not needed if you are signed in to Claude Code. |
| OpenAI | OpenAI narration voices (optional) |
| ElevenLabs | The voices in your ElevenLabs account (optional) |

Keys are saved in `~/.config/unfold/keys.json`, readable only by you and outside this repo, so they
never end up in a commit. A key set as an environment variable (`ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`, `ELEVENLABS_API_KEY`) is used instead of a saved one.

## Use

**In the browser.** Run `unfold web`. Paste an arXiv link or drop a PDF, say who it is for and how long
it should be, and press **Make video**. The page shows each step as Claude works through it in the
background, with every scene's latest frame as it renders. Finished videos play with chapters, a
transcript you can click to jump around, and a question bar: ask anything while you watch, or pick a
question suggested for the scene you are in.

**In Claude Code.** Open Claude Code in this folder and run:

```
/unfold 1412.6980 level=grad minutes=5
```

Claude shows you the plan before anything is rendered, then voices, codes, renders, critiques, and
assembles the video in `videos/<name>/final/`. `/unfold <video name>` picks a stopped video back up.

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
| `unfold keys [set\|remove <provider>]` | Show, save, or remove API keys |
| `unfold voices [--preview V] [--install kokoro]` | List voices, preview one, or install the local voice |
| `unfold where` | Print where the repo, videos, skill, and saved keys are |
| `unfold doctor` | Check that everything is installed |

Tests: `uv run pytest`.

## License

[MIT](LICENSE)
