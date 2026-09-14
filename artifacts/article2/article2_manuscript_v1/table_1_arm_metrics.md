| Architecture | Detection | Unsafe acceptance | False blocking | Median (us) | Overhead |
| --- | --- | --- | --- | --- | --- |
| Naive latest-state | 0.00% | 100.00% | 0.00% | 8.863 | 1.00x |
| Point-in-time, fail-open | 50.00% | 100.00% | 0.00% | 51.317 | 5.79x |
| Point-in-time + provenance, fail-closed | 100.00% | 0.00% | 0.00% | 385.028 | 43.44x |
