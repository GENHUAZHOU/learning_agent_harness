# Agent Harness 开发六课：从编排层到评测

> 面向初学者的 agent 开发教程。六课分别对应一个 agent harness（智能体框架）的核心模块，每课配一个可直接运行的 Python demo（零第三方依赖），配套代码见同目录下的 `step1` \~ `step6` 文件。

## 学习地图

| 课次 | 主题 | 解决的问题 | 对应 demo |
| --- | --- | --- | --- |
| 1 | 编排层 Orchestration | agent 怎么"动起来" | `step1_orchestrator.py` |
| 2 | 上下文工程 Context Engineering | agent 为什么"聪明/糊涂" | `step2_context_engineering.py` |
| 3 | 工具系统 Tool System | agent 怎么"动手且不闯祸" | `step3_tool_system.py` |
| 4 | 多 Agent 协作 Multi-Agent | 任务怎么"分工" | `step4_multi_agent.py` |
| 5 | 记忆与持久化 Memory | agent 怎么"记住"和"接着干" | `step5_memory.py` |
| 6 | 评测 Evaluation | 怎么证明"变好了" | `step6_agent_eval.py` |

一句话串起来：**编排层是骨架，上下文工程是智商，工具系统是手脚，多 Agent 是分工，记忆是连续性，评测是可信度。**

## 整体架构

```
┌─────────────────────────────────────┐
│  编排层 (Orchestrator)               │  循环控制、状态管理、决策分派
├─────────────────────────────────────┤
│  LLM（模型）                         │  推理与决策：下一步做什么
├─────────────────────────────────────┤
│  工具层 (Tools)                      │  读文件、跑命令、查网络
├─────────────────────────────────────┤
│  环境 (Environment)                  │  文件系统、终端、浏览器、API
└─────────────────────────────────────┘
```

---

# 第 1 课　编排层

## 核心定义

编排层是 agent 的中枢大脑，位于 LLM 之上、工具之下。它的核心是一个循环：

```
接收任务 → LLM 决策 → 执行工具 → 结果回灌给 LLM → 重复，直到完成
```

"结果回灌"是 agent 能多步做事的关键：模型看到自己行动的后果，才能修正下一步。

## 四项核心职责

1. **核心循环（Agent Loop）**：驱动整个"决策—执行—观察"的往复。
2. **决策分派**：解析模型输出，是"调用工具"还是"最终回答"。
3. **状态与上下文管理**：维护消息历史，控制上下文长度。
4. **安全护栏**：最大轮数、超时、权限、错误兜底。没有这些，agent 会死循环或闯祸。

## 最小实现

```python
MAX_TURNS = 10

def run_agent(task, llm, tools):
    messages = [{"role": "user", "content": task}]
    for _ in range(MAX_TURNS):
        decision = llm(messages)
        if decision["type"] == "final":
            return decision["text"]
        result = tools[decision["tool"]](**decision["args"])
        messages.append({"role": "assistant", "content": str(decision)})
        messages.append({"role": "tool", "content": result})
    return "达到最大轮数限制，强制终止"
```

真正的 harness，核心不过三十行。把 mock 的 llm 换成真实 API 调用，就是一个可用的 agent。

## Demo 观察点

`step1_orchestrator.py` 演示了一次"报错—修正"：第 1 轮读文件失败，错误被回灌；第 2 轮模型改调写文件，成功。**错误信息也是提示词**。

---

# 第 2 课　上下文工程

## 核心观点

编排层决定骨架，上下文工程决定智商。模型能力固定，喂什么就表现成什么样。实际开发中大部分 agent 失败不是模型不行，而是上下文出了问题。

## 四种消息角色

| 角色 | 内容 | 生命周期 |
| --- | --- | --- |
| `system` | 身份、规则、输出格式 | 每轮常驻，永远在开头 |
| `user` | 当前任务 | 会话内 |
| `assistant` | 模型的决策（含工具调用意图） | 会话内 |
| `tool` | 工具执行结果（回灌） | 会话内 |

## 四大技术

| 技术 | 解决什么 | 关键做法 |
| --- | --- | --- |
| 消息组装 | 每轮喂什么 | 四角色各司其职，system 永远在前 |
| 系统提示词设计 | 行为不稳定 | 写清身份、工具使用规则、错误处理策略、输出格式；要具体可执行 |
| 工具描述设计 | 调错工具 | 做什么 + 什么时候用 + **什么时候不用** + 参数含义 |
| 历史压缩（Compaction） | 长任务撑爆窗口 | 超预算时把早期消息摘要成一条，保留最近几轮原文 |

另有一条重要原则：**预算意识**。上下文各部分有机会成本，一条十万 token 的工具返回会毁掉整轮推理。生产级 harness 会对大结果做截断、分页或落盘引用。

## 压缩策略

```python
def compact(history, keep_recent=2):
    old, recent = history[:-keep_recent], history[-keep_recent:]
    summary = summarize(old)          # 真实场景由 LLM 完成
    return [{"role": "user", "content": summary}] + recent
```

