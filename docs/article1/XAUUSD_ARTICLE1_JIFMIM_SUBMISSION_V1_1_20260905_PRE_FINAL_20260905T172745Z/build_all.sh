#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
python3 build_figures.py

for doc in manuscript manuscript_anonymized supplementary_material title_page cover_letter; do
  latexmk -C "$doc.tex" >/dev/null 2>&1 || true
  latexmk -pdf -interaction=nonstopmode -halt-on-error "$doc.tex"
done

python3 validate_package.py
