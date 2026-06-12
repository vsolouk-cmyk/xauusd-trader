# Stage26B DB-First Family-Coverage Discovery

Research/shadow-only discovery branch.

Purpose:
- Continue discovery after Stage26A.
- Keep DB-first source of truth.
- Disable CSV fallback.
- Force family-coverage diagnostics and family-balanced exact replay.
- Avoid one family consuming all exact replay slots.

Run:

```bash
python3 -m app.stage26b_db_first_family_coverage_discovery
cat data/reports/stage26b_db_first_family_coverage_discovery/stage26b_db_first_family_coverage_discovery.md
```

No EA, paper, live, or order authorization.