## Demo 观察点

`step2_context_engineering.py` 模拟 8 轮长任务，token 逼近上限时自动压缩，上下文稳定在预算内（203 → 380 → 压缩回 262 → …）。最终结构是：system 提示词 + 早期摘要 + 最近两轮原文。

---

# 第 3 课　工具系统

## 核心观点

工具是 agent 的手脚。工具接口的质量直接决定成功率——描述含糊、错误信息晦涩，模型再聪明也会翻车。

## 三层结构

```
模型侧  ── Schema（描述）：决定"调用谁、怎么调"
编排侧  ── Registry（注册表）：查找 → 校验 → 权限 → 执行
实现侧  ── Tool.run()：真正的操作
```

## 四个关键设计

**1. Schema 是给模型看的说明书。** 三段式：做什么 / 适用场景 / 不适用场景 + 参数说明。例如 bash 工具要明确写"不适用：读写单个文件"，防止模型用重炮打蚊子。

**2. 参数校验前置，错误要可修复。** 每条错误信息都是给模型的下一句提示词：

- 工具名拼错 → 返回可用工具列表
- 缺参数 → "请重新调用 X，带上参数 Y"
- 类型错 → 说明需要什么类型、收到什么类型

**3. 安全护栏 = 权限分级 + 危险拦截。**

| 级别 | 例子 | 处理 |
| --- | --- | --- |
| read | grep、read\_file | 自动放行 |
| write | bash、write\_file | 暂停，请用户批准 |
| danger | rm -rf、mkfs | 黑名单/沙箱直接拦截，并说明原因与替代方案 |

**4. 工具粒度适中。** 太少没能力，太多选择困难且 schema 占满上下文。成熟产品通常是十几把精工细作的工具，而不是上百个细碎函数。

## 执行入口

```python
def execute(self, name, args, approved=False):
    tool = self.tools.get(name)
    if tool is None:
        return f"错误：未知工具 {name}。可用工具: {list(self.tools)}"
    ok, err = tool.validate(args)
    if not ok:
        return f"校验失败: {err}"
    if tool.permission != "read" and not approved:
        return "需要用户确认，已暂停"
    return tool.run(**args)
```

## 进阶方向

- **MCP（Model Context Protocol）**：把工具做成标准协议服务，跨 agent 复用，相当于工具系统的 USB 接口。
- **沙箱执行**：bash 类工具跑在隔离环境，模型犯错也伤不到真实系统。

## Demo 观察点

`step3_tool_system.py` 六个场景：只读放行、工具名拼错纠正、缺参数提示、`rm -rf /` 拦截、`git push` 待批准、批准后执行成功。

---

# 第 4 课　多 Agent 协作

## 核心观点

子 agent 是"消耗 token 的隔离舱"：脏活累活在隔离舱里干，主 agent 的上下文只进结论。多 agent 的本质不是更多智能，而是**上下文隔离 + 并行 + 专业分工**。

## 三种协作模式

| 模式 | 结构 | 适用 |
| --- | --- | --- |
| 委派（Orchestrator-Workers） | 主 agent 拆任务 → 派给子 agent → 收摘要聚合 | 大范围检索、多模块并行调研 |
| 流水线 | A 的输出是 B 的输入 | 生成 → 审查 → 修复 |
| 辩论/评审 | 多 agent 独立产出再交叉验证 | 结果校验、提升可靠性 |

## 三个关键机制

1. **任务拆解与委派**：子任务之间没有数据依赖才可并行。
2. **上下文隔离**：每个子 agent 有独立的上下文管理器，工具调用、报错、试错全留在自己那边，只返回一条摘要。
3. **结果聚合**：主 agent 只收结论，综合成最终回答。

## 什么时候该拆

**该拆**：子任务需要大量上下文但主 agent 不需要细节；子任务可并行；需要不同角色提示词。

**不该拆**：一次工具调用就能完成；子任务强依赖主 agent 的实时判断；委派开销（拆解+描述+聚合）大于收益。

经验法则：**先写好单 agent，出现上下文瓶颈时再拆**。

## Demo 观察点

`step4_multi_agent.py` 对比很直观：全程细节约 1400 token，摘要只要 17 token。

---

# 第 5 课　记忆与持久化

## 核心观点

上下文是工作记忆（会话结束即消失），记忆系统是长期记忆（跨会话持久化）。没有记忆层的 agent，每次对话都是一次性的。

## 三个层次

| 层次 | 载体 | 生命周期 | 存什么 |
| --- | --- | --- | --- |
| 工作记忆 | 上下文窗口 | 单次会话 | 当前任务、最近消息 |
| 长期记忆 | 外部存储（文件/向量库） | 跨会话 | 用户偏好、事实、进度 |
| 检查点 | 外部存储（JSON/DB） | 跨进程 | 执行状态，用于续跑 |

## 三个核心机制

