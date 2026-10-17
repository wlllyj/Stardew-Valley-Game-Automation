r"""task-200：0.7.37 批次（task-198/199/195/196/197 + 193）独立对抗验收探针。

用法：
  & $py -W error::SyntaxWarning scratch\_t200_probe.py            # 跑当前树
  $env:T200_ROOT = "$PWD\scratch\_t200_pre198"; & $py ...          # 跑冻结快照树（pre）
  $env:T200_FORCE = "1"                                           # 未交付也照跑（拿 pre 侧 FAIL 原文）

纪律：只写 `scratch/`；不改生产代码；`T200_ROOT` 只指向 `git archive` 出来的冻结快照。
设计：夹具/工具调用复用 `scratch\_t185_probe.py`（成熟脚手架），本文件只写本批的用例。
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("T200_ROOT") or WS)
FORCE = bool(os.environ.get("T200_FORCE"))

# _t185_probe 在 import 时就按 T185_ROOT 解析 brain/tests 的 import ⇒ 必须先设环境
os.environ["T185_ROOT"] = str(ROOT)
_spec = importlib.util.spec_from_file_location("t185", WS / "scratch" / "_t185_probe.py")
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)
T.ROOT = ROOT
J = WS / "scratch" / "_t200_j"
J.mkdir(parents=True, exist_ok=True)

check, skip = T.check, T.skip
NOTES: list[tuple[str, bool, str]] = []


def info(tag: str, ok: bool, detail: str = "") -> None:
    """只记录、不计入 PASS/FAIL（版本号这类"冻结后必然变化"的口径）。"""
    NOTES.append((tag, ok, detail))
    print(("  info " if ok else "  WARN ") + tag + (f" :: {detail}" if detail else ""))


def finding(tag: str, ok: bool, detail: str = "") -> None:
    NOTES.append((tag, ok, detail))
    print(("  info " if ok else "  WARN ") + tag + (f" :: {detail}" if detail else ""))


def marker(rel: str, needle: str) -> bool:
    p = ROOT / rel
    try:
        return needle in p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def has_198() -> bool:
    return FORCE or (marker("brain/agentfarm/farmwork.py", "no_slot")
                     and marker("brain/agentfarm/longrun.py", "inventory_blocked"))


def has_199() -> bool:
    return FORCE or (marker("mod/AgentFarm.Bridge/Contracts.cs", "readyTiles")
                     and marker("brain/agentfarm/farmwork.py", "ready_far_blocked"))


def has_195() -> bool:
    """task-195 的真 marker：作者会新增 `TestTask195*` 用例类；辅以 Mod 侧证据绑定字段。

    旧写法 `"5" in ClumpRules.cs` 是假阳性（文件里到处是数字字符），已废弃。
    """
    try:
        txt = (ROOT / "tests/test_longrun.py").read_text(encoding="utf-8", errors="replace")
    except OSError:
        txt = ""
    return FORCE or ("TestTask195" in txt
                     or marker("mod/AgentFarm.Bridge/Skills.cs", "affectedTiles")
                     or marker("mod/AgentFarm.Bridge/Contracts.cs", "evidenceScope"))


def has_196() -> bool:
    return FORCE or marker("brain/agentfarm/farmwork.py", "collateral_loot")


def has_197() -> bool:
    # 197 判据只能实测：子进程抓 stdout 是否显式编码 / 是否有 ASCII 标记
    p = ROOT / "tests" / "test_longrun.py"
    try:
        txt = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "SELFTEST_OK" in txt or 'encoding="utf-8"' in txt and "test_csharp_rules_self_test" in txt


# ---------------------------------------------------------------- A 段（批次级）
CHECKS_10 = {
    "crops_watered", "day_justified", "no_blocking_modal", "no_hard_failures",
    "no_unmet_stages", "refused_within_bound", "slept_by_us", "unreachable_within_bound",
    "watered_outdoor", "zero_action_evidenced",
}


def case_a() -> None:
    print("== A 段：批次级不变量（不 bump / checks 10 键 / JUSTIFIED_END_REASONS 不变）==")
    import json
    try:
        man = json.loads((ROOT / "mod/AgentFarm.Bridge/manifest.json").read_text(encoding="utf-8"))
        ver = str(man.get("Version") or "")
    except Exception as exc:                              # noqa: BLE001
        ver = f"(读不到: {exc})"
    info("A1 本批不 bump（manifest 仍是冻结的 0.7.36；冻结后变 0.7.37 属正常）", ver == "0.7.36", f"manifest={ver}")
    try:
        br = (ROOT / "brain/agentfarm/bridge.py").read_text(encoding="utf-8")
        exp = [ln for ln in br.splitlines() if ln.startswith("MOD_VERSION_EXPECTED")]
        info("A2 MOD_VERSION_EXPECTED 未越界 bump", '"0.7.36"' in (exp[0] if exp else ""), exp[0][:70] if exp else "缺")
    except OSError:
        info("A2 MOD_VERSION_EXPECTED 未越界 bump", False, "bridge.py 读不到")
    if has_198() or has_199() or has_196():
        lr = ROOT / "brain/agentfarm/longrun.py"
        txt = lr.read_text(encoding="utf-8", errors="replace")
        info("A3 JUSTIFIED_END_REASONS 语义未变", 'JUSTIFIED_END_REASONS = ("night", "stamina", "no_work")' in txt)
        info("A4 checks 键集仍 10 键（不许新增/删）", all(k in txt for k in CHECKS_10))
    else:
        skip("A3/A4 差量不变量", "本批卡未交付")


# ---------------------------------------------------------------- task-198 夹具
FW, LR, TL = T.FW, T.LR, T.TL


def _bag_rows(w, used: int = 12, material: int = 0) -> None:
    """占 `used` 行：前几行填杂物，`material` 行放可卖盈余材料（Wood 14 件 > K=10）。"""
    rows = []
    for i in range(max(0, used - material)):
        rows.append({"slot": i, "id": "300", "qualifiedId": "(O)300",
                     "name": "Filler", "stack": 1, "isTool": False})
    for i in range(material):
        rows.append({"slot": used - material + i, "id": "388", "qualifiedId": "(O)388",
                     "name": "Wood", "stack": 14, "isTool": False})
    w.inventory = rows


def _ripe_world(*, free_slots: int = 0, material: int = 0, n_ripe: int = 1,
                seeds: int = 0, money: int = 500):
    w = TL.FakeWorld(weeds=0, seeds=seeds, money=money)
    w.inventory_capacity = 12
    tiles = [(61 + i, 11) for i in range(n_ripe)]
    for t in tiles:
        w.dirt.add(t)
        w.crops[t] = {"ripe": True, "watered": True}
    w.player_tile = [60, 13]
    w.farm = w.farm_scan()
    used = max(1, 12 - int(free_slots))
    _bag_rows(w, used=used, material=min(material, used))
    return w, tiles


class _Client(TL.FakeClient):
    """补 `FakeClient` 缺的 `buy`/`sell`（真 `FarmWorker` 会调；回 dict 形状）。"""

    def buy(self, item, count=1, *, shop=None, timeout_ms=8000):        # noqa: ANN001
        return {"ok": False, "status": "item_not_sold", "availableItems": [],
                "reason": "探针桩：不卖种子", "money": 0}

    def sell(self, slot, *, whitelist=None, timeout_ms=8000):           # noqa: ANN001
        """复刻 `ShipSkill`：整叠出手、从背包删掉这一行；白名单只收本批 qid。"""
        rows = self.w.inventory
        for i, it in enumerate(rows):
            if int(it.get("slot", -1)) == int(slot):
                qid = str(it.get("qualifiedId") or "")
                if whitelist and qid not in whitelist:
                    return {"ok": False, "status": "not_whitelisted", "slot": int(slot),
                            "reason": f"{qid} 不在白名单里"}
                rows.pop(i)
                return {"ok": True, "status": "ok", "slot": int(slot), "item": it,
                        "bin": len(rows)}
        return {"ok": False, "status": "empty_slot", "slot": int(slot)}


def _mk(w, tag: str):
    journal = J / f"{tag}.jsonl"
    journal.unlink(missing_ok=True)
    client = _Client(w)
    worker = FW.FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
    run = TL.make_run(w, target_days=1, max_days=1,
                      client_factory=lambda: client, worker_factory=lambda c: worker,
                      journal_path=journal)
    run.worker, run.client = worker, client
    return run, worker, client


def _events(run, name: str):
    return [e for e in run.entries if str(e.get("event") or "") == name]


def _day(run):
    return run.days[0] if run.days else None


def _a_prime() -> None:
    r"""A′ 原型复现通道（Lead m08246 的正式冻结判据）。

    照 `logs\longrun-runA3-0736.jsonl` day13 的真实形态：背包满 + 多格熟作物在窗口外，
    pre 树会以 `stuck:同一秒连发 5 次换片都没有目标（守卫仍说还有活：农场口径还有 8 格熟作物…）`
    收尾；post 树必须出现 `slot_relief` 或 `inventory_blocked`，且不得再出现该形态。
    """
    print("== A′ 原型复现通道（满包 + 多格熟作物，判据见 docs/_release-0.7.37.md §3）==")
    w, tiles = _ripe_world(free_slots=0, material=1, n_ripe=8)
    run, worker, client = _mk(w, "198f-relief")
    run.run()
    day = _day(run)
    relief = _events(run, "slot_relief")
    freed = max([int(e.get("freed") or 0) for e in relief] or [0])
    reason = str(getattr(day, "ended_reason", "") or "")
    check("198f-1 A′ 原型（满包 + 8 熟作物 + 可腾）：腾格回路真的动了（slot_relief.freed>=1）",
          freed >= 1, f"freed={freed} relief={[{k: e.get(k) for k in ('need', 'freed', 'shipped')} for e in relief]}")
    check("198f-2 A′ 原型：不再以『守卫仍说还有活』的 stuck 收尾",
          "守卫仍说还有活" not in reason, f"ended={str(getattr(day, 'ended_by', None))!s} reason={reason[:160]}")
    check("198f-3 A′ 原型：no_slot 不计硬失败（failed_steps==0）",
          day is None or int(day.failed_steps) == 0,
          f"failed_steps={getattr(day, 'failed_steps', None)} "
          f"stages={[(s.get('stage'), s.get('failed'), s.get('env_block')) for s in ((day.stages if day else []) or [])]}")

    # f4：满包且**腾不出**（无可卖/可出货材料）⇒ inventory_blocked，仍不许 stuck 冒充
    w4, tiles4 = _ripe_world(free_slots=0, n_ripe=8)
    run4, _, _ = _mk(w4, "198f-blocked")
    run4.run()
    day4 = _day(run4)
    reason4 = str(getattr(day4, "ended_reason", "") or "")
    ev4 = [str(e.get("event") or "") for e in run4.entries]
    check("198f-4 A′ 原型（满包且腾不出）：记 inventory_blocked（事件或收尾理由）",
          "inventory_blocked" in ev4 or reason4.startswith("inventory_blocked"),
          f"ended={str(getattr(day4, 'ended_by', None))!s} reason={reason4[:160]}")
    check("198f-5 A′ 原型（腾不出）：不许以『守卫仍说还有活』收尾",
          "守卫仍说还有活" not in reason4, f"reason={reason4[:200]}")
    check("198f-6 A′ 原型（腾不出）：不许洗成 VERIFIED", day4 is None or day4.verified is False,
          f"verified={getattr(day4, 'verified', None)} checks={getattr(day4, 'checks', None)}")

    # f7：低水位 = 1 空格 + 8 熟作物（dev-coder 必修第 2 条的回归钉）
    w7, tiles7 = _ripe_world(free_slots=1, n_ripe=8)
    run7, _, _ = _mk(w7, "198f-lowwater")
    run7.run()
    day7 = _day(run7)
    reason7 = str(getattr(day7, "ended_reason", "") or "")
    ev7 = [str(e.get("event") or "") for e in run7.entries]
    check("198f-7 低水位（1 空格 + 8 熟作物）：出现 slot_relief 或 inventory_blocked（不许白撞 no_slot）",
          ("slot_relief" in ev7) or ("inventory_blocked" in ev7),
          f"events={sorted(set(ev7))[:12]} reason={reason7[:140]}")
    check("198f-8 低水位：不许以『守卫仍说还有活』收尾", "守卫仍说还有活" not in reason7,
          f"reason={reason7[:200]}")


def case_198() -> None:
    print("== task-198：背包满 ⇒ no_slot 不算硬失败 + 腾格收敛 + 不许洗 VERIFIED ==")
    if not has_198():
        skip("198 全部通道", "task-198 未交付（缺 no_slot / inventory_blocked）")
        return
    # ---- 198a 单元级：满包 harvest 的归类 ----
    w, tiles = _ripe_world(free_slots=0)
    run, worker, _ = _mk(w, "198a")
    r = worker.harvest(tiles[0])
    no_slot_code = getattr(FW, "NO_SLOT_CODE", "no_slot")
    check("198a-1 满包 harvest ⇒ code=failed + status/no_slot 标记（不是普通失败）",
          r.code == "failed" and getattr(r, "no_slot", False) is True and r.status == no_slot_code,
          f"code={r.code} status={r.status} no_slot={getattr(r, 'no_slot', None)}")
    check("198a-2 no_slot 归阻塞类（env_block 且进 ENV_BLOCK_STATUSES）",
          bool(r.env_block) and no_slot_code in getattr(FW, "ENV_BLOCK_STATUSES", ()),
          f"env_block={r.env_block} statuses={getattr(FW, 'ENV_BLOCK_STATUSES', None)}")
    before = dict(run.tile_attempts)
    run._count_attempts([r])
    check("198a-3 no_slot 不占每格配额、不封格（tile_attempts 不变 / 不进 blocked）",
          run.tile_attempts == before and tiles[0] not in run.blocked,
          f"attempts {before} → {run.tile_attempts} blocked={sorted(run.blocked)}")
    note_giveup = getattr(run, "_note_harvest_gave_up", None)
    if callable(note_giveup):
        run.tile_attempts[tiles[0]] = 2          # 伪造"试满上限"，看 no_slot 是否被写进 gave_up
        _rep = LR.DayReport(day_key=("summer", 10, 1), started_at=0.0)
        note_giveup([r], _rep)
        run.tile_attempts.pop(tiles[0], None)
    check("198a-4 no_slot 不吃 harvest_gave_up 上限", not run.harvest_gave_up,
          f"harvest_gave_up={sorted(run.harvest_gave_up)}")

    # ---- 198b 日级：1 空格 + 3 熟作物 ⇒ 1 收成 + no_slot 若干 ----
    w, tiles = _ripe_world(free_slots=1, n_ripe=3)
    run, worker, client = _mk(w, "198b")
    run.run()
    day = _day(run)
    if day is None:
        check("198b 日级：跑到 day_end", False, "没有 day 记录")
    else:
        chk = dict(day.checks or {})
        check("198b-1 no_slot **不许**拉成硬失败（failed_steps==0 且 no_hard_failures=True）",
              int(day.failed_steps) == 0 and chk.get("no_hard_failures") is True,
              f"failed_steps={day.failed_steps} checks={chk} stages={[(s.get('stage'), s.get('failed'), s.get('env_block')) for s in day.stages]}")
        check("198b-2 无空格日**不许**假 VERIFIED（洗白检查）", day.verified is False,
              f"verified={day.verified} ended_by={day.ended_by} reason={str(day.ended_reason)[:120]}")
        check("198b-3 收尾理由如实 inventory_blocked（不是 stick/no_work 混用）",
              str(day.ended_reason or "").startswith("inventory_blocked"),
              f"ended_by={day.ended_by} reason={str(day.ended_reason)[:140]}")
        check("198b-4 harvest_gave_up 未被 no_slot 消耗", not run.harvest_gave_up,
              f"={sorted(run.harvest_gave_up)}")
        check("198b-5 有界（不空转到天亮）", len(run.entries) < 300, f"entries={len(run.entries)}")
        check("198b-6 checks 键集仍 10 键", set(chk) == CHECKS_10,
              f"差集={set(chk) ^ CHECKS_10}")

    _a_prime()   # A′ 原型通道先跑（pre 树没有 `_slot_relief` 也必须出读数）

    # ---- 198c 腾格优先的正对照：0 空格 + 可卖材料 + 熟作物 ----
    w, tiles = _ripe_world(free_slots=0, material=1, n_ripe=2)
    run, worker, client = _mk(w, "198c")
    run.run()
    day = _day(run)
    relief = _events(run, "slot_relief")
    freed = max([int(e.get("freed") or 0) for e in relief] or [0])
    check("198c-1 freeSlots==0 ⇒ 腾格回路真的腾出格子（slot_relief.freed>=1）", freed >= 1,
          f"relief={[{k: e.get(k) for k in ('need', 'freed', 'shipped')} for e in relief]}")
    check("198c-2 腾格后当天收成（正对照 ok_steps>=1）", day is not None and int(day.ok_steps) >= 1,
          f"ok_steps={getattr(day, 'ok_steps', None)} ended={getattr(day, 'ended_reason', '')!s:120}")

    # ---- 198d 收敛有界：腾不出 / 轮数用满 ----
    w, tiles = _ripe_world(free_slots=0)
    run, worker, _ = _mk(w, "198d")
    rep = LR.DayReport(day_key=("summer", 10, 1), started_at=0.0)
    ok1 = run._slot_relief(w.obs(), rep)
    check("198d-1 腾不出（无可出货/可卖叠）⇒ False + inventory_blocked 记账",
          ok1 is False and run.inventory_blocked_today and bool(_events(run, "inventory_blocked")),
          f"ok={ok1} blocked_today={run.inventory_blocked_today}")
    check("198d-2 slot_relief 记 freed=0（本轮腾 0 格立刻认输，不自旋）",
          any(int(e.get("freed") or 0) == 0 for e in _events(run, "slot_relief")),
          f"={[{k: e.get(k) for k in ('freed', 'round')} for e in _events(run, 'slot_relief')]}")
    w2, tiles2 = _ripe_world(free_slots=0, material=1)
    run2, _, _ = _mk(w2, "198d2")
    run2.slot_relief_today = int(getattr(LR, "SLOT_RELIEF_MAX", 3))
    rep2 = LR.DayReport(day_key=("summer", 10, 1), started_at=0.0)
    ok2 = run2._slot_relief(w2.obs(), rep2)
    reason_txt = str([e.get("reason") for e in _events(run2, "inventory_blocked")])
    check("198d-3 轮数用满 SLOT_RELIEF_MAX ⇒ False + 理由点名『用满』",
          ok2 is False and "用满" in reason_txt, f"ok={ok2} reasons={reason_txt[:160]}")

    # ---- 198e 不洗白：正对照日的 checks 语义 ----
    w, tiles = _ripe_world(free_slots=0, material=1, n_ripe=1)
    run, worker, client = _mk(w, "198e")
    run.run()
    day = _day(run)
    if day is not None:
        chk = dict(day.checks or {})
        check("198e 腾格日若真干完活 ⇒ 不许因少了格子而假红（no_hard_failures 仍 True）",
              chk.get("no_hard_failures") is True, f"checks={chk} failed={day.failed_steps}")


# ---------------------------------------------------------------- task-199
def case_199() -> None:
    print("== task-199：readyTiles 与 readyCrops 同源 + 走不到不空转 + 缺字段 fail-closed ==")
    if not has_199():
        skip("199 全部通道", "task-199 未交付（缺 readyTiles / ready_far_blocked）")
        return
    todo = [
        "199a readyTiles 与 readyCrops 同源一致（伪造不一致 ⇒ 必须被拦/不可采信）",
        "199b 窗口外熟作物有坐标 ⇒ 走过去收（harvest_far 系列留痕）",
        "199c 走不到 ⇒ 如实 ready_far_blocked、当天有界（不许同秒连发换片 5 次 stuck）",
        "199d 缺 readyTiles 字段 ⇒ fail-closed 老行为（不许凭空多出目标）",
        "199e Mod 侧 C# 自检含 readyTiles/readyCrops 同源 + 截断标志断言",
    ]
    for t in todo:
        skip(t, "待 task-199 交付后实现")


# ---------------------------------------------------------------- task-195
def case_195() -> None:
    print("== task-195：use_tool 证据绑定目标格 + 原始技能不许静默连带 ==")
    if not has_195():
        skip("195 全部通道", "task-195 未交付")
        return
    todo = [
        "195a 目标格 ready!=true + use_tool ⇒ 回执不得声称该格已空/已完成",
        "195b 连带影响必须入回执（affected/collateral 字段）",
        "195c 证据能区分目标格证据与聚合证据（scope/tile）",
        "195d C# 自检 ≥3 条新断言实测（含变异杀数）",
    ]
    for t in todo:
        skip(t, "待 task-195 交付后实现")


# ---------------------------------------------------------------- task-196
def case_196() -> None:
    print("== task-196：附带掉落分栏（loot/collateral_loot）+ 不进白名单 + 口径说明 ==")
    if not has_196():
        skip("196 全部通道", "task-196 未交付")
        return
    todo = [
        "196a 目标掉落 + 附带掉落同动作 ⇒ 两栏分别正确",
        "196b 附带掉落不进白名单 harvested（下游 sell 白名单不含它）",
        "196c 全量背包差 ≠ 白名单逐 qid 差 ⇒ 不判失败",
        "196d 口径说明已写进 docs（_run10-criteria.md / _analyze-longrun-caliber.md）",
    ]
    for t in todo:
        skip(t, "待 task-196 交付后实现")


# ---------------------------------------------------------------- task-197
def _suite(env: dict[str, str], timeout: int = 900) -> tuple[int, str]:
    e = {k: v for k, v in os.environ.items()
         if k not in ("PYTHONUTF8", "PYTHONIOENCODING", "LC_ALL", "PYTHONPATH")}
    e.update(env)
    e["PYTHONPATH"] = str(ROOT / "brain") + os.pathsep + str(ROOT)
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                       cwd=ROOT, env=e, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    err = r.stderr or ""
    fails = [ln.strip() for ln in err.splitlines()
             if ln.startswith(("FAIL:", "ERROR:"))]
    tail = "\n".join(err.strip().splitlines()[-2:])
    return r.returncode, f"{tail} :: " + (" / ".join(fails)[:400] if fails else "无 FAIL/ERROR 行")


def case_197() -> None:
    print("== task-197：带/不带 PYTHONUTF8 都绿 + 故意注入 cp1252 也绿 ==")
    if os.environ.get("T200_SKIP_SUITE"):
        skip("197 全部通道", "T200_SKIP_SUITE=1（变异矩阵跑批时跳过全量套件，省时）")
        return
    rc1, t1 = _suite({"PYTHONUTF8": "1"})
    check("197a 带 PYTHONUTF8=1 全量绿（基线）", rc1 == 0, f"rc={rc1} :: {t1}")
    rc2, t2 = _suite({})                                  # 完全不设 PYTHONUTF8
    check("197b 不带 PYTHONUTF8 全量绿（task-197 的目标）", rc2 == 0, f"rc={rc2} :: {t2}")
    rc3, t3 = _suite({"PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0", "LC_ALL": "C"})
    check("197c 故意注入 cp1252/cp1252 环境仍绿（护栏）", rc3 == 0, f"rc={rc3} :: {t3}")
    t = ROOT / "tests" / "test_longrun.py"
    txt = t.read_text(encoding="utf-8", errors="replace") if t.exists() else ""
    body = ""
    key = "def test_csharp_rules_self_test_passes"
    if key in txt:
        rest = txt.split(key, 1)[1]
        body = rest.split("\n    def ", 1)[0]
    check("197d C# 自检用例内部显式编码或 ASCII 标记（只看该用例体）",
          ("SELFTEST_OK" in body) or ('encoding="utf-8"' in body),
          f"用例体 {len(body)} 字符：既无 SELFTEST_OK 也无 encoding=utf-8")


# ---------------------------------------------------------------- main
def main() -> int:
    print(f"ROOT={ROOT}")
    print("markers: " + ", ".join(
        f"{c}={'Y' if fn() else 'n'}" for c, fn in
        (("198", has_198), ("199", has_199), ("195", has_195), ("196", has_196), ("197", has_197))))
    for fn in (case_a, case_198, case_199, case_195, case_196, case_197):
        try:
            fn()
        except Exception as exc:                          # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{fn.__name__} 跑完不抛异常", False, f"{type(exc).__name__}: {exc}")
    print(f"\n== 汇总：PASS={T.PASS} FAIL={T.FAIL} SKIP={T.SKIP} ==")
    return 1 if T.FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
