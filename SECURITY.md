# Security Policy

This project runs a multi-agent local runtime with filesystem, shell, Python execution, web access, recursive delegation, and an encrypted key hierarchy. Treat it as a privileged local operator, not as a public chatbot. Untrusted prompts can attempt to influence tool use; the denylist and prompt policy are defense-in-depth, not a complete operating-system sandbox.

## Keys and vault

- Keep the Super Key passphrase out of files, shell history, chat logs, screenshots, and environment variables. The encrypted runtime vault under `keys/vault/` is local state and must not be committed or synchronized to an unapproved destination.
- Keep API/provider tokens in the intended local vault or ignored environment files. Cloud providers receive the prompts and context sent to them; choose a local Ollama route for data that must not leave the device.
- Do not print plaintext key material, copy the vault into bug reports, or run key initialization/rotation scripts as routine tests. Test key derivation against temporary directories only.
- A suspected key compromise requires immediate rotation of the affected tier and review of audit records; rotate the Super Key only through the documented recovery flow.

## Tool authority and network

Run only from a trusted user account and a private local workstation. Do not expose the tool runtime or UI server to a public/LAN interface without a separate authentication and sandbox review. Keep dangerous-command approval gates in place across every provider, and review shell/file tools after any routing or model change. Never execute a model-suggested destructive command blindly.

## Reporting

Report security issues privately to the repository owner or through the host's private vulnerability-reporting facility. Include a minimal synthetic reproduction. Do not share credentials, vault contents, user prompts, private workspace paths, or raw encrypted/unencrypted audit material publicly.
