#!/bin/sh
# Set up Unfold on this Mac: Python environment, the `unfold` command, and the /unfold skill.
set -e
cd "$(dirname "$0")"
REPO="$(pwd)"

for tool in uv ffmpeg latex dvisvgm; do
  command -v "$tool" >/dev/null || { echo "missing $tool: brew install uv ffmpeg texlive dvisvgm"; exit 1; }
done

uv sync --extra kokoro

mkdir -p "$HOME/.local/bin" "$HOME/.claude/skills"
ln -sfn "$REPO/.venv/bin/unfold" "$HOME/.local/bin/unfold"
[ -e "$HOME/.claude/skills/unfold" ] || ln -sfn "$REPO/skill" "$HOME/.claude/skills/unfold"

"$REPO/.venv/bin/unfold" doctor || true
echo
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo "Add ~/.local/bin to your PATH so the unfold command is found:"
     echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc" ;;
esac
command -v claude >/dev/null || echo "Install Claude Code to make videos: https://claude.com/claude-code"
echo "Sign in to Claude Code, or add your own key: unfold keys set anthropic"
echo "For a natural free voice: unfold voices --install kokoro"
echo "Then start the web app: unfold web"
