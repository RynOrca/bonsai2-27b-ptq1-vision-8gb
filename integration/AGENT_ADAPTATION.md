# 自建 Agent 接入

`interactive_agent.py` 是 Python 标准库实现的 OpenAI Chat Completions SSE 示例，无额外依赖，不执行 shell。默认直连 `http://127.0.0.1:18200/v1`，模型名为 `qwen3.8-27b-long`；若启动器使用其他端口，通过 `base_url` 或 `--base-url` 指定。

默认请求包含 `max_completion_tokens=16384`、`reasoning_effort="medium"`、`preserve_thinking=true`，不发送固定 `thinking_budget`。思考深度由任务决定，阶段汇报依据实际动作、工具结果和新证据，不能为了进度打断必要推理。若调用方主动需要思考预算，可以显式传 `request_options={"thinking_budget": 768}` 或 CLI 的 `--thinking-budget 768`。

这份适配器提供客户端循环与交互机制，不替代引擎 KV 修复，也不保证任意输入、任意资源状态都能输出满16K或任务质量改善。

## 接入已有 Agent

```python
import threading
from interactive_agent import InteractiveAgent, default_system_prompt

agent = InteractiveAgent(
    tools=your_openai_tool_schemas,
    execute_tool=execute_tool,  # (name, arguments_dict, call_id) -> str 或 JSON可序列化值
    on_event=on_event,          # 收到单个事件 dict
    base_url="http://127.0.0.1:18200/v1",
    api_key=None,              # 若服务需要鉴权，从业务配置安全传入
)
messages = [
    {"role": "system", "content": default_system_prompt()},
    {"role": "user", "content": "用户任务"},
]
cancel = threading.Event()
agent.run(messages, cancel=cancel)
```

在仓库根目录调用时，先将 `integration` 加到应用的 Python 导入路径，或从该目录导入。系统提示词读取同目录 `interactive-agent-system-prompt.md` 配套设置之前的指令。已有系统提示词可在会话初始化时合并一次，遵守调用方 JSON、结构化输出和工具协议。建议允许阶段汇报时每次不超过100字；示例不会强制裁剪正文或改写输出格式。

`run` 原地追加历史。后续用户输入继续追加同一个 `messages` 列表，保留完整正文、`reasoning_content`、工具调用参数原始字符串、`tool_call_id` 和工具结果。不要每轮重写 system、摘要、顺序或清理思考字段。保留完整历史有助于避免重想，不能保证模型从不重复。

`reasoning_content` 仅用于服务端重建历史，不发送给 UI；它属于内部敏感状态，业务日志也不应记录其原文。其他部署或模板可能有不同合同，迁移时核实支持的历史字段。

## 模板选项与跨请求复用

复用要求本轮序列化的 token 前缀与已保存检查点相匹配，同时检查点及所需资源仍可用。保留历史字段是重要条件，但不是充分条件。

本次验证使用的 `qwen3_8.jinja` 对 assistant 的保留条件为：

```jinja
not continuing and (preserve_thinking is undefined or preserve_thinking is true or loop.index0 > ns.last_query_index)
```

因此，在追加新 user 后，位于该 user 之前的历史 assistant：省略选项和显式 `true` 均保留思考块，显式 `false` 会去掉；位于最后 user 之后的工具循环 assistant 可由最后一个条件保留。它并非只影响最后一条 assistant。默认显式设为 true 表达保留意图，不能将“省略→true”宣传为已证明的性能修复。

建议从首轮起保持 system、工具清单及顺序、模板选项稳定。工具清单变化可能改写已有前缀并触发大量重新预填充；具体后果取决于模板、历史形态和可用检查点，并非任何变化都必然零命中。适配器复制工具清单并在内部续轮复用；调用方也应避免后续手动改动 `agent.tools` 或 `agent.options`。

## 已验证的性能边界

以下是2026-10-11在 RTX 4060 Laptop 8 GiB、单并发、Device KV 16000、Host KV 8 GiB 上的样本结果。均直连后端，不经过路由器；没有固定思考预算。TTFT 指首个生成 token，可能先是内部思考，并不等于用户看到正文的时间。

真实约35K输入、首轮实际生成16384 token，随后追加短 user 并请求512 token：

