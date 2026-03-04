---
name: apple-flow-mail
description: Deep workflow skill for Apple Flow Mail operations. Use for unread triage, message-id content fetch, mailbox/account targeting, label moves, and reply/send flows where deterministic sequencing matters.
---

# Apple Flow Mail

Use this skill when Mail work needs a reliable multi-step flow instead of one-off commands.

## Scope

- Unread inbox triage
- Search and content retrieval by `message_id`
- Bulk or targeted mailbox/label moves
- Outbound email send flows
- Mail-specific troubleshooting

## Standard Triage Flow

1. List unread messages:
```bash
apple-flow tools mail_list_unread --account "<account>" --mailbox "INBOX" --limit 20
```

2. Inspect specific message content:
```bash
apple-flow tools mail_get_content "<message_id>" --account "<account>" --mailbox "INBOX"
```

3. Move classified items:
```bash
apple-flow tools mail_move_to_label --label "<target-mailbox>" --message-id "<message_id>" --account "<account>" --mailbox "INBOX"
```

4. Send new email when needed:
```bash
apple-flow tools mail_send "user@example.com" "Subject" "Body text" --account "<account>"
```

## Search Flow

1. Query by keyword/time window:
```bash
apple-flow tools mail_search "<query>" --account "<account>" --mailbox "INBOX" --days 30 --limit 20
```

2. Pull full body for decision-critical items with `mail_get_content`.

3. Apply move/send action only after content confirmation.

## Message ID Handling Rules

- Treat `message_id` as authoritative for follow-up commands.
- Never infer message identity from subject alone.
- When batching, pass repeated `--message-id` flags or use `--input-file` JSON.

Batch example:
```bash
apple-flow tools mail_move_to_label \
  --label "Archive/Newsletters" \
  --message-id "id-1" \
  --message-id "id-2" \
  --account "<account>" \
  --mailbox "INBOX"
```

## Mailbox/Account Targeting Rules

- Always specify `--account` in multi-account environments.
- Default source mailbox is `INBOX`; override `--mailbox` when triaging another source.
- Validate destination labels/mailboxes exist before large batch moves.

## Common Failure Patterns

- Empty unread/search results:
  - wrong account or mailbox selected
  - time window too narrow (`--days`)
- `mail_get_content` fails:
  - stale or invalid `message_id`
  - message moved out of current source mailbox
- Move failures:
  - destination label/mailbox name mismatch
  - source mailbox mismatch

## Guardrails

- Use read-first sequencing: list/search -> get_content -> move/send.
- For high-impact changes, perform small sample batches first.
- Keep mutating automations behind approval controls in relay workflows.

## Done Criteria

- Intended messages were identified by `message_id`, not guesswork.
- Move/send operations succeeded with explicit account/mailbox context.
- Post-action spot check confirms expected mailbox state.
