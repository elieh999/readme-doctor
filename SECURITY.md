# Security policy

## Supported versions

Security fixes are provided for the latest released minor version.

## Reporting a vulnerability

Use GitHub private vulnerability reporting for the repository when available. If it is unavailable,
contact the repository owner privately. Do not include secrets or working exploits in a public
issue.

Include the affected version, platform, reproduction steps, impact, and any suggested mitigation.

## Scope

Command execution, path escape, symlink escape, unsafe YAML, network credential leakage, secret
redaction failures, and unsafe GitHub Action behavior are security relevant.

README Doctor does not execute commands or use network access by default. Enabling either feature
expands the attack surface. Secret redaction is a defense in depth measure and is not guaranteed to
identify every credential format.
