#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv
from pathlib import Path


def sep(path: Path) -> str:
    line = path.open('r', encoding='utf-8-sig', errors='replace').readline()
    return max(['\t', ',', ';', '|'], key=lambda x: line.count(x))


def read_rows(path: Path):
    if not path.exists():
        return [], []
    with path.open('r', encoding='utf-8-sig', errors='replace', newline='') as f:
        r=csv.DictReader(f, delimiter=sep(path))
        return list(r), list(r.fieldnames or [])


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--existing', default='')
    p.add_argument('--incoming', required=True)
    p.add_argument('--out', required=True)
    a=p.parse_args()
    incoming=Path(a.incoming)
    if not incoming.exists():
        raise SystemExit(f'incoming missing: {incoming}')
    old_rows, old_fields = read_rows(Path(a.existing)) if a.existing else ([], [])
    new_rows, new_fields = read_rows(incoming)
    fields=[]
    for x in old_fields + new_fields:
        if x not in fields: fields.append(x)
    if 'time_bucket_utc' not in fields:
        raise SystemExit('time_bucket_utc missing')
    by_time={}
    for row in old_rows + new_rows:
        k=str(row.get('time_bucket_utc') or '')
        if k: by_time[k]=row
    out=Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', encoding='utf-8', newline='') as f:
        w=csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for k in sorted(by_time): w.writerow(by_time[k])
    print({'existing_rows': len(old_rows), 'incoming_rows': len(new_rows), 'merged_rows': len(by_time), 'out': str(out)})
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
