# Stage68F Robust Policy Shadow Selector

Stage68F locks the Stage68E robustness-selected candidate policy as a no-order forward-shadow selector:

- policy: `D3_FIRST_EXCLUDE_D1`
- priority: `d3_h60 > h64l_v2 > d4_backup`
- reference-only: `d1_backup`

It reads the latest macro row, evaluates all rule conditions, selects the first active allowed rule by policy priority, and writes a local ledger row. It does not authorize orders, paper orders, broker connections, EA promotion, paper-live, live, threshold tuning, or readiness promotion.

Expected use after daily refresh:

1. Run Stage67D6.
2. Run Stage67E.
3. Run Stage66J3.
4. Run Stage68F.

If Stage68F reports an active policy signal, the output is for manual review only. A later no-broker ticket package would still be required before any subsequent governance discussion.