| 历史回传方式 | preserve_thinking | 次轮输入 | 命中 | 实算预填充 | TTFT |
|---|---|---:|---:|---:|---:|
| 人为丢弃思考字段 | 省略 | 51459 | 35139 | 16320 | 66.02秒 |
| 完整回传思考字段 | 省略 | 51551 | 51527 | 24 | 0.82秒 |
| 完整回传思考字段 | true | 51551 | 51527 | 24 | 0.84秒 |

后两组相同，证明该实验中省略选项与 true 等效。第一组不是现适配器的原始行为基线；适配器在这次显式选项调整之前已回传思考字段。三组自写传输对照验证历史机制，另有真实 `InteractiveAgent.run` 的长链和工具循环验收。

实际长链样本两轮都请求16384，首轮输入35144、实际输出16384；次轮输入51551、实际输出15371后自然停止，命中51527、实算24、TTFT 0.82秒，decode约44.3 token/s（首轮约53.9 token/s）。另外的诊断构建样本两轮都生成满16384，次轮命中51527/51550、实算23、TTFT 0.81秒、decode约52.0 token/s。后者不是对发布引擎更换的要求；这些数字展示个案，不构成持续速度或任意16K输出保证。

对照中保留完整历史的计数样本成功续接，另有中段标记检索及工具执行样本；它们只证明相应任务表现。删除思考字段同时改变了模型输入，不能将质量差异单独归因为缓存复用，固定采样参数也不能消除这种混杂。

未覆盖多并发、多会话压力、Host接近满额、长时间稳定性，以及所有视觉／工具／上下文组合。工具清单固定只是一项提高复用稳定性的建议。

## UI、终态与取消

`on_event` 收到 `content` 时立即展示 `text`；`waiting` 显示真实“等待服务端／可能冷预填充”，不能伪造进度。还包括 `heartbeat`、`usage`、`finish`、`tool_start`、`tool_end`、`no_progress`、`error`、`cancelled`。工具事件不含结果原文，业务可安全展示可观察结果。回调同步执行，应保持简短。

- `stop`：本轮自然结束，返回业务层，由业务任务状态决定后续交互。
- `tool_calls`：积累完整 JSON 参数，校验整个批次并收到 `[DONE]` 后才执行。工具结果按调用ID写回历史，再请求下一轮。工具清单外名称拒绝执行，执行器仍须校验权限及业务参数。
- `length`：保留已生成内容及调用，报错停止，不执行尚未完成的工具，不自动发送“继续”。
- SSE error、网络错误、缺少终态或 `[DONE]`：保留部分历史并停止，客户端不自动重试。
- `max_rounds`：到最后允许轮仍要求工具时，在执行前停止，避免做了操作却无下一轮汇报机会。
- `no_progress`：连续3轮的工具调用批次（相同顺序、名称及规范化参数）与结果字符串完全相同，保留第3次结果并停止。新结果重置计数。可用 `no_progress_limit=5` 调整或 `None` 禁用；它不能识别所有语义循环，仍保留轮数兜底。

真实工具应使用“会话ID + tool_call_id”建立持久化幂等记录，保存开始、完成及结果。示例不替代权限系统或幂等存储；失败后不要盲目重跑整个循环，应依记录恢复对应工具结果。

调用 `cancel.set()` 合作取消。适配器在读取前后、心跳边界及工具执行紧前检查并关闭响应；同步 urllib 在阻塞读取期间不能保证立即取消，已开始的工具也不会被强制中断。生产应用可替换为可取消异步传输，并为工具实现合作取消。

本示例直连后端，不依赖路由器恢复机制。若业务另加恢复层，应严格限定错误和输出前边界，正文开始后不得自动重发，以免重复工具副作用。

## 演示与离线验证

仓库根目录运行（会实际调用已启动的模型，仅提供命令）：

```powershell
python integration/interactive_agent.py "请用 add 工具计算 2+3，并简短汇报"
```

演示仅提供本地数值加法，没有自动 shell 执行。可选 API key 读取 `OPENAI_API_KEY` 环境变量，不硬编码密钥。

离线验证不请求网络或 GPU：

```powershell
python -m unittest discover -s tests -p test_interactive_agent.py -v
python -m py_compile integration/interactive_agent.py tests/test_interactive_agent.py
```

测试覆盖实际第二次发送请求中的完整 reasoning、工具参数和结果回传、默认 preserve_thinking、正文事件、流不完整／length／error 后不执行工具不重试、取消、轮数上限及无进展守卫；不将离线测试称为模型质量测试。
