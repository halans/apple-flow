---
name: apple-flow-pages
description: Universal Markdown-to-Apple-Pages formatting skill for Apple Flow. Use when converting `.md` files into polished `.pages` documents with accurate structure (headings, lists, tables, code blocks, links) and clean business-ready styling.
---

# Apple Flow Pages

Use this skill to turn markdown into polished Apple Pages documents quickly.

Primary command:
- `apple-flow tools pages_from_markdown <input.md|-> [output.pages] [--theme auto|neutral|minimal|corporate|legal|proposal] [--style auto|neutral] [--title-page auto|off] [--toc auto|off] [--citations auto|off] [--images auto|off] [--image-max-width N] [--page-break-marker TEXT] [--qa true|false] [--export none|pdf|docx|pdf,docx] [--overwrite true|false]`

Related commands:
- `apple-flow tools pages_update_sections <base.md|-> <updates.md> <output.pages> [--sections "A,B"] [same render flags]`
- `apple-flow tools pages_template <research|contract|proposal> [output.md] [--overwrite true|false]`

## Quick Start

1. Convert markdown using default output path (`same-name.pages`):
```bash
apple-flow tools pages_from_markdown \
  "/abs/path/proposal.md"
```

2. Convert to explicit destination:
```bash
apple-flow tools pages_from_markdown \
  "/abs/path/contract.md" \
  "/abs/path/client-contract.pages" \
  --theme legal \
  --title-page on \
  --toc on \
  --overwrite true
```

3. Use neutral style:
```bash
apple-flow tools pages_from_markdown \
  "/abs/path/notes.md" \
  "/abs/path/notes.pages" \
  --style neutral \
  --overwrite true
```

4. On-the-fly generation (no pre-existing markdown file):
```bash
cat <<'MD' | apple-flow tools pages_from_markdown - "/abs/path/ai-agent-systems.pages" --style auto --overwrite true
# AI Agent Systems Report

## Executive Summary
...

## Landscape
...
MD
```

5. Render with deterministic QA + exports:
```bash
apple-flow tools pages_from_markdown \
  "/abs/path/research.md" \
  "/abs/path/research.pages" \
  --theme corporate \
  --toc on \
  --citations on \
  --qa true \
  --export pdf,docx \
  --overwrite true
```

6. Merge only selected sections and render:
```bash
apple-flow tools pages_update_sections \
  "/abs/path/base-proposal.md" \
  "/abs/path/updates.md" \
  "/abs/path/final-proposal.pages" \
  --sections "Executive Summary,Timeline,Risks" \
  --theme proposal \
  --overwrite true
```

7. Create a starter template:
```bash
apple-flow tools pages_template proposal "/abs/path/proposal-template.md"
```

## Research-to-Report Workflow

When user asks:
- "Do research on the web for AI agent systems and make a beautiful Pages report"

Use this sequence:
1. Perform web research first (collect sources, key findings, comparisons).
2. Draft a structured markdown report:
   - title
   - executive summary
   - findings
   - comparison table
   - recommendations
3. Pipe markdown via stdin to `pages_from_markdown` (or save `.md` then convert).
4. Return final `.pages` path plus short summary.

## Supported Markdown

- Headings (`#`, `##`, `###`)
- Paragraphs
- Unordered and ordered lists
- Horizontal rules (`---`, `***`, `___`)
- Inline formatting: bold, italic, code, links
- Fenced code blocks
- Markdown tables

## Input / Output Rules

- Input file must exist and be UTF-8 text.
- Input can be `-` to read markdown from stdin.
- Output must end with `.pages`.
- If output path is omitted, default is `<input_basename>.pages` in the same directory.
- Existing output is blocked unless `--overwrite true`.
- `pages_template` outputs `.md` files (not `.pages`).

## Troubleshooting

- `input file not found`:
  - Confirm absolute path and file name.
- `output exists and overwrite=false`:
  - Re-run with `--overwrite true` or choose another output path.
- `Application isn’t running` / AppleScript errors:
  - Launch Pages once manually and grant Automation permissions, then retry.
- `textutil conversion failed`:
  - Confirm macOS `textutil` availability and source markdown readability.

## Done Criteria

- Command returns `"ok": true`.
- `output_path` points to a real `.pages` file.
- Result stats look sensible (headings/lists/tables/code counts align with source markdown).
