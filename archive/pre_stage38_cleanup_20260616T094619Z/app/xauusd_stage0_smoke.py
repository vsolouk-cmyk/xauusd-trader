from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_step(label: str, cmd: list[str]) -> None:
    print(f"\n=== {label} ===")
    print(" ".join(cmd))
    result = subprocess.run(cmd, text=True)
    if result.returncode != 0:
        raise SystemExit(
            f"\nFAILED at step: {label}\n"
            f"Exit code: {result.returncode}\n"
            "Stop here. Do not run later stages until this step is fixed."
        )


def count_files(pattern: str) -> int:
    return len(list(Path(".").glob(pattern)))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Stage 0 smoke test: collect -> normalize -> quality, with fail-fast checks."
    )
    parser.add_argument("--interval", default="1min")
    parser.add_argument("--outputsize", type=int, default=100)
    args = parser.parse_args()

    before_raw = count_files("data/raw/*.json")
    before_norm = count_files("data/normalized/*.csv")
    before_reports = count_files("data/reports/*.json")

    run_step(
        "collect",
        [
            sys.executable,
            "-m",
            "app.xauusd_collect",
            "--interval",
            args.interval,
            "--outputsize",
            str(args.outputsize),
        ],
    )

    after_raw = count_files("data/raw/*.json")
    if after_raw <= before_raw:
        raise SystemExit(
            "\nFAILED after collect: no new raw JSON file was created in data/raw.\n"
            "Check TWELVEDATA_API_KEY, symbol access, internet/VPN, and Twelve Data response."
        )

    run_step("normalize", [sys.executable, "-m", "app.xauusd_normalize"])

    after_norm = count_files("data/normalized/*.csv")
    if after_norm <= before_norm:
        raise SystemExit("\nFAILED after normalize: no new CSV file was created in data/normalized.")

    run_step("data_quality", [sys.executable, "-m", "app.xauusd_data_quality"])

    after_reports = count_files("data/reports/*.json")
    if after_reports <= before_reports:
        raise SystemExit("\nFAILED after data_quality: no new report was created in data/reports.")

    print(
        json.dumps(
            {
                "ok": True,
                "message": "Stage 0 smoke test completed.",
                "new_raw_files": after_raw - before_raw,
                "new_normalized_files": after_norm - before_norm,
                "new_reports": after_reports - before_reports,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
