# Release Checklist

## Offline validation

Use the project's virtual environment and run the self-contained suite:

```bash
.venv/bin/python -m pytest -q tests
.venv/bin/python -m compileall -q agents keys scripts
```

Tests that use key management must point vault, salt, metadata, and audit paths at a temporary directory. Do not test rotation against `keys/vault/` or run the bootstrap/key-creation scripts as a release check.

## Safety review

1. Inspect the tool registry and confirm filesystem operations stay within the intended workspace.
2. Verify `sh.run`/`py.exec` dangerous-command protections, command timeouts, output truncation, and approval policy after any change.
3. Confirm the default local model route works without provider keys and that cloud providers are explicitly opted in.
4. Review key derivation/encryption changes, audit log handling, `.gitignore`, infrastructure scripts, and any Tailscale/SSH/deploy changes.
5. Run `git diff --check`, inspect staged files, and confirm no vault, token, log, prompt, or workstation data is staged.

Do not launch deployment scripts, synchronize a vault, rotate real keys, or enable remote access during ordinary tests. Release only the reviewed commit and retain a known-good local version for rollback.
