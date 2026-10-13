# -*- coding: utf-8 -*-
"""task-33 验收的独立探针（不复用作者用例的断言，自己驱动 `FarmWorker.sleep()`）。

覆盖 Lead 的条款 3/4：
  A 永远不弹提问 ⇒ `sleep_no_question` 且**一次 `sleep` 请求都不发**、一次 `interact` 都没有；
  B 关框也救不回日期 ⇒ `timeout` 且有界（数 `pause` 轮数、`move_to` 次数）；
  C 桥中途沉默（observe 抛 BridgeError）⇒ 会怎样？（记录：有界但**异常穿出**，不是 StepResult）
  D 生产默认 `pause` 必须是真 `time.sleep`（不是 no-op）。

用法：`python scratch/_t33_probe.py`
"""

from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "brain"))
sys.path.insert(0, str(ROOT))

from agentfarm.bridge import BridgeError            # noqa: E402
from agentfarm.farmwork import SLEEP_NO_QUESTION, FarmWorker  # noqa: E402
import tests.test_farmwork as tf                    # noqa: E402  （复用它的假桥/假世界）

FAILED: list[str] = []


def check(tag: str, cond: bool, detail: str = "") -> None:
    print(f"{'PASS' if cond else 'FAIL'} {tag}" + (f" :: {detail}" if detail else ""))
    if not cond:
        FAILED.append(tag)


class FlakyBridge(tf.MiniBridge):
    """前 `ok_calls` 次 observe 正常，之后抛 BridgeError（模拟桥中途沉默）。"""

    def __init__(self, world, ok_calls=1):
        super().__init__(world)
        self.ok_calls = ok_calls
        self.observes = 0

    def observe(self, detail="summary", *, timeout=None):
        self.observes += 1
        if self.observes > self.ok_calls:
            raise BridgeError("observe 超时：桥没有响应", status="timeout")
        return self.w.obs()


def build(world, pause=None, client=None):
    kw = {"log": lambda _s: None}
    if pause is not None:
        kw["pause"] = pause
    return FarmWorker(client or tf.MiniBridge(world), **kw)


def scenario_a() -> None:
    w = tf.MiniWorld()
    w.step_opens_question = False                 # 踩了触发格也没提问（run2 的实情）
    pauses = []
    worker = build(w, pause=lambda s: pauses.append(s))
    r = worker.sleep()
    check("A 判据码 = sleep_no_question", r.code == SLEEP_NO_QUESTION, f"code={r.code!r}")
    check("A 绝不盲发 sleep 请求", w.sleep_calls == [], f"sleep_calls={w.sleep_calls}")
    check("A 一次 interact 都没有", w.interacts == 0, f"interacts={w.interacts}")
    check("A 不封格（proven_inert False）", not r.proven_inert, f"proven_inert={r.proven_inert}")
    check("A 等待轮数有界（<=8）", len(pauses) <= 8, f"pauses={len(pauses)}")
    check("A move_to 次数有界（<=6）", len(w.moves) <= 6, f"moves={len(w.moves)}")


def scenario_b() -> None:
    w = tf.MiniWorld()
    w.sleep_mode = "timeout"                      # Mod 回 timeout
    w.dismiss_finishes_day = False                # 关框也救不回日期
    pauses = []
    worker = build(w, pause=lambda s: pauses.append(s))
    r = worker.sleep()
    check("B 码 = timeout", r.code == "timeout", f"code={r.code!r}")
    check("B 兜底关框发了 1 次", w.dismiss_calls == 1, f"dismiss_calls={w.dismiss_calls}")
    check("B 只发 1 次 sleep（绝不重发）", w.sleep_calls == [15000], f"sleep_calls={w.sleep_calls}")
    check("B Mod 现场留在 reason 里", "newDaySync" in r.reason, r.reason[-60:])
    check("B 等待轮数有界（<=20）", len(pauses) <= 20, f"pauses={len(pauses)}")


def scenario_c() -> None:
    w = tf.MiniWorld()
    client = FlakyBridge(w, ok_calls=1)           # 第 2 次 observe 就掉线
    worker = build(w, pause=lambda _s: None, client=client)
    raised = None
    try:
        worker.sleep()
    except BridgeError as exc:
        raised = exc
    check("C 桥中途沉默 ⇒ 抛 BridgeError（不是 StepResult）", raised is not None,
          f"raised={type(raised).__name__ if raised else None} observes={client.observes}")
    check("C 有界：observe 次数很小", client.observes <= 4, f"observes={client.observes}")
    check("C 未发出 sleep 请求（还没走到应答）", w.sleep_calls == [], f"sleep_calls={w.sleep_calls}")


def scenario_d() -> None:
    w = tf.MiniWorld()
    worker = FarmWorker(tf.MiniBridge(w), log=lambda _s: None)   # 不传 pause = 生产形态
    check("D 生产默认 pause 是真 time.sleep", worker.pause is time.sleep, f"pause={worker.pause!r}")
    prod = FarmWorker(tf.MiniBridge(w), log=lambda _s: None)
    check("D 注入 pause 生效（测试形态）",
          build(w, pause=lambda _s: None).pause is not time.sleep)


def main() -> int:
    for fn in (scenario_a, scenario_b, scenario_c, scenario_d):
        print(f"--- {fn.__name__}")
        fn()
    print(f"== 探针结束：{'ALL-PASS' if not FAILED else 'FAILED ' + ','.join(FAILED)}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    raise SystemExit(main())
