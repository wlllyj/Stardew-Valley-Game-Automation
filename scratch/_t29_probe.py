"""task-29 独立验收探针（deputy-lead / task-35 收尾后）。

不复用 tests/test_main_pid_gate.py 的 _Recorder，自己写最小桩，直接断言
`await_game_exit` **每一条 return 路径**的退出码与日志事实。
只读生产代码，不碰游戏、不碰桥。
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "brain"))

from agentfarm import __main__ as main_mod  # noqa: E402


class Rec:
    def __init__(self, alive, kill_result=True, bridge=None):
        self._alive = alive
        self._kill_result = kill_result
        self._bridge = bridge
        self.lines: list[str] = []
        self.slept: list[float] = []
        self.killed: list[int] = []

        self._orig_pid_alive = main_mod.pid_alive
        main_mod.pid_alive = lambda pid: self._alive  # noqa: ARG005

    def restore(self):
        main_mod.pid_alive = self._orig_pid_alive

    def out(self, line: str) -> None:
        self.lines.append(line)

    def sleep(self, s: float) -> None:
        self.slept.append(s)

    def kill(self, pid: int) -> bool:
        self.killed.append(pid)
        if isinstance(self._kill_result, BaseException):
            raise self._kill_result
        return bool(self._kill_result)

    def bridge_responds(self) -> bool:
        return bool(self._bridge)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    def gate(self, rid, seconds):
        return main_mod.await_game_exit(
            SimpleNamespace(pid=rid), seconds,
            sleep=self.sleep, out=self.out, kill=self.kill,
            bridge_responds=self.bridge_responds,
        )


def case(name, *, alive, rid, seconds=1, kill_result=True, bridge=None,
         want_rc=None, want_in=(), want_not_killed=False, want_killed=None):
    rec = Rec(alive, kill_result, bridge)
    try:
        rc = rec.gate(rid, seconds)          # 故意不 try/except：让异常穿出来就是 FAIL
    finally:
        rec.restore()
    problems = []
    if rc != want_rc:
        problems.append(f"rc={rc} 期望 {want_rc}")
    for needle in want_in:
        if needle not in rec.text:
            problems.append(f"日志缺 {needle!r}")
    if want_not_killed and rec.killed:
        problems.append(f"不该强杀却杀了 {rec.killed}")
    if want_killed is not None and rec.killed != want_killed:
        problems.append(f"killed={rec.killed} 期望 {want_killed}")
    print(f"[{'OK ' if not problems else 'BAD'}] {name}: rc={rc} killed={rec.killed} "
          f"sleeps={len(rec.slept)}")
    for line in rec.lines:
        print(f"        | {line}")
    for p in problems:
        print(f"        !! {p}")
    return not problems


ok = True

# 1) pid_alive 明确判死 ⇒ 0，且绝不该去强杀
ok &= case("A 判死⇒0", alive=False, rid=24444, want_rc=0,
           want_in=["已退出"], want_not_killed=True)

# 2) pid 未知（None）+ 桥没应答 ⇒ 等满后老实返回 1，不强杀
ok &= case("B 缺pid⇒1", alive=None, rid=None, want_rc=1,
           want_in=["无法判定", "缺 pid", "手动确认"], want_not_killed=True)

# 3) pid 未知 + 桥仍应答 ⇒ 仍要等满并返回 1（不许因为桥应答就报成功）
ok &= case("C 缺pid+桥活⇒1", alive=None, rid=None, bridge=True, want_rc=1,
           want_in=["桥仍在应答"], want_not_killed=True)

# 4) 强杀返回 False（taskkill 失败）⇒ 1 + 日志含"未成功"
ok &= case("D kill=False⇒1", alive=True, rid=24444, kill_result=False, want_rc=1,
           want_in=["强杀", "未成功"], want_killed=[24444])

# 5) 强杀抛异常 ⇒ 1，异常不许穿出（本用例不 try/except；穿出=脚本崩） + 如实说明原因
ok &= case("E kill 抛异常⇒1", alive=True, rid=24444, kill_result=OSError("taskkill 不在 PATH"),
           want_rc=1, want_in=["强杀抛异常", "OSError", "未成功"], want_killed=[24444])

# 6) 强杀返回 True ⇒ 0
ok &= case("F kill=True⇒0", alive=True, rid=24444, want_rc=0,
           want_in=["强杀成功"], want_killed=[24444])

# 7) 真值非 bool（例如手滑返回 1）⇒ 仍按"成功"处理（bool() 语义）
ok &= case("G kill=1(真值)⇒0", alive=True, rid=24444, kill_result=1, want_rc=0,
           want_in=["强杀成功"], want_killed=[24444])

# 8) pid 是非法字符串 ⇒ kill(int(pid)) 抛 ValueError 被兜住，rc=1（安全方向）
ok &= case("H pid 非法⇒1", alive=True, rid="abc", want_rc=1,
           want_in=["强杀抛异常", "ValueError", "未成功"], want_killed=[])

# 9) seconds=0 ⇒ 循环不进；pid 有值 ⇒ 直接走强杀兜底
ok &= case("I seconds=0 + pid⇒kill", alive=True, rid=24444, seconds=0, want_rc=0,
           want_in=["强杀成功"], want_killed=[24444])

print()
print("PROBE RESULT:", "ALL-PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
