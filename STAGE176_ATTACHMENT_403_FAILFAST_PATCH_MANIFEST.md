# Stage176 Attachment 403 Fail-Fast Patch Manifest

Files:

- `app/stage176_central_bank_allocation_falsification.py`
- `configs/stage176_central_bank_allocation_falsification.json`
- `tests/test_stage176_central_bank_allocation_falsification.py`
- `docs/STAGE176_WGC_ATTACHMENT_403_FAILFAST.md`
- `STAGE176_ATTACHMENT_403_FAILFAST_PATCH_MANIFEST.md`

Research contract changes: none.

Operational changes:

- attachment HTTP 403 is permanent and gets no retry/backoff;
- curl fallback is skipped after attachment 403;
- two consecutive uncached attachment 403s disable further attachment network downloads for the current run;
- cached attachments and page/section extraction remain enabled.
