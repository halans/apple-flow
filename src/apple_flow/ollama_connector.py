from __future__ import annotations

import json
import logging
import subprocess
import threading
from pathlib import Path
from typing import Any

import httpx

from .apple_tools import TOOLS_CONTEXT
from .process_registry import ManagedProcessRegistry

logger = logging.getLogger("apple_flow.ollama_connector")


class OllamaConnector:
    """Native Ollama connector using /api/chat with optional tool execution.

    The connector is stateless at process level (HTTP per turn) but keeps a small
    in-memory per-sender context buffer to mirror other Apple Flow connectors.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen3.5:4b",
        workspace: str | None = None,
        timeout: float = 300.0,
        context_window: int = 10,
        inject_tools_context: bool = True,
        system_prompt: str = "",
        num_ctx: int = 32768,
        temperature: float = 0.2,
        auto_pull_model: bool = True,
        tool_timeout_seconds: float = 120.0,
        max_tool_iterations: int = 8,
        max_tool_output_chars: int = 12000,
        allowed_workspaces: list[str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model.strip() or "qwen3.5:4b"
        self.workspace = workspace
        self.timeout = timeout
        self.context_window = context_window
        self.inject_tools_context = inject_tools_context
        self.system_prompt = system_prompt.strip()
        self.num_ctx = int(num_ctx)
        self.temperature = float(temperature)
        self.auto_pull_model = bool(auto_pull_model)
        self.tool_timeout_seconds = float(tool_timeout_seconds)
        self.max_tool_iterations = max(1, int(max_tool_iterations))
        self.max_tool_output_chars = max(1000, int(max_tool_output_chars))
        self.soul_prompt: str = ""
        self._processes = ManagedProcessRegistry("ollama")
        self._sender_contexts: dict[str, list[str]] = {}
        self._contexts_lock = threading.Lock()
        self._pull_lock = threading.Lock()
        self._pulled_models: set[str] = set()
        self.ollama_command = "ollama"

        workspace_roots = allowed_workspaces or ([workspace] if workspace else [])
        self._allowed_workspaces: list[Path] = [
            Path(p).expanduser().resolve() for p in workspace_roots if p
        ]

    def set_soul_prompt(self, soul_prompt: str) -> None:
        """Set companion identity prompt prepended before turn content."""
        self.soul_prompt = soul_prompt.strip()

    def ensure_started(self) -> None:
        """No-op: HTTP API is used directly."""
        pass

    def get_or_create_thread(self, sender: str) -> str:
        return sender

    def reset_thread(self, sender: str) -> str:
        with self._contexts_lock:
            self._sender_contexts.pop(sender, None)
        logger.info("Reset context for sender: %s", sender)
        return sender

    def run_turn(self, thread_id: str, prompt: str, options: dict[str, Any] | None = None) -> str:
        sender = thread_id
        options = options or {}
        allow_tools = bool(options.get("allow_tools", False))
        cwd = str(options.get("cwd", "")).strip() or self.workspace or "."

        full_prompt = self._build_prompt_with_context(sender, prompt)
        messages: list[dict[str, Any]] = [{"role": "user", "content": full_prompt}]

        with self._contexts_lock:
            ctx_len = len(self._sender_contexts.get(sender, []))
        logger.info(
            "Executing Ollama chat: sender=%s model=%s base_url=%s tools=%s timeout=%.1fs context_items=%d",
            sender,
            self.model,
            self.base_url,
            allow_tools,
            self.timeout,
            ctx_len,
        )

        response_text, _ = self._run_chat_loop(
            messages=messages,
            allow_tools=allow_tools,
            sender=sender,
            cwd=cwd,
        )

        if not response_text:
            response_text = "No response generated."

        # Store the exchange using the initial user prompt and final assistant text.
        self._store_exchange(sender, prompt, response_text)
        return response_text

    def run_turn_streaming(
        self,
        thread_id: str,
        prompt: str,
        on_progress: Any = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Streaming fallback for API parity.

        Ollama native streaming can be added later; for now we return the final
        text and emit one progress callback if requested.
        """
        response = self.run_turn(thread_id, prompt, options=options)
        if on_progress and response:
            on_progress(response)
        return response

    def shutdown(self) -> None:
        logger.info("Ollama connector shutdown (no-op)")

    def cancel_active_processes(self, thread_id: str | None = None) -> int:
        """Cancel active tool subprocesses for one sender or globally."""
        return self._processes.cancel(thread_id)

    def _run_chat_loop(
        self,
        *,
        messages: list[dict[str, Any]],
        allow_tools: bool,
        sender: str,
        cwd: str,
    ) -> tuple[str, list[dict[str, Any]]]:
        for _ in range(self.max_tool_iterations):
            response = self._chat(messages=messages, allow_tools=allow_tools)
            if isinstance(response, str):
                # error path
                return response, messages

            message = response.get("message") or {}
            content = str(message.get("content") or "").strip()
            tool_calls = self._extract_tool_calls(message)

            if not allow_tools or not tool_calls:
                return content, messages

            messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})

            for tool_call in tool_calls:
                tool_name = str(tool_call.get("function", {}).get("name", ""))
                raw_args = tool_call.get("function", {}).get("arguments", {})
                parsed_args = self._coerce_tool_args(raw_args)

                if tool_name != "run_shell_command":
                    result_text = f"Unsupported tool: {tool_name}"
                else:
                    command = str(parsed_args.get("command", "")).strip()
                    result_text = self._run_shell_tool(
                        sender=sender,
                        command=command,
                        cwd=cwd,
                    )

                messages.append(
                    {
                        "role": "tool",
                        "name": tool_name,
                        "content": result_text,
                    }
                )

        return "Error: Tool loop exceeded maximum iterations.", messages

    def _chat(self, *, messages: list[dict[str, Any]], allow_tools: bool) -> dict[str, Any] | str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_ctx": self.num_ctx,
                "temperature": self.temperature,
            },
        }
        if allow_tools:
            payload["tools"] = self._tool_schemas()

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(f"{self.base_url}/api/chat", json=payload)
        except Exception as exc:
            logger.exception("Ollama request failed: %s", exc)
            return f"Error: Failed to reach Ollama at {self.base_url}. {type(exc).__name__}: {exc}"

        if resp.status_code >= 400:
            body = resp.text.strip()
            if self._is_missing_model_response(resp.status_code, body):
                if self.auto_pull_model and self._ensure_model_pulled(self.model):
                    # Retry once after pull.
                    try:
                        with httpx.Client(timeout=self.timeout) as client:
                            retry = client.post(f"{self.base_url}/api/chat", json=payload)
                        if retry.status_code < 400:
                            return retry.json()
                        body = retry.text.strip()
                    except Exception as exc:
                        logger.exception("Ollama retry after pull failed: %s", exc)
                        return f"Error: Model pull succeeded but retry failed: {type(exc).__name__}: {exc}"

                pull_help = f"Run: ollama pull {self.model}"
                return f"Error: Ollama model '{self.model}' is not available. {pull_help}"

            return f"Error: Ollama chat failed (HTTP {resp.status_code}). {body or 'No details.'}"

        try:
            return resp.json()
        except Exception as exc:
            logger.exception("Invalid Ollama JSON response: %s", exc)
            return f"Error: Invalid Ollama response: {type(exc).__name__}: {exc}"

    def _ensure_model_pulled(self, model: str) -> bool:
        with self._pull_lock:
            if model in self._pulled_models:
                return True

            logger.info("Model %s missing, attempting auto-pull", model)
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    with client.stream(
                        "POST",
                        f"{self.base_url}/api/pull",
                        json={"name": model, "stream": True},
                    ) as resp:
                        if resp.status_code >= 400:
                            logger.error(
                                "Ollama pull failed for model=%s status=%s body=%s",
                                model,
                                resp.status_code,
                                resp.text,
                            )
                            return False

                        for line in resp.iter_lines():
                            if not line:
                                continue
                            try:
                                event = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            if event.get("error"):
                                logger.error("Ollama pull error for model=%s: %s", model, event.get("error"))
                                return False
                            if event.get("status") == "success":
                                self._pulled_models.add(model)
                                return True
                # Some versions complete without explicit success event.
                self._pulled_models.add(model)
                return True
            except Exception:
                logger.exception("Ollama auto-pull failed for model=%s", model)
                return False

    @staticmethod
    def _is_missing_model_response(status_code: int, body: str) -> bool:
        if status_code not in {400, 404}:
            return False
        lowered = (body or "").lower()
        return "model" in lowered and ("not found" in lowered or "pull" in lowered)

    @staticmethod
    def _coerce_tool_args(raw_args: Any) -> dict[str, Any]:
        if isinstance(raw_args, dict):
            return raw_args
        if isinstance(raw_args, str):
            text = raw_args.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {"command": text}
        return {}

    @staticmethod
    def _extract_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            return [tc for tc in tool_calls if isinstance(tc, dict)]

        # Compatibility fallback for variants that place tool calls elsewhere.
        function_call = message.get("function_call")
        if isinstance(function_call, dict):
            return [{"function": function_call}]
        return []

    def _run_shell_tool(self, *, sender: str, command: str, cwd: str) -> str:
        if not command:
            return "Error: Missing 'command' argument."

        exec_cwd = self._resolve_exec_cwd(cwd)
        if exec_cwd is None:
            return "Error: Command blocked by workspace policy (outside allowed_workspaces)."

        proc: subprocess.Popen[str] | None = None
        try:
            proc = subprocess.Popen(
                ["/bin/zsh", "-lc", command],
                cwd=str(exec_cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            self._processes.register(sender, proc)
            stdout, stderr = proc.communicate(timeout=self.tool_timeout_seconds)
            rc = int(proc.returncode or 0)
            stdout = self._trim_output(stdout)
            stderr = self._trim_output(stderr)
            result = {
                "exit_code": rc,
                "stdout": stdout,
                "stderr": stderr,
                "timed_out": False,
                "cwd": str(exec_cwd),
            }
            return json.dumps(result, ensure_ascii=False)
        except subprocess.TimeoutExpired:
            if proc is not None:
                self._processes.terminate(proc)
            result = {
                "exit_code": 124,
                "stdout": "",
                "stderr": f"Command timed out after {int(self.tool_timeout_seconds)}s.",
                "timed_out": True,
                "cwd": str(exec_cwd),
            }
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            logger.exception("Shell tool execution failed: %s", exc)
            result = {
                "exit_code": 1,
                "stdout": "",
                "stderr": f"{type(exc).__name__}: {exc}",
                "timed_out": False,
                "cwd": str(exec_cwd),
            }
            return json.dumps(result, ensure_ascii=False)
        finally:
            if proc is not None:
                self._processes.unregister(proc)

    def _resolve_exec_cwd(self, requested_cwd: str) -> Path | None:
        try:
            candidate = Path(requested_cwd).expanduser().resolve()
        except Exception:
            return None

        if not self._allowed_workspaces:
            return candidate

        for allowed in self._allowed_workspaces:
            if candidate == allowed or allowed in candidate.parents:
                return candidate
        return None

    def _trim_output(self, text: str) -> str:
        if not text:
            return ""
        if len(text) <= self.max_tool_output_chars:
            return text
        return text[: self.max_tool_output_chars] + "\n...[truncated]"

    def _build_prompt_with_context(self, sender: str, prompt: str) -> str:
        with self._contexts_lock:
            history = list(self._sender_contexts.get(sender, []))

        parts: list[str] = []
        if self.soul_prompt:
            parts.append(self.soul_prompt)
        if self.system_prompt:
            parts.append(self.system_prompt)
        if self.inject_tools_context:
            parts.append(TOOLS_CONTEXT)
        if history:
            recent = history[-self.context_window :]
            context_text = "\n\n".join(recent)
            parts.append(f"Previous conversation context:\n{context_text}")
        parts.append(f"New message:\n{prompt}" if history or self.inject_tools_context else prompt)
        return "\n\n".join(parts)

    def _store_exchange(self, sender: str, user_message: str, assistant_response: str) -> None:
        exchange = f"User: {user_message}\nAssistant: {assistant_response}"
        max_history = self.context_window * 2
        with self._contexts_lock:
            if sender not in self._sender_contexts:
                self._sender_contexts[sender] = []
            self._sender_contexts[sender].append(exchange)
            if len(self._sender_contexts[sender]) > max_history:
                self._sender_contexts[sender] = self._sender_contexts[sender][-max_history:]

    @staticmethod
    def _tool_schemas() -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "run_shell_command",
                    "description": (
                        "Execute a shell command in the allowed workspace. "
                        "Use this for coding tasks and apple-flow tools invocations."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "Shell command to run.",
                            }
                        },
                        "required": ["command"],
                        "additionalProperties": False,
                    },
                },
            }
        ]
