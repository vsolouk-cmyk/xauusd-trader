# XAUUSD Stage 4D Exact Selected Replay

- Generated at UTC: `2026-06-05T11:59:49.124906+00:00`
- Decision: `stage4d_exact_selected_replay_pass`
- Reason: `Selected scenario passed exact trade-level replay checks.`

## Selected scenario

- scenario: `side=long|tp=24.0|sl=15.0`
- trades: `376`
- total net: `807.5899999999958`
- PF: `1.4049145888381354`
- median: `0.26000000000001366`
- max DD: `-106.52000000000135`
- ambiguous ratio: `0.0`

## Reference scenario

- scenario: `side=long|tp=None|sl=None`
- total net: `717.5999999999947`
- PF: `1.2800827446235494`
- max DD: `-232.36000000000058`

## Cost stress

| Cost x | Total net | PF | Median | Max DD |
|---:|---:|---:|---:|---:|
| 1.0 | 807.5900 | 1.405 | 0.2600 | -106.5200 |
| 2.0 | 675.9900 | 1.328 | -0.0900 | -120.5200 |
| 3.0 | 544.3900 | 1.256 | -0.4400 | -134.5200 |
| 4.0 | 412.7900 | 1.188 | -0.7900 | -149.6900 |

