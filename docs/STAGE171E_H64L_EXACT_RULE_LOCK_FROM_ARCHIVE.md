# Stage171E — H64L Exact Rule Lock From Archive

This is a read-only H64L rescue support stage.

It exists because Stage171B/171C/171D kept the H64L path alive but did not confirm the exact locked Stage64R/Stage66 rule. Stage171E narrows the work to archived H64L evidence only.

## What it does

- Searches archived Stage64/Stage66/H64L artifacts.
- Prioritizes `h64l_locked_rule_v2_stage66a3_exact_reconciled.json`, then `h64l_locked_rule_v1.json`.
- Extracts the four H64L conditions if they are present in archived evidence.
- Produces an evidence table, a locked-rule JSON, and a decision memo.

## What it does not do

- No threshold optimization.
- No broad scan.
- No new indicators.
- No MT5 signal.
- No demo/live authorization.

## Required policy

Daily Stage171D shadow logging continues in parallel. Even if the archived rule is confirmed, demo bridge is still blocked until a real shadow hit occurs and specialist approval is obtained.
