# Security Policy

## Supported Versions

Apple Flow is in active development, and security fixes are supported on the latest release only.

| Version | Supported |
| ------- | --------- |
| latest release | ✅ |
| older releases | ❌ (upgrade required) |

## Security Model

Apple Flow is local-first and ships with security-first defaults for message intake, workspace access, and mutating actions.

### Core Controls

#### 1. Sender allowlist
- Inbound processing is restricted to `apple_flow_allowed_senders`.
- With `apple_flow_only_poll_allowed_senders=true` (default), filtering happens at query time.
- Unknown senders are ignored.

#### 2. Workspace restrictions
- Agent work is restricted to `apple_flow_allowed_workspaces`.
- Path validation blocks traversal outside allowed roots.
- Workspace aliases resolve only to allowlisted paths.

#### 3. Approval workflow for mutating actions
- `task:` and `project:` require explicit approval.
- Approvals expire after `apple_flow_approval_ttl_minutes` (default: `20`).
- Only the original requester can approve or deny their own request.
- `deny all` is available to clear pending approvals quickly.

#### 4. Per-sender rate limiting
- Enforced by `apple_flow_max_messages_per_minute` (default: `30`).
- Protects against spam and accidental runaway loops.

#### 5. Read-only iMessage ingress
- Messages DB is opened read-only (`mode=ro` and query-only behavior).
- Apple Flow does not write to `chat.db`.
- Full Disk Access is still required on macOS for the host process.

#### 6. Connector process isolation
- Supported connectors include `codex-cli`, `claude-cli`, `gemini-cli`, `kilo-cli`, `cline`, and `ollama`.
- Connector invocations are isolated to reduce long-lived shared state risks.
- Conversation/session state is managed by Apple Flow with explicit controls.

#### 7. Admin API authentication
- If `apple_flow_admin_api_token` is set, Admin API routes (except `/health`) require a Bearer token.
- Token values are shared secrets and should be rotated if exposed.

#### 8. Egress hardening
- Duplicate/echo suppression fingerprints outbound responses.
- AppleScript-bound strings are escaped on egress paths to reduce script injection risk.

## Threat Model

### In Scope: Threats Apple Flow Mitigates

| Threat | Mitigation |
| ------ | ---------- |
| Unauthorized sender actions | Sender allowlist + optional SQL-time filtering |
| Path traversal / workspace escape | Allowlist path validation |
| Unapproved mutating execution | Approval gate + requester verification |
| Message echo loops | Duplicate suppression + fingerprinting |
| Abuse via rapid message bursts | Per-sender rate limits |
| Stale approvals being replayed | Approval TTL + status checks |
| AppleScript string injection | Escaping in egress modules |
| Admin endpoint misuse | Optional Bearer token auth |

### Out of Scope: Threats Not Fully Mitigated

| Threat | Reason |
| ------ | ------ |
| Compromised local macOS user account | Apple Flow runs with local user privileges |
| Physical access to unlocked machine | Local data can be accessed by local user/session |
| Malicious or incorrect model output | Depends on selected model/provider behavior |
| Prompt injection from trusted app content | Mail/Notes/Reminders/Calendar text may be model input |
| Network interception for remote providers | Connector traffic may leave host if non-local providers are used |

## Data Handling

- **Runtime state DB**: defaults to `~/.apple-flow/relay.db` (`apple_flow_db_path`).
- **iMessage source DB**: defaults to `~/Library/Messages/chat.db` (`apple_flow_messages_db_path`), read-only access.
- **Agent office content**: Markdown/state under `agent-office/` (scaffold tracked, personal content generally gitignored).
- **Memory**:
- Legacy file memory can use `agent-office/MEMORY.md` and `agent-office/60_memory/*.md`.
- Canonical memory v2 can use `apple_flow_memory_v2_db_path` (default empty means `<agent-office>/.apple-flow-memory.sqlite3`).
- **Attachments**: when enabled, extracted to a temp workspace (default `/tmp/apple_flow_attachments`) for processing.
- **Logs/audit**: local logs and optional CSV audit output (`apple_flow_csv_audit_log_path`).

## Vulnerability Reporting

Report security issues through GitHub Security Advisories:

- https://github.com/dkyazzentwatwa/apple-flow/security/advisories

Do not open public issues for suspected vulnerabilities.

### What to include

1. A clear description of the vulnerability.
2. Affected versions or commit range (if known).
3. Reproduction steps or proof-of-concept.
4. Security impact (confidentiality, integrity, availability).
5. Any proposed remediation ideas.

### Disclosure expectations

1. Use private advisory reporting first.
2. Give maintainers reasonable time to triage and prepare a fix.
3. Coordinate public disclosure timing with maintainers when possible.

### Response targets

- Initial acknowledgement: within 48 hours.
- Triage update: within 7 days.
- Remediation timeline: severity-dependent and communicated during triage.

## Security Best Practices

1. Keep `apple_flow_allowed_senders` minimal (ideally only your own sender IDs).
2. Keep `apple_flow_allowed_workspaces` narrow.
3. Require review before approving `task:`/`project:` actions.
4. Set `apple_flow_admin_api_token` for any enabled admin API deployment.
5. Keep Apple Flow and connector tooling updated.
6. Protect the host: FileVault, OS updates, strong local account hygiene.

## Security Configuration Checklist

```env
# Baseline controls
apple_flow_allowed_senders=+15551234567
apple_flow_allowed_workspaces=/Users/you/code
apple_flow_only_poll_allowed_senders=true

# Approval + abuse controls
apple_flow_approval_ttl_minutes=20
apple_flow_max_messages_per_minute=30

# Intake mode
apple_flow_require_chat_prefix=false

# Admin API hardening
apple_flow_admin_api_token=<strong-random-secret>

# Optional integration hardening
apple_flow_mail_allowed_senders=you@example.com
apple_flow_reminders_auto_approve=false
apple_flow_notes_auto_approve=false
apple_flow_calendar_auto_approve=false
```

## Hardening Status

AppleScript escaping and approval sender verification are foundational controls in current releases. A third-party security audit is still recommended before high-risk or large-scale deployments.

---

**Last updated**: 2026-03-05
