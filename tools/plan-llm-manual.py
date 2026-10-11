"""用户 m01186 批准的**单次**边界决策演练：真的调一次大模型，把 prompt 与原文返回摊开给人看。

它做什么 / 不做什么
-------------------
* 只做**一次** `BoundaryPlanner.decide()`，让它自然走到 `default_llm_chat`（也就是产品里那条
  唯一联网路径）——不替换 seam，这样能同时验证"缝真的接在真 llm.chat 上"。
* 在调用前后临时包一层 `llm.chat`，只为**抄录**送出去的 messages 与拿回来的原文；
  不改行为（wrapper 原样转发参数与返回值，异常也原样抛）。
  注意 `default_llm_chat` 内部是 `from .llm import chat`（函数体内延迟导入），
  所以这个运行期替换**一定**会被它看到；若 captured 为空就是"没走到联网那条路"，会直接报出来。
* 不碰 Bridge（快照从 `--observe` 文件读），所以跑它不需要游戏开着。
* 把 messages、返回原文、坐标扫描、解析结果一起落进 `logs\\plan-llm-manual-<ts>.log`。

用法：
    python tools\\plan-llm-manual.py --observe scratch\\obs-full.json --boundary new_day
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "brain"))

from agentfarm import llm as llm_mod                          # noqa: E402
from agentfarm.__main__ import force_utf8_console             # noqa: E402
from agentfarm.planner import (                               # noqa: E402
    BOUNDARY_NEW_DAY,
    BOUNDARY_RECOVERY,
    BOUNDARY_TASK_CHANGE,
    BoundaryPlanner,
    Brief,
    PlannerState,
    farm_areas,
    find_coordinate_like,
)


def main() -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--observe", required=True,
                    help="full 快照 JSON 文件（'agentfarm observe full --json' 的输出）")
    ap.add_argument("--boundary", default=BOUNDARY_NEW_DAY,
                    choices=(BOUNDARY_NEW_DAY, BOUNDARY_RECOVERY, BOUNDARY_TASK_CHANGE))
    ap.add_argument("--failures", type=int, default=0)
    ap.add_argument("--max-tokens", type=int, default=16384,
                    help="给慢脑的 token 上限（默认 16384：8192 在 run2 真机上仍被推理吃光过）")
    ap.add_argument("--zone-split", type=int, default=2, dest="zone_split",
                    help="把农场切成 N×N 个具名田区（默认 2，与长跑一致）")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--out", default=None, help="日志文件（默认 logs\\plan-llm-manual-<ts>.log）")
    args = ap.parse_args()

    obs = json.loads(Path(args.observe).read_text(encoding="utf-8"))
    # 具名田区必须与长跑走同一条路：否则演练时提示词里显示"（本轮没有具名田区）"，
    # 而真机上却有 —— 那样的演练证不了"模型能指定去哪片地"。
    areas, area_lines = farm_areas(obs, split=args.zone_split)
    brief = Brief.from_observe(obs, consecutive_failures=max(0, args.failures),
                               areas=areas, area_lines=area_lines)
    if areas:
        print(f"具名田区（来自快照，split={args.zone_split}）：{', '.join(areas)}")
    else:
        print("具名田区：无（快照不是露天农场，或田区算不出来）")

    # 人为站到边界上：否则单次调用永远是"首次决策=非边界"，一次 LLM 都不会调。
    state = PlannerState(last_seen_failures=max(0, args.failures))
    if args.boundary == BOUNDARY_NEW_DAY:
        state.day_key = (-1, "forced-by-cli", -1)
    elif args.boundary == BOUNDARY_RECOVERY:
        state.last_seen_failures = max(0, args.failures) - 1
    elif args.boundary == BOUNDARY_TASK_CHANGE:
        state.last_task_kind = "__forced__"

    captured: list[dict] = []
    real_chat = llm_mod.chat

    def spy_chat(messages, **kwargs):                          # noqa: ANN001, ANN003
        started = time.perf_counter()
        try:
            result = real_chat(messages, **kwargs)
        except Exception as exc:                                # noqa: BLE001
            captured.append({"messages": messages,
                             "kwargs": {k: str(v) for k, v in kwargs.items()},
                             "error": f"{type(exc).__name__}: {exc}"})
            raise
        captured.append({
            "messages": messages,
            "kwargs": {k: str(v) for k, v in kwargs.items()},
            "content": result.content,
            "reasoning": result.reasoning,
            "model": result.model,
            "finish_reason": result.finish_reason,
            "usage": str(result.usage),
            "elapsed_ms": result.elapsed_ms,
            "wall_ms": int((time.perf_counter() - started) * 1000),
        })
        return result

    planner = BoundaryPlanner(llm_enabled=True, max_tokens=args.max_tokens,
                              temperature=args.temperature)
    # 关键：**不**替换 planner 的 seam，只把底层 llm.chat 包一层抄录；
    # 这样走的就是产品里那条 default_llm_chat 真路径。
    llm_mod.chat = spy_chat
    try:
        decision = planner.decide(state, brief)
    finally:
        llm_mod.chat = real_chat

    lines: list[str] = []
    add = lines.append
    add("=" * 78)
    add(f"单次边界决策演练（用户 m01186 批准）  边界={args.boundary}  "
        f"时间={time.strftime('%Y-%m-%d %H:%M:%S')}")
    add("=" * 78)
    add("")
    add("── 1. 情境简报（送进模型的「世界描述」，代码生成，必须是纯文字、无坐标）──")
    add(brief.situation_text())
    add("")
    add("── 2. 送出去的 messages（原文，逐条）──")
    if not captured:
        add("❌ 没有任何 LLM 调用！说明这次没走到 default_llm_chat（边界没触发 / 开关没开），"
            "下面的决策结果必然是纯代码降级。")
    for i, call in enumerate(captured, 1):
        add(f"--- 第 {i} 次调用  kwargs={call['kwargs']} ---")
        for msg in call["messages"]:
            add(f"[role={msg.get('role')}]")
            add(str(msg.get("content", "")))
            add("")
        if call.get("error"):
            add(f"!! 调用抛错：{call['error']}")
    add("")
    add("── 3. 模型原文返回 ──")
    for i, call in enumerate(captured, 1):
        if call.get("error"):
            add(f"--- 第 {i} 次返回：❌ 抛错（被 BoundaryPlanner 捕获后重问/降级）---")
            add(call["error"])
            add("")
            continue
        add(f"--- 第 {i} 次返回  model={call.get('model')} finish={call.get('finish_reason')} "
            f"usage={call.get('usage')} 耗时={call.get('elapsed_ms')}ms ---")
        if call.get("reasoning"):
            add("[reasoning_content]（推理模型的思考，非回答正文）")
            add(call["reasoning"])
            add("")
        add("[content]")
        add(call.get("content") or "（空）")
        add("")
        body = call.get("content") or ""
        hit = find_coordinate_like(body)
        add(f"坐标扫描（find_coordinate_like）：{'❌ 命中 ' + repr(hit) if hit else '✅ 无坐标'}")
        add("")
    add("── 4. 决策结果（解析、校验之后）──")
    add(f"边界={decision.boundary}  来源={decision.source}  真的调了 LLM={decision.llm_called}")
    add(f"prompt_chars={decision.prompt_chars}  attempts={decision.attempts}")
    if decision.fallback_reason:
        add(f"降级原因：{decision.fallback_reason}")
    if decision.rejection:
        add(f"拒收原因：{decision.rejection}")
    if decision.problems:
        add(f"问题清单：{list(decision.problems)}")
    for i, intent in enumerate(decision.intents, 1):
        add(f"  {i}. {intent.to_line()}")
    add("")
    add("（以上只有任务意图；坐标与动作序列由技能层按当下 observe 计算）")

    text = "\n".join(lines)
    print(text)
    out = Path(args.out) if args.out else REPO_ROOT / "logs" / f"plan-llm-manual-{int(time.time())}.log"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"\n[已写] {out}", file=sys.stderr)
    return 0 if decision.intents else 1


if __name__ == "__main__":
    sys.exit(main())
