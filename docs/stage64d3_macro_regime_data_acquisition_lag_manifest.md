# Stage64D3 - Macro-Regime Data Acquisition and Lag Manifest

## Purpose

Stage64D3 converts the Stage64D2 remediation plan into an operational acquisition and lag manifest for the Daily/Weekly Macro-Regime Gold Thesis. It is intentionally a governance and data-contract stage, not a validation stage.

## What it produces

- Source acquisition manifest for all required macro-regime features.
- Lag manifest specifying `available_after_utc`, release lag, session-close lag, and no-lookahead join rules.
- Expected file schema manifest for raw source files.
- Operator checklist for manual/source acquisition.
- Summary and report under `reports/stage64d3_macro_regime_data_acquisition_lag_manifest/`.

## What it does not do

- It does not fetch or download data.
- It does not mutate trading state.
- It does not run historical validation.
- It does not generate any trading signal.
- It does not authorize paper-order, paper-live, live, EA promotion, or broker connection.

## Required sequence after this stage

1. Acquire source files according to the manifest.
2. Place files under `data/macro_regime/raw/` with exact target filenames.
3. Run Stage64D4 import preflight after files are present.
4. Rerun Stage64D for the selected feature scope.
5. Only if Stage64D passes, consider a predeclared validation stage.

## Key policy

No reduced-scope validation is allowed implicitly. If ETF or central-bank demand data cannot be acquired, exclusion must be documented and approved before any reduced-scope validation is built.
