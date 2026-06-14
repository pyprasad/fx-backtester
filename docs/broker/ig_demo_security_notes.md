# IG DEMO Security Notes

- `.env.demo`, `.runtime/`, token caches, and captured DEMO ticks are gitignored.
- Do not put credentials in YAML, source code, CLI arguments, logs, reports, tests, or chat.
- Password, API key, CST, X-SECURITY-TOKEN, OAuth access token, and refresh token are sensitive.
- Config and session representations redact secrets and partially redact account identifiers.
- Optional token cache is disabled by default, DEMO-only, stored at
  `.runtime/ig_demo_session.json`, and written with user-only permissions.
- `IG_ENV=DEMO`, `IG_ACC_TYPE=DEMO`, `IG_ORDER_EXECUTION_ENABLED=false`, and
  `IG_DRY_RUN_ONLY=true` are mandatory.
- No live account support or order submission endpoint exists in FX-2I.

If a secret is printed, committed, or shared, revoke/rotate it immediately and purge it from
history. Demo credentials still require careful handling.
