# -*- coding: utf-8 -*-
"""
第 2 课：上下文工程（Context Engineering）Demo
=============================================
演示 agent harness 中上下文管理的三个核心技术：
  1. 消息组装   —— 每轮该把哪些内容放进上下文
  2. 上下文预算 —— token 预算分配（系统提示 / 历史 / 工具结果）
  3. 历史压缩   —— 旧消息太长时做"摘要+保留近况"（compaction）

运行：python3 step2_context_engineering.py
"""

import json

# ---------------------------------------------------------------
# 1. 消息组装：一条消息 = 角色 + 内容， roles 有约定
#    system   : 系统提示词（每轮都在，定义"你是谁、规则是什么"）
#    user     : 用户的任务
#    assistant: 模型自己的决策（含工具调用意图）
#    tool     : 工具执行结果（回灌给模型）
# ---------------------------------------------------------------

# ---------------------------------------------------------------
# 2. 上下文预算：模拟 token 计数与分配
# ---------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """粗糙估算：中文约 1.5 字符/token，这里简化为 len()"""
    return max(1, len(text) // 2)

MAX_CONTEXT_TOKENS = 500   # 模拟一个很小的上下文窗口，方便演示压缩

class ContextManager:
    """上下文管理器：agent harness 的核心组件之一"""

    def __init__(self, system_prompt: str):
        self.system_prompt = system_prompt
        self.history = []          # (role, content) 列表
        self.compressions = 0      # 压缩次数统计

    def add(self, role: str, content: str):
        self.history.append({"role": role, "content": content})

    def total_tokens(self) -> int:
        return (estimate_tokens(self.system_prompt)
                + sum(estimate_tokens(m["content"]) for m in self.history))

    # ---- 核心技术：历史压缩（compaction）----
    def compact(self, keep_recent: int = 2):
        """
        策略：把较早的消息摘要成一条，只保留最近 keep_recent 条原文。
        真实 harness 中，"摘要"由 LLM 完成；这里用规则模拟。
        """
        if len(self.history) <= keep_recent:
            return False

        old = self.history[:-keep_recent]
        recent = self.history[-keep_recent:]

        # 生成摘要（真实场景：调 LLM 总结这些消息）
        summary_parts = []
        for m in old:
            prefix = {"assistant": "[决策]", "tool": "[结果]", "user": "[任务]"}[m["role"]]
            summary_parts.append(f"{prefix}{m['content'][:20]}")
        summary = f"<早期对话摘要 共{len(old)}条> " + " | ".join(summary_parts)

        self.history = [{"role": "user", "content": summary}] + recent
        self.compressions += 1
        return True

    def build_messages(self) -> list:
        """
        组装本轮要发给 LLM 的完整上下文：
        system 提示词永远在开头 + （必要时压缩后的）历史
        """
        # 预算检查：超了就压缩
        while self.total_tokens() > MAX_CONTEXT_TOKENS:
            if not self.compact():
                break  # 已无法再压缩
        return [{"role": "system", "content": self.system_prompt}] + self.history

# ---------------------------------------------------------------
# 3. 工具描述设计：描述写得差，模型就不会用/用错
# ---------------------------------------------------------------

TOOL_SCHEMAS = {
    "search_web": {
        # 好的描述 = 做什么 + 什么时候用 + 什么时候不用 + 参数说明
        "description": (
            "搜索互联网获取实时信息。"
            "适用：需要最新数据、事实核查、超出你训练时间的信息。"
            "不适用：代码库内的本地搜索（改用 grep）。"
            "参数 query：具体的关键词组合，避免整句提问。"
        ),
        "params": ["query"],
    },
}

# ---------------------------------------------------------------
# 4. 演示：模拟一段超长的 agent 执行过程，观察压缩触发
# ---------------------------------------------------------------

def demo():
    system_prompt = (
        "你是一个文件助手 agent。规则：1) 先读再写 2) "
        "每次只调用一个工具 3) 任务完成后简短汇报。"
    )
    cm = ContextManager(system_prompt)
    print(f"系统提示词: {system_prompt}\n{'-'*60}")

    # 模拟 agent 执行 8 轮，每轮产生较长的工具结果
    for turn in range(1, 9):
        cm.add("assistant", f"第{turn}轮决策：调用工具 list_files 查看目录 第{turn}区内容")
        tool_result = f"工具返回：目录下有 {turn*37} 个文件，详细列表 " + "file_%d.md " % turn * 30
        cm.add("tool", tool_result)

        msgs = cm.build_messages()   # 组装上下文（内部自动做预算检查）
        print(f"轮次{turn} | 历史{len(cm.history)}条 | "
              f"上下文{cm.total_tokens()} tok | 压缩{cm.compressions}次")

    print(f"\n{'-'*60}\n压缩后的上下文内容：")
    for m in cm.build_messages():
        print(f"  [{m['role']:>9}] {m['content'][:80]}")

if __name__ == "__main__":
    demo()
