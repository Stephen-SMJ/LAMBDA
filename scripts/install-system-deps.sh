#!/usr/bin/env bash
set -euo pipefail

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is required to install system dependencies." >&2
  exit 1
fi

sudo apt-get update

# Minimal system packages for local PDF report generation.
# - texlive-xetex + texlive-lang-chinese provide xelatex, xeCJK, and ctex.
# - fonts-noto-cjk is used by both LaTeX and matplotlib Chinese charts.
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  texlive-latex-base \
  texlive-latex-recommended \
  texlive-fonts-recommended \
  texlive-xetex \
  texlive-lang-chinese \
  fonts-noto-cjk

echo "System dependencies installed."
echo "xelatex: $(command -v xelatex || true)"
echo "pdflatex: $(command -v pdflatex || true)"
