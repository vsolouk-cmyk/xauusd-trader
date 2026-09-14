# XAUUSD Article 2 Manuscript Package V1

This package adds an evidence-bound manuscript draft, claim–evidence matrix, preliminary bibliography, journal-fit decision, reviewer-risk register, deterministic manuscript-input generator, unit tests, generated tables/figure, and a manual GitHub QA workflow.

It requires the previously verified Article 2 evidence directory at:

`artifacts/article2/article2_evidence_v1/`

It does not rerun the evidence collector, alter Article 1 results, search for trading alpha, or permit any order execution.

## Install and run on macOS

Run every command from Terminal exactly as shown. The commands preserve both expanded Article 2 artifact folders.

```bash
cd /Users/vahid/Desktop/xauusd-trader

git status --short

test -f artifacts/article2/article2_evidence_v1/article2_decision.json

mkdir -p /Users/vahid/Desktop/xauusd-trader/_incoming_article2_manuscript_v1

unzip -q -o \
  "$HOME/Downloads/XAUUSD_ARTICLE2_MANUSCRIPT_PACKAGE_V1.zip" \
  -d /Users/vahid/Desktop/xauusd-trader/_incoming_article2_manuscript_v1

rsync -a \
  /Users/vahid/Desktop/xauusd-trader/_incoming_article2_manuscript_v1/ \
  /Users/vahid/Desktop/xauusd-trader/

python3 -m py_compile \
  tools/article_publication/build_article2_manuscript_inputs.py \
  tests/test_article2_manuscript_inputs.py

python3 -m unittest -v tests/test_article2_manuscript_inputs.py

python3 tools/article_publication/build_article2_manuscript_inputs.py --root .

(
  cd artifacts/article2
  shasum -a 256 -c XAUUSD_ARTICLE2_MANUSCRIPT_INPUTS_V1.zip.sha256
)

unzip -t \
  artifacts/article2/XAUUSD_ARTICLE2_MANUSCRIPT_INPUTS_V1.zip

python3 - <<'PY'
import json
from pathlib import Path
p = Path("artifacts/article2/article2_manuscript_v1/article2_results_snapshot.json")
d = json.loads(p.read_text())
assert d["source_decision"] == "ARTICLE2_EVIDENCE_SUFFICIENT"
assert d["benchmark"]["fault_count"] == 12
assert d["verification"]["tests_total"] == 44
assert d["verification"]["scoped_line_coverage_rate"] >= 0.80
print("ARTICLE2_MANUSCRIPT_INPUTS_READY")
PY

git status --short
```

After all commands pass, remove only the temporary incoming directory. The retained `artifacts/article2/article2_manuscript_v1/` directory is not removed.

```bash
cd /Users/vahid/Desktop/xauusd-trader

rm -rf /Users/vahid/Desktop/xauusd-trader/_incoming_article2_manuscript_v1

git status --short
```

## Commit and push

Review the diff before committing:

```bash
cd /Users/vahid/Desktop/xauusd-trader

git diff -- \
  tools/article_publication/build_article2_manuscript_inputs.py \
  tests/test_article2_manuscript_inputs.py \
  docs/article2/manuscript \
  artifacts/article2/article2_manuscript_v1 \
  .github/workflows/xauusd_article2_manuscript_qa.yml

git status --short

git add -A

git commit -m "Add evidence-bound Article 2 manuscript inputs"

git pull --rebase origin main

git push origin main
```

Then open GitHub and run:

**Actions → XAUUSD Article 2 Manuscript QA → Run workflow → Run workflow**

## Expected local decision

The generator prints `ARTICLE2_MANUSCRIPT_INPUTS_READY`. A missing or non-passing evidence decision fails closed with `BLOCK_ARTICLE2_MANUSCRIPT_INPUTS`.
