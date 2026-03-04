---
name: apple-flow-gateways
description: Core routing and troubleshooting skill for Apple Flow gateways (Mail, Reminders, Notes, Calendar). Use when deciding which `apple-flow tools` command to run, applying shared safety rules, or debugging gateway permissions/resource-name mismatches.
---

# Apple Flow Gateways

Use this as the first-stop skill for cross-gateway work. It helps choose the right command path quickly and safely.

## Use This Skill For

- Picking the right gateway tool for a user request.
- Running quick health checks for Mail, Reminders, Notes, or Calendar.
- Troubleshooting empty results, app permission prompts, or wrong resource names.
- Applying shared Apple Flow safety defaults before mutating workflows.

## Command Matrix

- Mail:
  - `apple-flow tools mail_list_unread`
  - `apple-flow tools mail_search <query>`
  - `apple-flow tools mail_get_content <message_id>`
  - `apple-flow tools mail_send <to> <subject> <body>`
  - `apple-flow tools mail_move_to_label --label <name> --message-id <id>`
- Reminders:
  - `apple-flow tools reminders_list_lists`
  - `apple-flow tools reminders_list --list "<list>"`
  - `apple-flow tools reminders_search <query> --list "<list>"`
  - `apple-flow tools reminders_create "<name>" --list "<list>" --due YYYY-MM-DD`
  - `apple-flow tools reminders_complete <id> --list "<list>"`
- Notes:
  - `apple-flow tools notes_list_folders`
  - `apple-flow tools notes_list --folder "<folder>"`
  - `apple-flow tools notes_search <query> --folder "<folder>"`
  - `apple-flow tools notes_get_content "<title-or-id>" --folder "<folder>"`
  - `apple-flow tools notes_create "<title>" "<body>" --folder "<folder>"`
  - `apple-flow tools notes_append "<title-or-id>" "<text>" --folder "<folder>"`
- Calendar:
  - `apple-flow tools calendar_list_calendars`
  - `apple-flow tools calendar_list_events --cal "<calendar>" --days 7`
  - `apple-flow tools calendar_search <query> --cal "<calendar>"`
  - `apple-flow tools calendar_create "<title>" "<start>" --end "<end>" --cal "<calendar>"`

## Shared Safety Rules

- Keep mutating intent behind approval flows (`task:` and `project:`) in relay workflows.
- Prefer read/list/search before create/update operations.
- Use explicit list/folder/calendar/account names instead of assuming defaults in critical runs.
- Use absolute paths for file-backed tools.

## Quick Gateway Triage

1. Confirm macOS app access:
   - first run may require Automation permissions.
2. Confirm resource names:
   - reminders list, notes folder, calendar names must exactly match.
3. Run a list command first:
   - if list fails/empty unexpectedly, do not continue with mutations.
4. Re-run with explicit selectors:
   - `--list`, `--folder`, `--cal`, `--account`, `--mailbox`.

## Escalate To Specialized Skill

- For multi-step mailbox triage, message-id handling, or label workflows, use `apple-flow-mail`.

## Done Criteria

- Correct gateway chosen for the request.
- Read command confirms expected target objects.
- Mutating step uses explicit resource selectors and succeeds.
