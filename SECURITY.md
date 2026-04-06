# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Aulinx, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please email: **security@aulinx.com**

Or use [GitHub's private vulnerability reporting](https://github.com/aulinx/aulinx/security/advisories/new).

## What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

## Response Timeline

- **Acknowledgment**: Within 48 hours
- **Assessment**: Within 1 week
- **Fix**: As soon as possible, depending on severity

## Scope

The following are in scope:

- The `aulinx` Python package
- The `ui/` React frontend
- The WebSocket server (`aulinx --serve`)
- Tool execution and permission system
- Audit logging and secret redaction

## Security Considerations

Aulinx gives an AI agent access to your desktop. Key security measures:

- **Permission tiers**: Tools are classified by risk level (OBSERVE → IRREVERSIBLE)
- **User confirmation**: Destructive actions always require explicit approval
- **Audit logging**: Every tool call is logged with timestamps and arguments
- **Secret redaction**: Passwords, tokens, and API keys are redacted from audit logs
- **Shell sandboxing**: `shell_exec` runs in the user's home directory with timeout limits

## Responsible Disclosure

We follow responsible disclosure practices. We will credit reporters in our security advisories unless they prefer to remain anonymous.
