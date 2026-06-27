from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_stage101_detects_tracked_runtime_artifacts_and_applies_gitignore(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    root = tmp_path / 'repo'
    root.mkdir()
    subprocess.run(['git', 'init'], cwd=root, check=True, capture_output=True)
    (root / 'reports').mkdir()
    (root / 'reports' / 'x.json').write_text('{}', encoding='utf-8')
    (root / 'data' / 'external_frontiers').mkdir(parents=True)
    (root / 'data' / 'external_frontiers' / 'cot_positioning_normalized.csv').write_text('a,b\n1,2\n', encoding='utf-8')
    (root / 'app').mkdir()
    (root / 'app' / 'source.py').write_text('print(1)\n', encoding='utf-8')
    subprocess.run(['git', 'add', '-A'], cwd=root, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.email', 't@example.com'], cwd=root, check=True)
    subprocess.run(['git', 'config', 'user.name', 'T'], cwd=root, check=True)
    subprocess.run(['git', 'commit', '-m', 'init'], cwd=root, check=True, capture_output=True)

    pkg_root = Path(__file__).resolve().parents[1]
    cfg = pkg_root / 'configs' / 'stage101_repo_hygiene_cleanup_audit.json'
    out = root / 'reports' / 'stage101'
    script = pkg_root / 'app' / 'stage101_repo_hygiene_cleanup_audit.py'
    subprocess.run([sys.executable, str(script), '--root', str(root), '--config', str(cfg), '--out', str(out), '--apply-gitignore'], check=True)
    summary = json.loads((out / 'stage101_repo_hygiene_cleanup_audit_summary.json').read_text(encoding='utf-8'))
    assert summary['tracked_cleanup_candidate_count'] >= 2
    assert any('git rm -r --cached' in c for c in summary['suggested_untrack_commands'])
    assert 'BEGIN XAUUSD runtime/artifact ignores - Stage101' in (root / '.gitignore').read_text(encoding='utf-8')
    assert 'app/source.py' not in summary['tracked_cleanup_candidates_sample']


if __name__ == '__main__':
    test_stage101_detects_tracked_runtime_artifacts_and_applies_gitignore(Path('/tmp/stage101_test'))
    print('Stage101 tests passed')