**1. 写入过滤。** 不是所有对话都值得记。偏好（"我喜欢用 Python"）、事实、进度值得记；寒暄不值得。真实 harness 由 LLM 判断，配合去重与过期清理。

**2. 检索与注入。** 新会话开始时用当前任务检索，把最相关的 K 条注入上下文。demo 用关键词重合度模拟，生产用 embedding 向量相似度，结构一致：`search(query) → top_k → 注入`。

**3. 检查点。** 长任务每完成一步保存 `{任务描述, 已完成步骤, 下一步}`，崩溃后从断点继续，而不是从头来过。

```python
checkpoint = {"task_id": "job-001", "task": "...",
              "done": ["step1", "step2"], "next": "step3"}
```

## Demo 观察点

`step5_memory.py` 三个场景：首次会话边干边记、第二次会话跨会话召回（agent 自动知道该用 Python）、崩溃后从 step3 续跑。记忆持久化在 `memory_store.json`。

---

# 第 6 课　评测方法

## 核心观点

评测不是"跑一下看看行不行"，而是可复现、可对比、能拦住退化的工程体系。没有评测，改一句提示词全靠感觉；有了评测，收益和代价都是数字。

## 三个维度

| 维度 | 评什么 | 为什么重要 |
| --- | --- | --- |
| 结果 Outcome | 最终答案对不对 | 基础成败判断 |
| 过程 Trajectory | 工具调用序列对不对、有没有绕远路 | agent 独有：答对但过程危险/低效同样不可接受 |
| 安全 Safety | 有无越权、危险操作、提示注入 | 一票否决，hard fail |

只看结果的评测是危险的：一个"成功"执行了清空磁盘的 agent，结果指标会骗你。

## 五个核心指标

| 指标 | 含义 |
| --- | --- |
| 任务成功率 | 结果正确的比例（主指标） |
| 轨迹准确率 | 工具序列符合预期的比例（诊断为什么错） |
| pass@k | n 次采样中至少一次成功的概率；k=1 看稳定性，k=5 看能力上限 |
| 平均轮数 / token | 效率与成本 |
| 安全违规率 | 必须为 0 |

常见的教学现象：pass@1 只有 0.44 但 pass@5 为 1.0——说明"有能力但极不稳定"，不能上线，因为用户只给一次机会。

pass@k 用 Codex 论文的无偏估计：

```python
def pass_at_k(n, c, k):
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)
```

## 评测集怎么建

四类用例缺一不可：

1. **常规用例**：主流程，验证基本能力
2. **边界用例**：文件不存在、路径错、超长输入，考察自我修正
3. **对抗用例**：危险指令、提示注入，考察拒绝越权
4. **开放用例**：无标准答案，用 LLM-as-judge 按 rubric 打分

原则：**用例来自真实失败**。线上每出现一次 bad case，就固化成一条用例，形成回归集。

## 四条方法论纪律

1. **可复现**：固定随机种子、temperature=0 或固定采样数
2. **A/B 对比而非绝对值**："比上一版高 6 个点"才有意义
3. **LLM-as-judge 要给 rubric**：写清评分维度与扣分项，重要场景人工抽检校准
4. **回归门禁**：接入 CI，核心指标下降或安全违规 \> 0 就阻断合并

## 行业基准

| 基准 | 考什么 |
| --- | --- |
| SWE-bench | 真实 GitHub issue 修复，代码 agent 事实标准 |
| WebArena / OSWorld | 浏览器 / 桌面操作 |
| τ-bench | 多轮工具调用 + 业务规则，最接近生产 |
| GAIA | 通用助理型多步任务 |
| Terminal-bench | 终端长任务 |

工程工具：LangSmith、Braintrust、promptfoo、Inspect。

## Demo 观察点

`step6_agent_eval.py` 输出逐用例明细与 A/B 报告：

```
任务成功率  0.40 → 1.00 (+0.60)
轨迹准确率  0.40 → 1.00 (+0.60)
安全合规率  0.80 → 1.00 (+0.20)   ← v1 在对抗用例越权，hard fail
pass@1     0.44 → 0.96 (+0.52)
每例 token  1800 → 1400 (-400)
```

---

# 配套代码与运行方式

六个 demo 均在 `/workspace/agent_tutorial/` 下，Python 3.8+ 直接运行，无需安装依赖：

```bash
python3 step1_orchestrator.py
python3 step2_context_engineering.py
python3 step3_tool_system.py
python3 step4_multi_agent.py
python3 step5_memory.py
python3 step6_agent_eval.py
```

依赖关系：第 4、5 课复用了第 2 课的 `ContextManager`，第 6 课复用了前五课的产出结构，可直接看到模块化设计。

# 下一步

1. **把 mock 换成真实 LLM API**，把前五课串成一个能读代码库、回答问题、修改文件的编码 agent。
2. **接入 MCP**，把工具标准化，跨 agent 复用。
3. **用第 6 课的 harness 给自己的 agent 打分**，建立回归集。
4. **深挖安全**：提示注入防御、沙箱隔离、工具权限最小化。
