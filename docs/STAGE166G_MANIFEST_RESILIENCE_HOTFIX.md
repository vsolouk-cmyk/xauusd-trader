# Stage166G Manifest Resilience Hotfix

## Incident

A scheduled GitHub Actions run failed while loading `stage166g_persistent_manifest.json`:

`JSONDecodeError: Expecting value: line 1 column 1`

The workflow used shell redirection with `git show ... || true`. When the file did not exist on an older or partially initialized publication branch, the redirection still created a zero-byte file. The persistent-store process treated file existence as proof of valid JSON.

## Corrections

1. The persistent store now safely handles missing, empty, malformed, or non-object prior manifests.
2. A degraded prior manifest is diagnostic only; persistent points and fetch ledger remain authoritative.
3. The next manifest records `prior_manifest_read` status.
4. The workflow now writes into a temporary file and publishes it to the prior directory only when non-empty; JSON is validated before use.
5. Job timeout increases from 55 to 120 minutes so bounded sequential retries are not killed by the runner timeout.

## Invariants

- Failed GDELT ranges never overwrite previously valid points with zeroes.
- Invalid prior manifest never destroys the persistent point store.
- GDELT remains a guard/context input, not direct alpha.
- No order, demo, live, or threshold authorization is changed.
