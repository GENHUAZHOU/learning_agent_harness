# -*- coding: utf-8 -*-
"""
第 3 课：工具系统（Tool System）Demo
====================================
演示 agent harness 工具层的四个核心设计：
  1. 工具 Schema 定义 —— 让模型"看得懂"每个工具
  2. 参数校验         —— 在执行前拦截错误，并返回"可修复"的错误信息
  3. 安全护栏         —— 权限分级 + 危险命令拦截（agent 不会闯祸的关键）
  4. 错误信息设计     —— 好的错误信息能引导模型自我修正

运行：python3 step3_tool_system.py
"""

import json, re

# ---------------------------------------------------------------
# 1. 工具基类：Schema + 校验 + 执行 三合一
# ---------------------------------------------------------------

class Tool:
    name = ""
    description = ""          # 给模型看的说明
    permission = "read"       # 权限级别: read(自动放行) / write(需确认) / danger(默认拒绝)
    params_spec = {}          # 参数名 -> (类型, 是否必填, 说明)

    def validate(self, args: dict):
        """参数校验：返回 (是否通过, 错误提示)。错误提示要'教模型怎么改'"""
        # 检查必填
        for p, (ptype, required, desc) in self.params_spec.items():
            if required and p not in args:
                return False, (f"缺少必填参数 '{p}'（{desc}）。"
                               f"请重新调用 {self.name}，带上参数 {p}。"
                               f"该工具完整参数: {json.dumps(list(self.params_spec))}")
            if p in args and not isinstance(args[p], ptype):
                return False, (f"参数 '{p}' 类型错误：需要 {ptype.__name__}，"
                               f"收到 {type(args[p]).__name__}。请修正后重试。")
        # 检查未知参数
        extra = set(args) - set(self.params_spec)
        if extra:
            return False, (f"发现未知参数 {sorted(extra)}，"
                           f"有效参数仅有 {list(self.params_spec)}。")
        return True, None

    def run(self, **kwargs):
        raise NotImplementedError

# ---------------------------------------------------------------
# 2. 具体工具实现
# ---------------------------------------------------------------

class BashTool(Tool):
    name = "bash"
    description = ("在终端执行命令。适用：运行脚本、git 操作、安装依赖。"
                   "不适用：读写单个文件（用专用工具更快更安全）。")
    permission = "write"
    params_spec = {"command": (str, True, "要执行的 shell 命令")}

    # ---- 安全护栏：危险命令黑名单（真实 harness 会用白名单+沙箱）----
    DANGEROUS = [r"rm\s+-rf\s+/", r"mkfs", r"dd\s+if=", r":\(\)\{.*\}", r"shutdown"]

    def validate(self, args):
        ok, err = super().validate(args)
        if not ok:
            return ok, err
        for pat in self.DANGEROUS:
            if re.search(pat, args["command"]):
                return False, (f"安全拦截：命令匹配危险模式 '{pat}'，已拒绝执行。"
                               f"如确需此操作，请改用更安全的替代命令或向用户确认。")
        return True, None

    def run(self, command):
        return f"[bash 模拟输出] 已执行: {command}"

class GrepTool(Tool):
    name = "grep"
    description = "在文件内容中搜索正则表达式。适用：找代码、找配置项。"
    permission = "read"
    params_spec = {
        "pattern": (str, True, "要搜索的正则表达式"),
        "path": (str, False, "搜索目录，默认当前目录"),
    }
    def run(self, pattern, path="."):
        return f"[grep 模拟输出] 在 {path} 中搜索 '{pattern}'：找到 3 处匹配"

# ---------------------------------------------------------------
# 3. 工具注册表 + 执行入口（编排层调用它的方式）
# ---------------------------------------------------------------

class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, tool: Tool):
        self.tools[tool.name] = tool

    def schemas_for_llm(self):
        """把所有工具的 schema 打包给模型 —— 模型据此决定调用谁"""
        out = []
        for t in self.tools.values():
            out.append({"name": t.name, "description": t.description,
                        "permission": t.permission,
                        "params": {k: f"{v[0].__name__}{'*' if v[1] else ''}: {v[2]}"
                                   for k, v in t.params_spec.items()}})
        return out

    def execute(self, name, args, approved=False):
        """完整执行流程：找到工具 -> 校验 -> 权限检查 -> 执行"""
        tool = self.tools.get(name)
        if tool is None:
            # 错误信息里附上可用工具列表，帮模型自我修正
            return f"错误：未知工具 '{name}'。可用工具: {list(self.tools)}"
        ok, err = tool.validate(args)
        if not ok:
            return f"校验失败: {err}"
        if tool.permission in ("write", "danger") and not approved:
            # 写操作默认需用户确认 —— agent 安全的经典设计
            return (f"需要用户确认: '{name}' 是{ {'write':'写操作','danger':'高危操作'}[tool.permission] }，"
                    f"已暂停。请在获得用户批准后重新调用。")
        return tool.run(**args)

# ---------------------------------------------------------------
# 4. 演示：模拟模型的 5 次调用，覆盖各种成功/失败场景
# ---------------------------------------------------------------

def demo():
    reg = ToolRegistry()
    reg.register(BashTool())
    reg.register(GrepTool())

    print("== 模型看到的工具 schema ==")
    print(json.dumps(reg.schemas_for_llm(), ensure_ascii=False, indent=2))

    print("\n== 模拟模型调用 ==")
    cases = [
        ("调用 1: 正常只读工具",       "grep",   {"pattern": "def run_agent", "path": "/tmp"}),
        ("调用 2: 拼错工具名",         "grpe",   {"pattern": "x"}),
        ("调用 3: 缺必填参数",         "bash",   {}),
        ("调用 4: 危险命令被拦截",     "bash",   {"command": "rm -rf /"}),
        ("调用 5: 写操作未获批准",     "bash",   {"command": "git push"}),
    ]
    for label, name, args in cases:
        print(f"\n{label}")
        print(f"  调用: {name}({json.dumps(args, ensure_ascii=False)})")
        print(f"  返回: {reg.execute(name, args)}")

    print("\n== 场景 6: 用户批准后，写操作放行 ==")
    print(f"  返回: {reg.execute('bash', {'command': 'git push'}, approved=True)}")

if __name__ == "__main__":
    demo()
