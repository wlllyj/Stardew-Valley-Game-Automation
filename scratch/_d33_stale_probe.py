"""NIT-3 delta 复核（deputy-lead）：sleep 路径上 BridgeError 的分类是否"不误伤"。

问题：`_sleep_impl` 里
    if not raw or raw == "bridge_down" or raw in BRIDGE_DOWN_STATUSES: raise
只要 `status` 属"桥自己没了"就 re-raise，交给 `_sleep_bridge_fail` 收口（报 bridge_down、不做兜底关框）；
`timeout`/`stale`/`no_save`/`ui_modal`/`world_fading`/`busy` 这些**游戏侧/环境侧**码应该**不** re-raise，
继续走原来的"打标 + 兜底关框 + 等日期"。

本探针把 `MiniWorld.do_sleep` 换成"抛指定 status 的 BridgeError"，逐个看：
  ① 异常是否穿出（应否）；② `code`；③ 是否走 bridge-fail 分支（reason 含"睡觉过程中桥失败"）；
  ④ 兜底关框是否发生（`dismiss_calls`）。
只读：不写任何生产文件。
"""

import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.test_farmwork import MiniWorld, make_worker  # noqa: E402
import agentfarm.farmwork as fw                          # noqa: E402

GAME_SIDE = ("timeout", "stale", "no_save", "ui_modal", "world_fading", "busy", "error")
BRIDGE_SIDE = ("connection_broken", "unreachable_bridge", "bad_response", "schema_mismatch")
# `BridgeError` 没带 status（生产不可达：`bridge.py` 每个 raise 都带 status）⇒ `_exc_status()` 按
# `error` 算（= inconclusive，见 `farmwork.py:454-460` 的 docstring），仍走 bridge-fail 收口。
NO_STATUS = ("",)


def probe(status: str):
    w = MiniWorld()
    w.in_bed = True
    w.question = "sleep"

    def boom(*_a, **_k):
        raise fw.BridgeError(f"Mod 回执 status={status or '(空)'}", status=status)

    w.do_sleep = boom
    r = make_worker(w).sleep()
    return w, r


print(f"{'status':20s} {'穿出?':6s} {'ok':6s} {'code':16s} {'env':6s} {'incon':6s} {'dismiss':8s} {'路径'}")
bad = []
for status in GAME_SIDE + BRIDGE_SIDE + NO_STATUS:
    try:
        w, r = probe(status)
    except BaseException as exc:                          # noqa: BLE001
        print(f"{status or '(空)':20s} ❌ {type(exc).__name__}: {str(exc)[:60]}")
        bad.append((status, "异常穿出"))
        continue
    bridge_road = "睡觉过程中桥失败" in r.reason
    road = "bridge-fail" if bridge_road else "原逻辑兜底"
    print(f"{status or '(空)':20s} {'否':6s} {str(r.ok):6s} {(r.code or '(空)'):16s} "
          f"{str(r.env_block):6s} {str(r.inconclusive):6s} {w.dismiss_calls:<8d} {road}")
    want_bridge = status in BRIDGE_SIDE or status in NO_STATUS
    if bridge_road != want_bridge:
        bad.append((status, f"路径错：期望 bridge-fail={want_bridge}，实得 {road}"))
    if status in BRIDGE_SIDE and r.code != "bridge_down":
        bad.append((status, f"归一词表未生效：code={r.code!r}"))
    if status in NO_STATUS and (r.code != "error" or not r.inconclusive):
        bad.append((status, f"无 status 应归 error+inconclusive，实得 code={r.code!r} incon={r.inconclusive}"))
    if status in GAME_SIDE and (w.dismiss_calls == 0 or r.code):
        bad.append((status, f"游戏侧码应走兜底关框且不算桥掉线，实得 dismiss={w.dismiss_calls} code={r.code!r}"))

print()
print("== 静态检查：`_sleep_bridge_fail` 里只许有 1 次 best-effort 观测 ==")
src = (ROOT / "brain/agentfarm/farmwork.py").read_text(encoding="utf-8").splitlines()
start = next(i for i, ln in enumerate(src) if ln.startswith("    def _sleep_bridge_fail("))
end = next(i for i in range(start + 1, len(src)) if src[i].startswith("    # ---") or src[i].startswith("    def "))
body = "\n".join(src[start:end])
snaps = body.count("self.snap()")
print(f"   _sleep_bridge_fail 行范围 {start + 1}-{end}；`self.snap()` 出现 {snaps} 次 "
      f"（无循环）⇒ {'✅ 只做 1 次' if snaps == 1 and 'while ' not in body and 'for ' not in body else '❌ 有重试风险'}")

print()
print("== 结论 ==")
if bad:
    for status, why in bad:
        print(f"   ❌ {status or '(空)'}: {why}")
else:
    print("   ✅ 游戏侧/环境侧码全部不 re-raise（走原兜底逻辑、兜底关框 1 次）；桥侧码全部折成 bridge_down；"
          "无 status ⇒ error+inconclusive")
print("   生产 farmwork.py SHA256 =",
      hashlib.sha256((ROOT / "brain/agentfarm/farmwork.py").read_bytes()).hexdigest().upper())
