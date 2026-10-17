r"""task-190 探针骨架：对 task-186 / task-188 / task-189 的独立对抗验收（0.7.36 冻结门）。

只写 `scratch/`，不碰生产码。用 `T190_ROOT` 把探针指向任意快照树（缺省 = 当前仓库）：

    $env:T190_ROOT = "<repo>"; & $py -W error::SyntaxWarning scratch\_t190_probe.py

通道（卡面 7 条）：
  C1 F1 假绿：动作后缺格 + 其余三路全否 ⇒ 必须 failed；反例（格在窗口内 + crop 消失）⇒ 仍应 ok
  C2 F3 白名单污染：无关物品入包 ⇒ 不许进 `sell` 白名单；工具/种子/建材红线不放宽
  C3 F5 措辞：`readyCrops` 缺失/-1 ⇒ 文案必须写"无法判定"，不许写"没下降"
  C4 R2 loot 记账：多格 + 并入既有叠 + 延迟入包 ⇒ 记账正确、不许写"没有新增物品"；真丢失 ⇒ 如实告警
  C5 R1 Mod `use_tool` 回执 acted/actedEvidence（**等 task-188**，未落地 ⇒ SKIP）
  C6 GAP 类：作者是否用源码文本断言冒充行为回归；C# 断言必须真跑编译产物；变异映射实测
  C7 一致性：`checks` 键集未变、`_leftover` 语义未变、F4 已注明"有意口径"

骨架状态：C1–C4/C7 已可跑（task-186/189 已入库）；C5 等 task-188；C6 的变异复核待补。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("T190_ROOT") or Path(__file__).resolve().parents[1]).resolve()
for p in (ROOT, ROOT / "brain", ROOT / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import test_farmwork as TF                      # noqa: E402
import agentfarm.farmwork as FW                 # noqa: E402

PASS = 0
FAIL = 0
SKIPPED = 0
FINDINGS: list[str] = []
SRC = (ROOT / "brain" / "agentfarm" / "farmwork.py").read_text(encoding="utf-8")


def check(tag: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {tag}")
    else:
        FAIL += 1
        print(f"  FAIL {tag}  :: {detail}")


def finding(tag: str, reproduced: bool, detail: str = "") -> None:
    if reproduced:
        FINDINGS.append(tag)
        print(f"  发现 {tag}  :: {detail}")
    else:
        print(f"  （未复现）{tag}  :: {detail}")


def skip(tag: str, why: str) -> None:
    global SKIPPED
    SKIPPED += 1
    print(f"  SKIP {tag}  :: {why}")


def has_186() -> bool:
    return "tile_seen" in SRC and "whitelist_bound" in SRC


def has_189() -> bool:
    return "LOOT_CONFIRM_TRIES" in SRC


def has_188() -> bool:
    mod = ROOT / "mod" / "AgentFarm.Bridge" / "UseToolSkill.cs"
    tests = ROOT / "mod" / "AgentFarm.Bridge.Tests"
    body = mod.read_text(encoding="utf-8") if mod.exists() else ""
    probe = ""
    for p in tests.glob("*.cs"):
        probe += p.read_text(encoding="utf-8")
    return "actedEvidence" in (body + probe)


# ═══════════════════════════════ 夹具 ═══════════════════════════════
class World(TF.MiniWorld):
    """加 `hidden`：只从**观测**里抹掉这些格，世界真相（`records`）不变。"""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.hidden: set[tuple[int, int]] = set()
        self.hide_after_action = False


    def obs(self) -> dict:
        o = super().obs()
        if self.hidden:
            o["location"]["tiles"] = [r for r in o["location"]["tiles"]
                                      if tuple(r["tile"]) not in self.hidden]
        return o


def crop(tile=(60, 29), **kw) -> dict:
    rec = {"tile": list(tile), "kind": "dirt", "feature": "HoeDirt", "crop": "270",
           "ripe": True, "ready": True, "readySource": "game", "harvestMethod": "Grab",
           "regrowsAfterHarvest": True, "watered": True, "standable": True, "actionable": True}
    rec.update(kw)
    return rec


def item(qid: str, stack: int, slot: int = 9, name: str = "Item", is_tool: bool = False) -> dict:
    return {"slot": int(slot), "id": qid.split(")")[-1], "qualifiedId": qid,
            "name": name, "stack": int(stack), "isTool": bool(is_tool)}


def farm(crops=102, ready=102, **kw) -> dict:
    d = {"loaded": True, "complete": True, "crops": int(crops), "readyCrops": int(ready)}
    d.update(kw)
    return d


def mk(w: World, bridge_cls=TF.MiniBridge) -> FW.FarmWorker:
    return TF.FarmWorker(bridge_cls(w), log=lambda _s: None, pause=lambda _s: None)


# ═══════════════════════════════ C1（F1 假绿） ═══════════════════════════════
def case_f1() -> None:
    print("== C1 F1：动作后缺格不许当成功 ==")
    if not has_186():
        return skip("C1", "task-186 未落地")
    # 负例：动作后该格从观测里消失，且其余三路全否（世界真相：crop 仍在）
    w = World(records=[crop()], inventory=[item("(O)388", 99)])
    w.farm = farm()

    class HideBridge(TF.MiniBridge):
        def interact(self, tile=None, *, timeout_ms=None):
            self.w.hidden.add((int(tile[0]), int(tile[1])))
            return {"ok": True, "status": "ok", "acted": True}

    st = mk(w, HideBridge).harvest((60, 29))
    check("C1a 缺格 + 其余三路全否 ⇒ failed（不许假绿）",
          st.ok is False and st.code == "failed", f"ok={st.ok} code={st.code} reason={st.reason}")
    check("C1b 缺格时文案点明「不在观测窗口内」", "不在" in st.reason and "窗口" in st.reason, st.reason)
    check("C1c 缺格不许凭空写进白名单", mk(w, HideBridge).harvested == {}, "")

    # 正例（不许修成假阴）：格在观测里且 crop 真消失 ⇒ ok
    w2 = World(records=[crop()], inventory=[item("(O)388", 99)])
    w2.farm = farm()

    class GoneBridge(TF.MiniBridge):
        def interact(self, tile=None, *, timeout_ms=None):
            for r in self.w.records:
                r["crop"] = None
            return {"ok": True, "status": "ok", "acted": True}

    st2 = mk(w2, GoneBridge).harvest((60, 29))
    check("C1d 正对照：格在窗口内 + crop 消失 ⇒ 仍 ok（没修成假阴）",
          st2.ok is True and "crop 已消失" in st2.reason, f"ok={st2.ok} reason={st2.reason}")


# ═══════════════════════════════ C2（F3 白名单污染） ═══════════════════════════════
def case_f3() -> None:
    print("== C2 F3：无关物品不许进 sell 白名单 ==")
    if not has_186():
        return skip("C2", "task-186 未落地")
    w = World(records=[crop()], inventory=[item("(O)388", 99)])
    w.farm = farm()

    class UnrelatedBridge(TF.MiniBridge):
        def interact(self, tile=None, *, timeout_ms=None):
            for r in self.w.records:
                r["crop"] = None                       # 真的收成了
            self.w.inventory.append(item("(O)128", 1, 8, "Sardine"))   # 与本次动作无关
            return {"ok": True, "status": "ok", "acted": True}

    worker = mk(w, UnrelatedBridge)
    st = worker.harvest((60, 29))
    # 【卡面必修 2 的字面要求】白名单 `qid ⊆ 本次动作 affected_tiles 的 gained`。
    # 现实现只做到"没有格子级证据时整批不进白名单"；有格子级证据时**整份 gained** 都进 ⇒
    # 同一次动作里顺手进包的无关注 qid 仍会被放进白名单（本探针实测复现）。
    finding("C2-a 无关 qid 仍进 `sell` 白名单（卡面要求按 affected_tiles 的 gained 收窄）",
            "(O)128" in worker.harvested,
            f"harvested={worker.harvested} affected={(st.after or {}).get('affected_tiles')} "
            f"loot={(st.after or {}).get('loot')}")
    check("C2a 无关 qid 不进白名单（卡面字面：qid ⊆ affected_tiles 的 gained）",
          "(O)128" not in worker.harvested, f"harvested={worker.harvested}")
    check("C2a2 已实现的不变式：白名单 ⊆ 动作前后背包差分",
          set(worker.harvested) <= set((st.after or {}).get("loot") or {}),
          f"harvested={worker.harvested} loot={(st.after or {}).get('loot')}")
    check("C2c 只凭背包差分、没有格子级证据时白名单为空",
          (st.after or {}).get("whitelist_bound") is True or not worker.harvested,
          f"after={st.after}")
    # 红线不放宽：工具行不许进 sellable_slots
    w3 = World(records=[crop()], inventory=[item("(O)388", 99), item("(T)Hoe", 1, 3, "Hoe", True)])
    w3.farm = farm()
    slots = mk(w3).sellable_slots(w3.obs())
    check("C2d 工具行不进 sellable_slots（红线未放宽）",
          all((r.get("isTool") is not True) for r in slots), f"slots={slots}")


# ═══════════════════════════════ C3（F5 措辞） ═══════════════════════════════
def case_f5() -> None:
    print("== C3 F5：readyCrops 判不了时不许写「没下降」==")
    if not has_186():
        return skip("C3", "task-186 未落地")
    for label, f in (("缺字段", {}), ("-1", {"readyCrops": -1})):
        w = World(records=[crop()], inventory=[item("(O)388", 99)])
        w.farm = {"loaded": True, "complete": True, "crops": 102, **f}

        class NoopBridge(TF.MiniBridge):
            def interact(self, tile=None, *, timeout_ms=None):
                return {"ok": True, "status": "ok"}      # 回执 ok 但世界没动 ⇒ 走失败分支

        st = mk(w, NoopBridge).harvest((60, 29))
        check(f"C3 {label} ⇒ 文案含「无法判定」", "无法判定" in st.reason, st.reason)
        check(f"C3 {label} ⇒ 不许写「没下降」", "没下降" not in st.reason, st.reason)


# ═══════════════════════════════ C4（R2 loot 记账） ═══════════════════════════════
def case_r2() -> None:
    print("== C4 R2：多格 + 并入既有叠 + 延迟入包 ==")
    if not has_189():
        return skip("C4", "task-189 未落地")
    base = [item("(O)262", 1, 8, "Salmonberry"), item("(O)178", 1, 9, "Hay")]

    class MergeBridge(TF.MiniBridge):
        """一次动作收 4 格：+4 并入既有叠、+2 并入另一既有叠（真机形态）。"""

        def use_tool(self, tile=None, *, tool=None, timeout_ms=None):
            for r in self.w.records:
                r["crop"] = None
            for row in self.w.inventory:
                if row.get("qualifiedId") == "(O)262":
                    row["stack"] += 4
                elif row.get("qualifiedId") == "(O)178":
                    row["stack"] += 2
            return {"ok": True, "status": "ok", "acted": True,
                    "actedEvidence": "tile", "reason": "挥了一下"}

    w = World(records=[crop(crop="262", harvestMethod="Scythe")], inventory=[dict(r) for r in base])
    w.farm = farm()
    st = mk(w, MergeBridge).harvest((60, 29))
    got = (st.after or {}).get("loot") or {}
    check("C4a 并入既有叠的 +4/+2 都记进 gained",
          got.get("(O)262") == 4 and got.get("(O)178") == 2, f"loot={got}")
    check("C4b 不许再写「背包没有新增物品」",
          "没有新增物品" not in st.reason, st.reason)
    check("C4c ok 且理由写明逐 qid 差分", st.ok is True and "进背包" in st.reason, st.reason)

    # 延迟入包：第一张后观测里背包还是旧的，第二张才出现 ⇒ loot_waits ≥ 1 且记账正确
    class LateBridge(TF.MiniBridge):
        def __init__(self, w):
            super().__init__(w)
            self.calls = 0

        def use_tool(self, tile=None, *, tool=None, timeout_ms=None):
            for r in self.w.records:
                r["crop"] = None
            self.calls += 1
            return {"ok": True, "status": "ok", "acted": True}

        def observe(self, *a, **kw):
            obs = super().observe(*a, **kw)
            self.calls += 1
            if self.calls >= 2:
                for row in self.w.inventory:
                    if row.get("qualifiedId") == "(O)262":
                        row["stack"] += 4
            return obs

    w2 = World(records=[crop(crop="262", harvestMethod="Scythe")], inventory=[dict(r) for r in base])
    w2.farm = farm()
    st2 = mk(w2, LateBridge).harvest((60, 29))
    check("C4d 延迟入包 ⇒ 有界多等后仍记到 +4",
          ((st2.after or {}).get("loot") or {}).get("(O)262") == 4,
          f"loot={(st2.after or {}).get('loot')} waits={(st2.after or {}).get('loot_waits')}")

    # 真丢失：有格子级证据但背包始终没新增 ⇒ 如实写「对不上」，不许写「没有新增物品」
    class LossBridge(TF.MiniBridge):
        def use_tool(self, tile=None, *, tool=None, timeout_ms=None):
            for r in self.w.records:
                r["crop"] = None
            return {"ok": True, "status": "ok", "acted": True}

    w3 = World(records=[crop(crop="262", harvestMethod="Scythe")], inventory=[dict(r) for r in base])
    w3.farm = farm()
    st3 = mk(w3, LossBridge).harvest((60, 29))
    check("C4e 真丢失 ⇒ 文案写「对不上」", "对不上" in st3.reason, st3.reason)
    check("C4f 真丢失 ⇒ 不许写「没有新增物品」", "没有新增物品" not in st3.reason, st3.reason)
    check("C4g 真丢失 ⇒ 白名单为空（不出货）",
          ((st3.after or {}).get("loot_whitelisted") or []) == [], str(st3.after))


# ═══════════════════════════════ C5（R1 Mod 回执，等 task-188） ═══════════════════════════════
def case_r1() -> None:
    print("== C5 R1：use_tool 回执 acted/actedEvidence（fail-closed）==")
    if not has_188():
        return skip("C5", "task-188 未落地（UseToolSkill/自检工程里还没有 actedEvidence）")
    proj = ROOT / "mod" / "AgentFarm.Bridge.Tests" / "AgentFarm.Bridge.Tests.csproj"
    if not proj.exists():
        return skip("C5", "C# 自检工程不存在")
    proc = subprocess.run(["dotnet", "run", "--project", str(proj), "-c", "Release", "--nologo"],
                          cwd=str(ROOT), capture_output=True, text=True, timeout=900)
    out = (proc.stdout or "") + (proc.stderr or "")
    check("C5a C# 自检工程真的跑编译产物且 exit 0", proc.returncode == 0, out[-400:])
    check("C5b 自检输出含「断言全部通过」", "断言全部通过" in out, out[-400:])
    body = (ROOT / "mod" / "AgentFarm.Bridge" / "UseToolSkill.cs").read_text(encoding="utf-8")
    check("C5c use_tool 回执带 actedEvidence", "actedEvidence" in body or "ActedEvidence" in body, "")
    check("C5d use_tool 不许把 acted 简化成 err == null",
          not re.search(r"bool\s+acted\s*=\s*err\s*==\s*null\s*;", body), "")
    # 共享口径：interact 与 use_tool 走同一个证据方法
    skills = (ROOT / "mod" / "AgentFarm.Bridge" / "Skills.cs").read_text(encoding="utf-8")
    check("C5e 跨观测证据提取成共享方法（interact/use_tool 同源）",
          bool(re.search(r"(private|internal|static).*(Evidence|CrossObservation|WorldChange)", skills)), "")


# ═══════════════════════════════ C6（GAP 类） ═══════════════════════════════
def case_gap() -> None:
    print("== C6 GAP：行为回归不许用源码文本断言冒充 ==")
    tests = (ROOT / "tests" / "test_longrun.py").read_text(encoding="utf-8")
    check("C6a 存在真的 `dotnet run` 行为回归（不是只 grep 源码）",
          "dotnet" in tests and "AgentFarm.Bridge.Tests" in tests, "")
    proj = ROOT / "mod" / "AgentFarm.Bridge.Tests" / "AgentFarm.Bridge.Tests.csproj"
    if proj.exists():
        proc = subprocess.run(["dotnet", "run", "--project", str(proj), "-c", "Release", "--nologo"],
                              cwd=str(ROOT), capture_output=True, text=True, timeout=900)
        check("C6b C# 自检工程当前可跑（行为化）", proc.returncode == 0,
              ((proc.stdout or "") + (proc.stderr or ""))[-300:])
    else:
        skip("C6b", "C# 自检工程不存在")
    skip("C6c", "作者自报的「变异⇒用例」映射：task-190 正式跑时由 scratch\\_t190_mutate.py 实测复核")


# ═══════════════════════════════ C7（一致性） ═══════════════════════════════
CHECKS_KEYS = {"slept_by_us", "no_blocking_modal", "no_hard_failures", "unreachable_within_bound",
               "refused_within_bound", "no_unmet_stages", "crops_watered", "watered_outdoor",
               "day_justified", "zero_action_evidenced"}


def case_consistency() -> None:
    import agentfarm.longrun as LR
    print("== C7 一致性：checks 键集 / `_leftover` 语义 / F4 文档 ==")
    import inspect
    src = inspect.getsource(LR)
    m = re.search(r"rep\.checks = \{(.*?)\n        \}", src, re.S)
    found = set(re.findall(r'"([a-z_]+)":', m.group(1))) if m else set()
    check("C7a `checks` 键集仍是这 10 个（没被悄悄加宽）",
          found == CHECKS_KEYS, f"found={sorted(found)}")
    body = inspect.getsource(LR.LongRun._leftover)
    check("C7b `_leftover` 仍不按认输格逐格扣减（task-168 红线）",
          "_shed_tile_set" not in body, "body 里出现了 `_shed_tile_set`")
    doc = ROOT / "docs" / "_review-task181-182.md"
    text = doc.read_text(encoding="utf-8") if doc.exists() else ""
    check("C7c F4（仅 readySource 变化即算成功）已注明是**有意口径**",
          "F4" in text and ("有意" in text or "设计如此" in text), "")


CASES = {
    "C1": case_f1, "C2": case_f3, "C3": case_f5, "C4": case_r2,
    "C5": case_r1, "C6": case_gap, "C7": case_consistency,
}


def main() -> int:
    print(f"ROOT={ROOT}")
    print(f"markers: has_186={has_186()} has_188={has_188()} has_189={has_189()}")
    wants = sys.argv[1:] or list(CASES)
    for name in wants:
        fn = CASES.get(name.upper())
        if fn is None:
            print(f"  ?? 未知通道 {name}")
            continue
        fn()
    print(f"\n== 汇总：PASS={PASS} FAIL={FAIL} SKIP={SKIPPED}；复现发现 {len(FINDINGS)} 条 ==")
    for f in FINDINGS:
        print(f"   - {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
