#!/usr/bin/env python3
"""Validate AMarkets MT5 tab-separated OHLC exports without modifying them."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

EXPECTED = ["<DATE>", "<TIME>", "<OPEN>", "<HIGH>", "<LOW>", "<CLOSE>", "<TICKVOL>", "<SPREAD>", "<VOL>"]


@dataclass
class Result:
    path: str
    pass_: bool
    rows: int
    first: str | None
    last: str | None
    duplicate_timestamps: int
    non_monotonic_timestamps: int
    invalid_ohlc: int
    negative_volume: int
    header: list[str]
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "pass": self.pass_,
            "rows": self.rows,
            "first": self.first,
            "last": self.last,
            "duplicate_timestamps": self.duplicate_timestamps,
            "non_monotonic_timestamps": self.non_monotonic_timestamps,
            "invalid_ohlc": self.invalid_ohlc,
            "negative_volume": self.negative_volume,
            "header": self.header,
            "error": self.error,
        }


def parse_timestamp(date_text: str, time_text: str) -> datetime:
    value = f"{date_text.strip()} {time_text.strip()}"
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError(f"unsupported timestamp: {value!r}")


def validate(path: Path) -> Result:
    rows = 0
    first: datetime | None = None
    last: datetime | None = None
    duplicates = 0
    non_monotonic = 0
    invalid_ohlc = 0
    negative_volume = 0
    previous: datetime | None = None
    header: list[str] = []

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter="\t")
            header = next(reader)
            if header != EXPECTED:
                raise ValueError(f"unexpected header: {header!r}")

            for line_number, row in enumerate(reader, start=2):
                if not row or all(not item.strip() for item in row):
                    continue
                if len(row) != len(EXPECTED):
                    raise ValueError(f"line {line_number}: expected 9 columns, got {len(row)}")
                ts = parse_timestamp(row[0], row[1])
                open_, high, low, close = map(float, row[2:6])
                tickvol = int(float(row[6]))
                spread = int(float(row[7]))
                realvol = int(float(row[8]))

                if high < max(open_, low, close) or low > min(open_, high, close):
                    invalid_ohlc += 1
                if tickvol < 0 or spread < 0 or realvol < 0:
                    negative_volume += 1
                if previous is not None:
                    if ts == previous:
                        duplicates += 1
                    elif ts < previous:
                        non_monotonic += 1
                if first is None:
                    first = ts
                previous = ts
                last = ts
                rows += 1
    except Exception as exc:  # noqa: BLE001 - CLI should report exact parse failure
        return Result(str(path), False, rows, first.isoformat() if first else None, last.isoformat() if last else None,
                      duplicates, non_monotonic, invalid_ohlc, negative_volume, header, f"{type(exc).__name__}: {exc}")

    passed = rows > 0 and duplicates == 0 and non_monotonic == 0 and invalid_ohlc == 0 and negative_volume == 0
    return Result(str(path), passed, rows, first.isoformat() if first else None, last.isoformat() if last else None,
                  duplicates, non_monotonic, invalid_ohlc, negative_volume, header)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = [validate(path.expanduser().resolve()) for path in args.paths]
    payload = {"program": "VALIDATE_AMARKETS_MT5_EXPORT_V1", "pass": all(r.pass_ for r in results),
               "results": [r.as_dict() for r in results]}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for result in results:
            print(json.dumps(result.as_dict(), indent=2))
    return 0 if payload["pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
