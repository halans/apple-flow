#!/usr/bin/env python3
"""Optional local benchmark harness for Apple Flow's Ollama connector.

Usage:
  ./scripts/ollama_bench.py --workspace /path/to/repo
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from apple_flow.ollama_connector import OllamaConnector


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local Ollama capability smoke tasks")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument("--workspace", default=".")
    args = parser.parse_args()

    workspace = str(Path(args.workspace).resolve())
    connector = OllamaConnector(
        base_url=args.base_url,
        model=args.model,
        workspace=workspace,
        allowed_workspaces=[workspace],
        auto_pull_model=True,
        inject_tools_context=True,
    )

    tasks = [
        (
            "coding-smoke",
            "List files in the current workspace and summarize the project in 4 bullets.",
            True,
        ),
        (
            "apple-tools-smoke",
            "Run `apple-flow tools messages_list_recent_chats --limit 1` and summarize output.",
            True,
        ),
        (
            "chat-smoke",
            "In one sentence, explain what Apple Flow does.",
            False,
        ),
    ]

    results = []
    for idx, (name, prompt, allow_tools) in enumerate(tasks, start=1):
        started = time.time()
        response = connector.run_turn(
            thread_id=f"bench-{idx}",
            prompt=prompt,
            options={"allow_tools": allow_tools, "cwd": workspace},
        )
        elapsed = round(time.time() - started, 2)
        results.append(
            {
                "name": name,
                "allow_tools": allow_tools,
                "elapsed_seconds": elapsed,
                "response_preview": (response or "")[:300],
            }
        )

    print(json.dumps({"base_url": args.base_url, "model": args.model, "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
