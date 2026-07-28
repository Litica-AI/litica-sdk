# Security Policy

## Reporting a vulnerability

**Do not open a public issue for a security problem.**

Report it privately through
[GitHub's private vulnerability reporting](https://github.com/Litica-AI/litica-sdk/security/advisories/new),
or by email to **security@litica.org**.

Please include:

- what the issue is and what an attacker could do with it
- steps to reproduce, or a proof of concept
- the SDK version and Python version
- anything you think we would otherwise miss

**Redact your API key** and any memory contents from reproductions.

## What to expect

- **Acknowledgement within 3 business days.**
- An assessment and an expected timeline within 10 business days.
- We will keep you updated as we work on a fix, and credit you in the advisory
  unless you would rather stay anonymous.

Please give us a reasonable opportunity to ship a fix before disclosing
publicly.

## Scope

This policy covers the `litica` Python package in this repository — for example
credential handling, TLS verification, or a parsing flaw in the client.

Vulnerabilities in the **Litica service** are not in scope here; report those to
security@litica.org directly, not through this repository's issue tracker.

## Supported versions

While the SDK is `0.x`, only the latest released version receives security
fixes. Once `1.0` ships, this section will state a support window.

## Keeping your API key safe

A Litica API key grants full read and write access to your tenant's memories.

- Supply it via the `LITICA_API_KEY` environment variable or a secrets manager —
  never commit it to source control
- Do not paste it into issues, logs, or tracebacks
- Rotate it if you suspect exposure
- Use a separate key per environment, so revoking one does not take down others

The SDK sends your key only as an `X-API-Key` header to the `base_url` you
configure. It is never logged by the client, and never written to disk.
