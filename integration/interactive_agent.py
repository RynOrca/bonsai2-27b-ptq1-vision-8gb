"""Standard-library SSE Agent adapter. Never executes arbitrary shell commands."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import threading
import urllib.request


class AgentError(RuntimeError):
    """The turn cannot safely continue automatically."""


class Cancelled(AgentError):
    pass


def default_system_prompt():
    path = Path(__file__).with_name("interactive-agent-system-prompt.md")
    if path.exists():
        # Exclude deployment notes from the model's instructions.
        return (path.read_text(encoding="utf-8").split("## 配套设置")[0].strip()
                + "\n遵守调用方输出格式；允许阶段汇报时，每次不超过100字。"
                "依据实际动作和工具结果汇报，不按固定token或时间强制结束思考。")
    return ("遵守调用方格式要求；将复杂任务拆成小阶段，尽早使用工具。"
            "每阶段用100字以内正文汇报可观察动作、结果和下一步，不展示内部思考。")


class InteractiveAgent:
    def __init__(self, tools=(), execute_tool=None, on_event=None, *,
                 base_url="http://127.0.0.1:18200/v1", model="qwen3.8-27b-long",
                 api_key=None, max_rounds=12, timeout=120, opener=None,
                 request_options=None, no_progress_limit=3):
        self.tools = copy.deepcopy(list(tools))
        self.allowed = {tool["function"]["name"] for tool in self.tools}
        self.execute_tool = execute_tool
        self.on_event = on_event or (lambda event: None)
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model, self.api_key = model, api_key
        if max_rounds < 1:
            raise ValueError("max_rounds must be positive")
        self.max_rounds, self.timeout = max_rounds, timeout
        if no_progress_limit is not None and no_progress_limit < 2:
            raise ValueError("no_progress_limit must be at least 2 or None")
        self.no_progress_limit = no_progress_limit
        self.opener = opener or urllib.request.urlopen
        # Keep template options stable across a session and retain reasoning in history.
        # In the supplied qwen3_8 template, unset and true both preserve reasoning; explicit
        # false removes it from assistant turns before the latest user query. Setting true
        # makes this intent explicit; it is not sufficient by itself to guarantee KV reuse.
        self.options = dict(max_completion_tokens=16384, reasoning_effort="medium",
                            preserve_thinking=True)
        self.options.update(request_options or {})
        if {"messages", "tools", "stream", "stream_options"} & self.options.keys():
            raise ValueError("request_options cannot override protocol fields")

    def emit(self, event_type, **values):
        self.on_event(dict(type=event_type, **values))

    @staticmethod
    def check_cancel(cancel):
        if cancel is not None and cancel.is_set():
            raise Cancelled("cancelled; synchronous HTTP observes cancellation at read boundaries")

    def events(self, response, cancel):
        """SSE fields may span lines; comments/heartbeats are cancellation boundaries."""
        data, kind = [], "message"
        while True:
            self.check_cancel(cancel)
            line = response.readline()
            self.check_cancel(cancel)
            if not line:
                if data:
                    yield kind, "\n".join(data)
                return
            line = line.decode("utf-8").rstrip("\r\n")
            if not line:
                if data:
                    yield kind, "\n".join(data)
                data, kind = [], "message"
            elif line.startswith(":"):
                self.emit("heartbeat")
            else:
                field, _, value = line.partition(":")
                value = value.removeprefix(" ")
                if field == "data":
                    data.append(value)
                elif field == "event":
                    kind = value

    def run(self, messages, cancel=None):
        """Mutates messages with assistant/tool turns, including partial failed output.

        execute_tool(name, arguments, call_id) must implement its own authorization,
        validation and persistent idempotency. on_event receives no reasoning text.
        """
        try:
            previous_tool_round, repeated_rounds = None, 0
            for round_index in range(self.max_rounds):
                self.check_cancel(cancel)
                self.emit("waiting", round=round_index + 1,
                          message="等待服务端（可能正在冷预填充）")
                body = dict(self.options, model=self.model, messages=messages,
                            stream=True, stream_options={"include_usage": True})
                if self.tools:
                    body["tools"] = self.tools
                headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
                if self.api_key:
                    headers["Authorization"] = "Bearer " + self.api_key
                req = urllib.request.Request(self.url, json.dumps(body).encode(), headers)
                assistant = {"role": "assistant", "content": ""}
                calls, reasoning, finish = {}, "", None
                recorded = False
                completed_stream = False

                def record():
                    nonlocal recorded
                    if not recorded and (assistant["content"] or calls or reasoning or finish):
                        if calls:
                            assistant["tool_calls"] = [calls[i] for i in sorted(calls)]
                        if reasoning:
                            assistant["reasoning_content"] = reasoning
                        messages.append(assistant)
                        recorded = True

                try:
                    with self.opener(req, timeout=self.timeout) as response:
                        for kind, raw in self.events(response, cancel):
                            if raw == "[DONE]":
                                completed_stream = True
                                break
                            try:
                                chunk = json.loads(raw)
                            except ValueError as exc:
                                raise AgentError("invalid SSE JSON") from exc
                            if kind == "error" or "error" in chunk:
                                # Do not leak a server's diagnostic (possibly reasoning) to UI.
                                raise AgentError("server SSE error; inspect trusted server logs")
                            if chunk.get("usage") is not None:
                                self.emit("usage", usage=chunk["usage"])
                            for choice in chunk.get("choices", []):
                                if choice.get("index", 0) != 0:
                                    raise AgentError("adapter supports one completion only")
                                delta = choice.get("delta", {})
                                if delta.get("content"):
                                    assistant["content"] += delta["content"]
                                    self.emit("content", text=delta["content"])
                                reasoning += delta.get("reasoning_content") or delta.get("reasoning") or ""
                                for fragment in delta.get("tool_calls", []):
                                    index = fragment["index"]
                                    call = calls.setdefault(index, {"id": "", "type": "function",
                                                                   "function": {"name": "", "arguments": ""}})
                                    call["id"] += fragment.get("id", "")
                                    if fragment.get("type", "function") != "function":
                                        raise AgentError("unsupported tool type")
                                    for key in ("name", "arguments"):
                                        call["function"][key] += fragment.get("function", {}).get(key, "")
                                if choice.get("finish_reason") is not None:
                                    finish = choice["finish_reason"]
                    record()
                except Exception:
                    record()
                    raise
                self.check_cancel(cancel)
                if not completed_stream:
                    raise AgentError("incomplete SSE stream: missing [DONE]; no tools executed")
                self.emit("finish", reason=finish)
                if finish == "length":
                    raise AgentError("length: partial output preserved; no tools executed or request retried")
                if finish == "stop" and not calls:
                    return messages
                if finish != "tool_calls" or not calls:
                    raise AgentError("missing or inconsistent terminal finish_reason")
                # Validate the entire batch before any tool has side effects.
                parsed, ids = [], set()
                for call in assistant["tool_calls"]:
                    name, call_id = call["function"]["name"], call["id"]
                    if name not in self.allowed or self.execute_tool is None:
                        raise AgentError("unknown or unavailable tool: " + name)
                    if not call_id or call_id in ids:
                        raise AgentError("missing or duplicate tool call id")
                    ids.add(call_id)
                    try:
                        arguments = json.loads(call["function"]["arguments"])
                    except ValueError as exc:
                        raise AgentError("invalid tool arguments") from exc
                    if not isinstance(arguments, dict):
                        raise AgentError("tool arguments must be an object")
                    parsed.append((name, arguments, call_id))
                if round_index + 1 == self.max_rounds:
                    raise AgentError("max_rounds reached; tools not executed without room for continuation")
                tool_round = []
                for name, arguments, call_id in parsed:
                    self.check_cancel(cancel)
                    self.emit("tool_start", name=name, call_id=call_id)
                    self.check_cancel(cancel)
                    result = self.execute_tool(name, arguments, call_id)
                    messages.append({"role": "tool", "tool_call_id": call_id,
                                     "content": result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)})
                    tool_round.append((name, json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                                       messages[-1]["content"]))
                    self.emit("tool_end", name=name, call_id=call_id)
                # Only consecutive identical call batches AND identical results count.
                # A polling tool returning new state resets this conservative guard.
                repeated_rounds = repeated_rounds + 1 if tool_round == previous_tool_round else 1
                previous_tool_round = tool_round
                if self.no_progress_limit is not None and repeated_rounds >= self.no_progress_limit:
                    self.emit("no_progress", consecutive_rounds=repeated_rounds)
                    raise AgentError("no_progress: repeated tool calls and unchanged results")
            raise AgentError("max_rounds reached")
        except Cancelled:
            self.emit("cancelled")
            raise
        except Exception as exc:
            self.emit("error", message=str(exc))
            raise


ADD_TOOL = {"type": "function", "function": {"name": "add", "description": "Add two numbers locally",
            "parameters": {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                           "required": ["a", "b"], "additionalProperties": False}}}


def demo_tool(name, arguments, call_id):
    if name != "add" or set(arguments) != {"a", "b"}:
        raise AgentError("demo permits only add(a, b)")
    if any(type(value) not in (int, float) for value in arguments.values()):
        raise AgentError("a and b must be numbers")
    return {"sum": arguments["a"] + arguments["b"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt")
    parser.add_argument("--base-url", default="http://127.0.0.1:18200/v1")
    parser.add_argument("--thinking-budget", type=int, default=None)
    parser.add_argument("--max-rounds", type=int, default=12)
    args = parser.parse_args()
    def show(event):
        if event["type"] == "content":
            print(event["text"], end="", flush=True)
        elif event["type"] in ("waiting", "tool_start", "tool_end", "error", "cancelled"):
            print("\n[" + event["type"] + "] " + event.get("message", event.get("name", "")), flush=True)
    options = {} if args.thinking_budget is None else {"thinking_budget": args.thinking_budget}
    agent = InteractiveAgent([ADD_TOOL], demo_tool, show, base_url=args.base_url,
                             api_key=os.environ.get("OPENAI_API_KEY"), max_rounds=args.max_rounds,
                             request_options=options)
    messages = [{"role": "system", "content": default_system_prompt()},
                {"role": "user", "content": args.prompt}]
    try:
        agent.run(messages, threading.Event())
    except (AgentError, KeyboardInterrupt):
        return 1
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
