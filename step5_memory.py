# -*- coding: utf-8 -*-
"""
第 5 课：记忆系统（Memory）与状态持久化 Demo
============================================
演示 agent harness 记忆层的核心技术：
  1. 工作记忆 vs 长期记忆 —— 会话内上下文 vs 跨会话持久化
  2. 记忆写入 —— 判断什么值得记（用户偏好/事实/进度）
  3. 记忆检索 —— 按关键词匹配召回相关记忆，注入当前上下文
  4. 检查点（Checkpoint）—— 保存执行状态，崩溃后断点续跑

运行：python3 step5_memory.py
"""

import json, os, time
from pathlib import Path

MEMORY_FILE = str(Path(__file__).resolve().parent / "memory_store.json")
CKPT_FILE = str(Path(__file__).resolve().parent / "checkpoint.json")

# ---------------------------------------------------------------
# 1. 记忆存储：每条记忆 = 内容 + 标签 + 时间戳
# ---------------------------------------------------------------

class MemoryStore:
    def __init__(self, path):
        self.path = path
        self.memories = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.memories = json.load(f)

    def write(self, text: str, tags: list):
        """写入长期记忆。真实 harness 会用 LLM 判断'是否值得记'，
        并提取结构化内容；这里演示判断规则。"""
        self.memories.append({"text": text, "tags": tags, "ts": time.time()})
        self._save()
        return f"已记住: {text[:40]}"

    def search(self, query: str, top_k: int = 2):
        """检索：真实系统用向量相似度（embedding）；
        这里用关键词重合度模拟，原理相同——召回最相关的 K 条"""
        scored = []
        q_words = set(query)  # 中文字符级匹配，简化
        for m in self.memories:
            overlap = len(q_words & set(m["text"] + "".join(m["tags"])))
            if overlap > 0:
                scored.append((overlap, m))
        scored.sort(key=lambda x: -x[0])
        return [m for _, m in scored[:top_k]]

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.memories, f, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------
# 2. 值得记吗？—— 记忆写入的过滤规则（真实场景由 LLM 判断）
# ---------------------------------------------------------------

WORTHY_RULES = [
    ("偏好",  lambda t: "喜欢" in t or "偏好" in t or "习惯" in t),
    ("事实",  lambda t: "是" in t and len(t) > 10),
    ("进度",  lambda t: "完成" in t or "待办" in t),
]

def should_remember(text: str):
    for tag, rule in WORTHY_RULES:
        if rule(text):
            return tag
    return None  # 闲聊寒暄不值得长期记忆

# ---------------------------------------------------------------
# 3. 检查点（Checkpoint）：断点续跑的核心
#    保存 = 任务描述 + 已完成步骤 + 中间产物路径
# ---------------------------------------------------------------

class Checkpoint:
    def __init__(self, path):
        self.path = path

    def save(self, task_id, task, done_steps, next_step):
        state = {"task_id": task_id, "task": task,
                 "done": done_steps, "next": next_step}
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return f"检查点已保存（已完成 {len(done_steps)} 步）"

    def resume(self, task_id):
        if not os.path.exists(self.path):
            return None
        with open(self.path, "r", encoding="utf-8") as f:
            s = json.load(f)
        return s if s["task_id"] == task_id else None

# ---------------------------------------------------------------
# 4. 带记忆的 Agent：会话开始先检索记忆，结束前写入新记忆
# ---------------------------------------------------------------

def demo():
    store = MemoryStore(MEMORY_FILE)
    ckpt = Checkpoint(CKPT_FILE)

    print("== 场景 1: 第 1 次会话（记忆为空，边干活边记）==")
    user_says = [
        "我喜欢用 Python 写 agent，别推荐别的语言",     # 偏好 -> 记
        "今天的待办：写完记忆系统 demo",                 # 进度 -> 记
        "你好呀，今天天气怎么样？",                       # 寒暄 -> 不记
    ]
    for text in user_says:
        tag = should_remember(text)
        if tag:
            store.write(text, [tag])
            print(f"  用户: {text}\n  -> 判定[{tag}]，写入长期记忆")
        else:
            print(f"  用户: {text}\n  -> 不值得长期记忆，仅留在工作记忆（本次会话）")

    print("\n== 场景 2: 第 2 次会话（跨会话记忆召回）==")
    query = "帮我写个脚本，用我喜欢的语言"
    recalled = store.search(query)
    print(f"  用户: {query}")
    print(f"  检索到 {len(recalled)} 条相关记忆，注入系统上下文：")
    for m in recalled:
        print(f"    * [{','.join(m['tags'])}] {m['text']}")
    print("  -> agent 因此知道该用 Python（不需要用户重复说明）")

    print("\n== 场景 3: 检查点与断点续跑 ==")
    # 模拟长任务中途崩溃
    ckpt.save("job-001", "重构 agent_tutorial 全部 demo",
              ["step1 重构完成", "step2 重构完成"], "step3 重构")
    print("  [任务执行中] 检查点已保存（已完成 2 步）")
    print("  ...进程崩溃，重启后...")
    state = ckpt.resume("job-001")
    if state:
        print(f"  恢复任务: {state['task']}")
        print(f"  已完成: {state['done']}")
        print(f"  从下一步继续: {state['next']}")

    print(f"\n长期记忆已持久化到: {MEMORY_FILE}（跨进程可读）")

if __name__ == "__main__":
    demo()
