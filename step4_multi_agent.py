# -*- coding: utf-8 -*-
"""
第 4 课：多 Agent 协作（Multi-Agent）Demo
=========================================
演示 agent harness 多智能体的核心模式：
  1. 委派模式（Orchestrator-Workers）—— 主 agent 拆任务派给子 agent
  2. 上下文隔离 —— 子 agent 有独立的 ContextManager，主 agent 只收摘要
  3. 并行执行   —— 相互独立的子任务同时跑，缩短总耗时
  4. 结果聚合   —— 子 agent 返回"摘要结果"，而非全部过程

运行：python3 step4_multi_agent.py
"""

import json
from step2_context_engineering import ContextManager, estimate_tokens

# ---------------------------------------------------------------
# 1. Agent 基类：每个 agent = 编排循环（复用第 1 课）+ 独立上下文
# ---------------------------------------------------------------

class Agent:
    def __init__(self, name: str, system_prompt: str, subagents=None):
        self.name = name
        self.ctx = ContextManager(system_prompt)   # 上下文隔离的关键！
        self.subagents = subagents or {}           # 名字 -> Agent 实例

    def execute(self, task: str) -> str:
        """单 agent 的执行循环（第 1 课的核心循环的简化版）"""
        self.ctx.add("user", task)
        log = [f"[{self.name}] 接到任务: {task}"]

        # 简化：用脚本模拟"LLM 决策"。真实场景由模型决定是否委派
        steps = self.plan(task, log)
        for step in steps:
            log.append(f"[{self.name}] {step}")

        summary = f"{self.name} 完成任务，关键结论: {self.summarize(task)}"
        return summary

    def plan(self, task, log):
        """决策：自己干，还是委派给子 agent？"""
        # 如果这个任务与子 agent 的职责匹配，就委派
        for name, sub in self.subagents.items():
            if name in task:
                log.append(f"发现子任务与 '{name}' 相关 → 委派")
                return [f"委派给 {name}", f"收到 {name} 的摘要结果"]
        return [f"自行处理: 分析任务 → 执行 → 产出结论"]

    def summarize(self, task):
        return f"'{task}' 的 3 条要点摘要（模拟）"

# ---------------------------------------------------------------
# 2. 主编排器：拆解任务 + 并行调度 + 聚合
# ---------------------------------------------------------------

def parallel_run(agents_and_tasks):
    """模拟并行执行：真实 harness 用线程/异步；这里顺序执行但计时间"""
    import time
    t0 = time.time()
    results = {}
    for name, agent, task in agents_and_tasks:
        results[name] = agent.execute(task)
    elapsed = time.time() - t0
    return results, elapsed

def main_orchestrator(top_task: str, subagents: dict):
    print(f"{'='*62}\n[主编排器] 收到顶层任务: {top_task}\n{'-'*62}")

    # 步骤 1: 任务拆解（真实场景由 LLM 规划；这里用规则演示）
    subtasks = {
        "研究组":  "研究组: 调研主流 agent 框架的上下文管理方案",
        "实现组":  "实现组: 按调研结论实现 ContextManager 原型",
    }
    # 步骤 2: 委派（此处两个任务相互独立 → 可并行）
    pairs = [(n, subagents[n], t) for n, t in subtasks.items() if n in subagents]
    print(f"[主编排器] 拆解为 {len(pairs)} 个子任务，相互独立 → 并行委派")
    results, _ = parallel_run(pairs)

    # 步骤 3: 聚合 —— 只收摘要，不收过程（上下文隔离的好处）
    print(f"\n[主编排器] 聚合子 agent 结果:")
    for name, r in results.items():
        print(f"  <- {name}: {r}")

    final = f"综合调研与实现结果，顶层任务 '{top_task}' 已完成。"
    print(f"\n[主编排器] {final}")
    return final

# ---------------------------------------------------------------
# 3. 组装团队并演示
# ---------------------------------------------------------------

def demo():
    # 两个专项子 agent，各有自己的系统提示与独立上下文
    researcher = Agent("研究组", "你是研究员 agent。只做调研，不写代码。输出精炼结论。")
    implementer = Agent("实现组", "你是工程师 agent。只做实现，依赖上游结论。输出交付说明。")

    main_orchestrator("构建一个带上下文压缩的 agent 框架",
                      {"研究组": researcher, "实现组": implementer})

    # 对比：上下文隔离的收益
    print(f"\n{'='*62}\n对比：若不用子 agent，全部过程进入主上下文会怎样？")
    full_process = "调研过程细节 " * 200 + "实现过程细节 " * 200
    print(f"全部过程 ≈ {estimate_tokens(full_process)} tok（会迅速撑爆主上下文）")
    summary = "研究组: 结论摘要 50 tok + 实现组: 交付摘要 50 tok"
    print(f"只收摘要 ≈ {estimate_tokens(summary)} tok（主 agent 保持轻装）")
    print("=> 子 agent 是'消耗 token 的隔离舱'：脏活累活在里面干，主上下文只进结论")

if __name__ == "__main__":
    demo()
