import io
import importlib.util
import json
from pathlib import Path
import threading
import unittest

MODULE = Path(__file__).resolve().parents[1] / "integration" / "interactive_agent.py"
spec = importlib.util.spec_from_file_location("interactive_agent", MODULE)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def chunk(delta=None, finish=None):
    return {"choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}]}


def sse(*chunks):
    return b"".join(("data: " + json.dumps(value) + "\n\n").encode() for value in chunks) + b"data: [DONE]\n\n"


class Network:
    def __init__(self, *responses):
        self.responses, self.requests = list(responses), []

    def __call__(self, request, timeout):
        self.requests.append(json.loads(request.data))
        return io.BytesIO(self.responses.pop(0))


def tool_fragment(arguments, first=False, name="add"):
    call = {"index": 0, "function": {"arguments": arguments}}
    if first:
        call.update(id="call_1", type="function")
        call["function"]["name"] = name
    return chunk({"tool_calls": [call]})


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.messages = [{"role": "system", "content": "固定前缀"}, {"role": "user", "content": "test"}]
        self.events, self.executed = [], []

    def agent(self, network, **kw):
        def execute(name, args, call_id):
            self.executed.append((name, args, call_id))
            return adapter.demo_tool(name, args, call_id)
        return adapter.InteractiveAgent([adapter.ADD_TOOL], execute, self.events.append,
                                        opener=network, **kw)

    def test_content_usage_reasoning_private(self):
        net = Network(sse(chunk({"reasoning_content": "private thought"}),
                          chunk({"content": "开始"}), chunk({"content": "完成"}, "stop"),
                          {"choices": [], "usage": {"completion_tokens": 10}}))
        self.agent(net).run(self.messages)
        self.assertEqual(self.messages[-1]["content"], "开始完成")
        self.assertEqual(self.messages[-1]["reasoning_content"], "private thought")
        self.assertNotIn("private thought", json.dumps(self.events))
        self.assertTrue(any(e["type"] == "usage" for e in self.events))
        self.assertNotIn("thinking_budget", net.requests[0])
        self.assertIs(net.requests[0]["preserve_thinking"], True)
        self.assertEqual(net.requests[0]["max_completion_tokens"], 16384)
        self.assertEqual(net.requests[0]["stream_options"], {"include_usage": True})

    def test_fragmented_tool_and_continuation(self):
        net = Network(sse(chunk({"reasoning_content": "first complete\n"}),
                          chunk({"reasoning_content": "reasoning"}),
                          chunk({"content": "计算中"}), tool_fragment('{"a":', True),
                          tool_fragment('2,"b":3}'), chunk(finish="tool_calls")),
                      sse(chunk({"content": "结果是5"}, "stop")))
        agent = self.agent(net)
        original = list(self.messages)
        agent.run(self.messages)
        self.assertEqual(self.executed, [("add", {"a": 2, "b": 3}, "call_1")])
        second = net.requests[1]["messages"]
        self.assertEqual(second[:2], original)
        self.assertEqual(second[2]["content"], "计算中")
        self.assertEqual(second[2]["reasoning_content"], "first complete\nreasoning")
        self.assertEqual(second[2]["tool_calls"][0]["function"]["arguments"], '{"a":2,"b":3}')
        self.assertTrue(all(request["preserve_thinking"] is True for request in net.requests))
        self.assertNotIn("first complete", json.dumps(self.events))
        self.assertEqual(second[3], {"role": "tool", "tool_call_id": "call_1", "content": '{"sum": 5}'})
        event_types = [e["type"] for e in self.events]
        self.assertLess(event_types.index("finish"), event_types.index("tool_start"))

    def test_no_terminal_no_execution(self):
        net = Network(sse(tool_fragment('{"a":2,"b":3}', True)))
        with self.assertRaises(adapter.AgentError):
            self.agent(net).run(self.messages)
        self.assertFalse(self.executed)
        self.assertEqual(len(net.requests), 1)
        self.assertIn("tool_calls", self.messages[-1])

    def test_unknown_tool_rejected(self):
        net = Network(sse(tool_fragment('{}', True, "shell"), chunk(finish="tool_calls")))
        with self.assertRaisesRegex(adapter.AgentError, "unknown"):
            self.agent(net).run(self.messages)
        self.assertFalse(self.executed)

    def test_tool_terminal_without_done_no_execution(self):
        response = sse(tool_fragment('{"a":2,"b":3}', True), chunk(finish="tool_calls"))
        net = Network(response.replace(b"data: [DONE]\n\n", b""))
        with self.assertRaisesRegex(adapter.AgentError, "missing \\[DONE\\]"):
            self.agent(net).run(self.messages)
        self.assertFalse(self.executed)
        self.assertEqual(len(net.requests), 1)
        self.assertIn("tool_calls", self.messages[-1])

    def test_tool_start_callback_cancel_no_execution(self):
        cancel = threading.Event()
        net = Network(sse(tool_fragment('{"a":2,"b":3}', True), chunk(finish="tool_calls")))
        agent = self.agent(net)
        def event(value):
            self.events.append(value)
            if value["type"] == "tool_start":
                cancel.set()
        agent.on_event = event
        with self.assertRaises(adapter.Cancelled):
            agent.run(self.messages, cancel)
        self.assertFalse(self.executed)
        self.assertEqual(self.events[-1]["type"], "cancelled")

    def test_length_no_execution_no_retry(self):
        net = Network(sse(chunk({"content": "partial"}), tool_fragment('{}', True), chunk(finish="length")))
        with self.assertRaisesRegex(adapter.AgentError, "length"):
            self.agent(net).run(self.messages)
        self.assertEqual(self.messages[-1]["content"], "partial")
        self.assertFalse(self.executed)
        self.assertEqual(len(net.requests), 1)

    def test_error_after_partial_no_retry(self):
        net = Network(sse(chunk({"content": "partial"}), {"error": {"message": "private diagnostic"}}))
        with self.assertRaises(adapter.AgentError):
            self.agent(net).run(self.messages)
        self.assertEqual(self.messages[-1]["content"], "partial")
        self.assertEqual(len(net.requests), 1)
        self.assertNotIn("private diagnostic", json.dumps(self.events))

    def test_cancel_before_request(self):
        cancel = threading.Event()
        cancel.set()
        net = Network()
        with self.assertRaises(adapter.Cancelled):
            self.agent(net).run(self.messages, cancel)
        self.assertFalse(net.requests)

    def test_cancel_at_heartbeat_preserves_partial(self):
        cancel = threading.Event()
        net = Network(sse(chunk({"content": "partial"})).replace(b"data: [DONE]\n\n", b": heartbeat\n\n"))
        agent = self.agent(net)
        def event(value):
            self.events.append(value)
            if value["type"] == "heartbeat":
                cancel.set()
        agent.on_event = event
        with self.assertRaises(adapter.Cancelled):
            agent.run(self.messages, cancel)
        self.assertEqual(self.messages[-1]["content"], "partial")

    def test_max_rounds_before_side_effect(self):
        net = Network(sse(tool_fragment('{"a":2,"b":3}', True), chunk(finish="tool_calls")))
        with self.assertRaisesRegex(adapter.AgentError, "max_rounds"):
            self.agent(net, max_rounds=1).run(self.messages)
        self.assertFalse(self.executed)

    def test_explicit_budget_override(self):
        net = Network(sse(chunk({"content": "ok"}, "stop")))
        self.agent(net, request_options={"thinking_budget": 512}).run(self.messages)
        self.assertEqual(net.requests[0]["thinking_budget"], 512)

    def test_identical_tool_rounds_stop_after_three(self):
        rounds = [sse(tool_fragment('{"a":2,"b":3}' if i % 2 == 0 else '{"b":3,"a":2}', True),
                      chunk(finish="tool_calls")) for i in range(3)]
        net = Network(*rounds)
        with self.assertRaisesRegex(adapter.AgentError, "no_progress"):
            self.agent(net).run(self.messages)
        self.assertEqual(len(self.executed), 3)
        self.assertEqual(len(net.requests), 3)
        self.assertEqual(self.messages[-1]["role"], "tool")
        self.assertTrue(any(e["type"] == "no_progress" for e in self.events))

    def test_polling_with_new_results_does_not_trigger_guard(self):
        rounds = [sse(tool_fragment('{"a":2,"b":3}', True), chunk(finish="tool_calls")) for _ in range(4)]
        net = Network(*rounds, sse(chunk({"content": "done"}, "stop")))
        agent = self.agent(net)
        counter = iter(range(4))
        agent.execute_tool = lambda name, args, call_id: {"state": next(counter)}
        agent.run(self.messages)
        self.assertEqual(len(net.requests), 5)
        self.assertFalse(any(e["type"] == "no_progress" for e in self.events))

    def test_no_progress_guard_can_be_disabled(self):
        rounds = [sse(tool_fragment('{"a":2,"b":3}', True), chunk(finish="tool_calls")) for _ in range(3)]
        net = Network(*rounds, sse(chunk({"content": "done"}, "stop")))
        self.agent(net, no_progress_limit=None).run(self.messages)
        self.assertEqual(len(net.requests), 4)
        self.assertFalse(any(e["type"] == "no_progress" for e in self.events))


if __name__ == "__main__":
    unittest.main()
