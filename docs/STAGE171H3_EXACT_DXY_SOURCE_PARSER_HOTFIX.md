# Stage171H3 — Exact DXY Source Parser Hotfix

- Parses normal Stooq CSV, auto-delimited CSV, and headerless YYYYMMDD Stooq exports.
- Detects HTML, access-denied, rate-limit, and empty responses explicitly.
- Treats FRED `DTWEXBGS` as a broad trade-weighted dollar proxy, not the exact DXY input.
- Keeps shadow fail-closed until a valid current DXY/ICE USDX-compatible series exists.
- Does not change the H64L rule, thresholds, or order permissions.
