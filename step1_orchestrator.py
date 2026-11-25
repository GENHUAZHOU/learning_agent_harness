# -*- coding: utf-8 -*-
"""
最小 Agent 编排层 Demo（Step 1）
================================
只做一件事：实现 Agent Harness 的核心循环
    接收任务 -> LLM 决策 -> 执行工具 -> 把结果喂回 LLM -> 直到完成

依赖：无需任何第三方库。LLM 调用处用 mock 模拟，方便你先理解结构。
理解本文件后，你只需要把 `fake_llm` 换成真实的 API 调用（如 Claude/GPT），
一个真正的 agent 就诞生了。

运行：python3 step1_orchestrator.py
"""

import json

# ---------------------------------------------------------------
# 1. 工具（Tools）：agent 能"动手"的能力
#    每个工具 = 名字 + 描述（给 LLM 看）+ 函数（真正执行）
# ---------------------------------------------------------------

def tool_read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"错误: {e}"

def tool_write_file(path: str, content: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"已写入 {path}，{len(content)} 字符"

TOOLS = {
    "read_file": {
        "description": "读取指定路径的文件内容",
        "params": ["path"],
        "func": tool_read_file,
    },
    "write_file": {
        "description": "把内容写入指定路径的文件",
        "params": ["path", "content"],
        "func": tool_write_file,
    },
}

# ---------------------------------------------------------------
# 2. LLM 调用（这里用脚本 mock，演示"决策"长什么样）
#    真实场景：把 messages + 工具描述发给模型，模型返回
#    要么是「调用某工具」，要么是「最终回答」
# ---------------------------------------------------------------

def fake_llm(messages):
    """根据对话进度返回预设决策，模拟模型行为。"""
    # 数一下对话轮数，模拟"第一步调工具、第二步给答案"
    tool_results = [m for m in messages if m["role"] == "tool"]
    if not tool_results:
        # 决策 1：我需要先看看当前目录有什么
        return {
            "type": "tool_call",
            "tool": "read_file",
            "args": {"path": "/workspace/agent_tutorial/notes.txt"},
        }
    if len(tool_results) == 1:
        # 决策 2：看到了文件内容（可能是错误），写入笔记
        prev = tool_results[0]["content"]
        return {
            "type": "tool_call",
            "tool": "write_file",
            "args": {"path": "/workspace/agent_tutorial/notes.txt",
                     "content": "第1课：编排层 = 循环 + 决策 + 工具执行 + 结果回灌"},
        }
    # 决策 3：信息够了，输出最终答案
    return {"type": "final", "text": "已完成：笔记已写入 notes.txt"}

# ---------------------------------------------------------------
# 3. 编排层（Orchestrator）：核心循环，agent harness 的心脏
# ---------------------------------------------------------------

MAX_TURNS = 10  # 保护机制：防止无限循环（真实 harness 必须有）

def run_agent(task: str):
    print(f"[任务] {task}\n{'-'*50}")
    messages = [{"role": "user", "content": task}]

    for turn in range(1, MAX_TURNS + 1):
        print(f"\n===== 第 {turn} 轮 =====")

        # 3.1 让 LLM 决策
        decision = fake_llm(messages)

        # 3.2 分派决策
        if decision["type"] == "final":
            print(f"[编排层] 收到最终回答，结束循环")
            return decision["text"]

        if decision["type"] == "tool_call":
            name, args = decision["tool"], decision["args"]
            tool = TOOLS.get(name)
            if tool is None:
                result = f"错误：未知工具 {name}"
            else:
                print(f"[编排层] 调用工具 {name} 参数: {json.dumps(args, ensure_ascii=False)}")
                result = tool["func"](**args)

            # 3.3 结果回灌 —— 这是 agent 能"多步推理"的关键！
            print(f"[编排层] 工具结果: {result}")
            messages.append({"role": "assistant", "content": json.dumps(decision, ensure_ascii=False)})
            messages.append({"role": "tool", "content": result})

    return "达到最大轮数限制，强制终止"

# ---------------------------------------------------------------
# 4. 入口
# ---------------------------------------------------------------

if __name__ == "__main__":
    answer = run_agent("请把今天的学习笔记写入 notes.txt")
    print(f"\n{'='*50}\n[最终回答] {answer}")
