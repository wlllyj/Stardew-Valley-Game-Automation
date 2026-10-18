#!/usr/bin/env python
"""task-31（0.7.46 冻结树 737c4a5）合并对抗验收探针 —— deputy-lead 独立实现。

四卡合并：task-25（背包升级对话购买）/ task-26（回片区预算口径）/
task-27（挡死格证据口径）/ task-28（售材纪律 + 满包证据门槛 + 清障有界）。
外加 task-33（Mod `talk` 原语）的契约面。

纪律：判据全部本人自写；只 import 冻结树 tests 的 FakeWorld/FakeClient/FakeWorker
当夹具（作者测试不跑也行，跑只用来看"作者口径"）。不写生产代码。

用法：
  PYTHONUTF8=1 python scratch\\_t0746b_probe.py --only A,B,C[,D] [--readings]
环境：
  T0746B_ROOT   冻结树根（默认仓库根；正式判定必须指向 `git archive 737c4a5` 解出的树）
  T0746B_COMMIT 冻结提交（默认 737c4a5）
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(os.environ.get("T0746B_ROOT") or Path(__file__).resolve().parents[1]).resolve()
REPO = Path(__file__).resolve().parents[1]
COMMIT = os.environ.get("T0746B_COMMIT") or "737c4a5"
PREV = "2feb1f8"          # 0.7.45 冻结（对比基线）
PY = sys.executable

sys.path.insert(0, str(REPO / "scratch"))
import _t0746_prep_replay as RP      # noqa: E402  预热重放判据（同作者：我）
import _t0746_prep_prov as PV        # noqa: E402  provenance 工具（同作者：我）

CHECKS_BASELINE = (
    "slept_by_us", "no_blocking_modal", "no_hard_failures",
    "unreachable_within_bound", "refused_within_bound", "no_unmet_stages",
    "crops_watered", "watered_outdoor", "day_justified", "zero_action_evidenced",
)
FORBIDDEN_SELL_QIDS = {"388", "390", "330", "771", "382", "378", "380", "384", "386", "909"}
KEY46 = [
    "brain/agentfarm/longrun.py", "brain/agentfarm/farmwork.py", "brain/agentfarm/bridge.py",
    "tests/test_longrun.py", "mod/AgentFarm.Bridge/manifest.json",
    "tests/_mutate_t25_dialogue.py", "tests/_mutate_t26_budget.py",
    "tests/_mutate_t27_enclosed.py", "tests/_mutate_t28_bag.py",
]

RESULTS: list[tuple[str, str, str]] = []


def check(tag: str, ok: Any, detail: str = "") -> None:
    state = "PASS" if ok else "FAIL"
    RESULTS.append((tag, state, detail))
    print(f"  {state:<4} {tag}" + (f" —— {detail}" if detail else ""))


def info(tag: str, detail: str = "") -> None:
    RESULTS.append((tag, "INFO", detail))
    print(f"  INFO {tag}" + (f" —— {detail}" if detail else ""))


def skip(tag: str, detail: str = "") -> None:
    RESULTS.append((tag, "SKIP", detail))
    print(f"  SKIP {tag}" + (f" —— {detail}" if detail else ""))


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def run_cmd(args: list[str], cwd: Path | None = None, extra_env: dict[str, str] | None = None):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if extra_env:
        env.update(extra_env)
    return subprocess.run(args, cwd=str(cwd or ROOT), env=env, text=True,
                          encoding="utf-8", errors="replace", capture_output=True)


def repo_git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO), *args], text=True,
                          encoding="utf-8", errors="replace", capture_output=True)
    return proc.stdout


def _day_ends() -> list[dict[str, Any]]:
    rows = RP.load_jsonl(ROOT / "logs" / "longrun-smoke-0745.jsonl")
    return RP.day_groups(rows)


def _smoke_day(day_num: int) -> dict[str, Any] | None:
    for d in _day_ends():
        de = d.get("day_end") or {}
        day = de.get("day") or []
        if isinstance(day, (list, tuple)) and len(day) >= 3 and int(day[2]) == day_num:
            return d
    return None


def _a8_rows() -> list[dict[str, Any]]:
    return RP.load_jsonl(ROOT / "logs" / "longrun-runA8-0743.jsonl")


# ---------------------------------------------------------------- 夹具
_FIX: dict[str, Any] = {}


def fixtures():
    if _FIX:
        return _FIX
    for p in (ROOT / "tests", ROOT / "brain"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import test_longrun as TL          # noqa: F401
    import agentfarm.longrun as LR    # noqa: F401
    import agentfarm.farmwork as FW   # noqa: F401
    _FIX.update(TL=TL, LR=LR, FW=FW)
    return _FIX


def fresh_rep(day: int = 26):
    TL = fixtures()["TL"]
    return TL.DayReport(day_key=("winter", 1, day), started_at=0.0)


def new_run(world=None):
    TL = fixtures()["TL"]
    w = world if world is not None else TL.FakeWorld(weeds=0, seeds=0, money=0)
    run = TL.make_run(w)
    run.client = TL.FakeClient(w)
    run.worker = TL.FakeWorker(w)
    return run, w


# ================================================================ A 段
def _checks_keys_from_source(src: str) -> tuple[list[str] | None, str]:
    """AST 找 `rep.checks = {...}` 的键序。"""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if (isinstance(tgt, ast.Attribute) and tgt.attr == "checks"
                    and isinstance(node.value, ast.Dict)):
                keys = []
                for k in node.value.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        keys.append(k.value)
                return keys, f"longrun.py:{node.lineno}"
    return None, "未找到 rep.checks 字面赋值"


def _field_names(src: str, cls_name: str) -> list[str]:
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            out: list[str] = []
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    out.append(stmt.target.id)
            return out
    return []


def _journal_names(src: str) -> set[str]:
    tree = ast.parse(src)
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute) and fn.attr in ("_journal", "journal"):
                if node.args and isinstance(node.args[0], ast.Constant):
                    v = node.args[0].value
                    if isinstance(v, str):
                        out.add(v)
    return out


def check_provenance() -> None:
    print("[A] provenance")
    ls = PV.parse_ls_tree(COMMIT)
    tracked = len(ls)
    missing, mismatch = 0, 0
    for rel, blob in ls.items():
        p = ROOT / rel
        if not p.exists():
            missing += 1
            continue
        got = PV.blob_sha(PV.norm(p.read_bytes()))
        if got != blob:
            mismatch += 1
    check("A0 全量 blob 对照", tracked > 0 and missing == 0 and mismatch == 0,
          f"{COMMIT}: tracked {tracked} / extracted {sum(1 for _ in ROOT.rglob('*') if _.is_file())} / "
          f"missing {missing} / mismatch {mismatch}")
    ok_key = 0
    detail: list[str] = []
    for rel in KEY46:
        p = ROOT / rel
        if not p.exists():
            detail.append(f"{rel}: 缺失")
            continue
        want = repo_git("rev-parse", f"{COMMIT}:{rel}").strip()
        got = repo_git("hash-object", "--path", rel, str(p)).strip()
        if got and got == want:
            ok_key += 1
            detail.append(f"{Path(rel).name}={got[:12]}")
        else:
            detail.append(f"{Path(rel).name}: {got[:12]}≠{want[:12]}")
    check("A0b 关键文件 hash-object 对照", ok_key == len(KEY46), f"{ok_key}/{len(KEY46)}: " + "、".join(detail))
    info("A0c 作者变异脚本清单", "、".join(sorted(p.name for p in (ROOT / "tests").glob("_mutate_*.py"))))


def check_version() -> None:
    print("[A] 版本载体")
    bridge = read("brain/agentfarm/bridge.py")
    manifest = read("mod/AgentFarm.Bridge/manifest.json")
    m = re.search(r'MOD_VERSION_EXPECTED\s*=\s*"([^"]+)"', bridge)
    mv = re.search(r'"Version"\s*:\s*"([^"]+)"', manifest)
    got_b = m.group(1) if m else "缺失"
    got_m = mv.group(1) if mv else "缺失"
    check("A1 bridge MOD_VERSION_EXPECTED=0.7.46", got_b == "0.7.46", got_b)
    check("A1b manifest Version=0.7.46", got_m == "0.7.46", got_m)
    msz = (ROOT / "mod/AgentFarm.Bridge/manifest.json").stat().st_size
    info("A1c manifest 字节数", f"{msz}B（Lead 报 75293B）")


def _code_only(text: str) -> str:
    """剥掉 docstring / 行注释，只留代码 —— 用于"生产代码里有没有这个动作"类判据。"""
    text = re.sub(r'""".*?"""', "", text, flags=re.S)
    text = re.sub(r"'''.*?'''", "", text, flags=re.S)
    return "\n".join(ln.split("#", 1)[0] for ln in text.splitlines())

def _func_body(src: str, name: str) -> str:
    """按缩进取一个函数/方法的完整函数体文本（不依赖下一条 def 是否顶格）。"""
    lines = src.splitlines(True)
    start, indent = None, None
    pat = re.compile(r"^(\s*)def " + re.escape(name) + r"\(")
    for i, ln in enumerate(lines):
        m = pat.match(ln)
        if m:
            start, indent = i, len(m.group(1))
            break
    if start is None:
        return ""
    out = []
    for ln in lines[start:]:
        if out:
            stripped = ln.lstrip()
            if stripped.startswith(("def ", "class ")):
                cur = len(ln) - len(stripped)
                if cur <= indent:
                    break
        out.append(ln)
    return "".join(out)


def check_checks_and_fields() -> None:
    print("[A] checks / DayReport 字段 / 事件名 / 公式")
    src = read("brain/agentfarm/longrun.py")
    keys, where = _checks_keys_from_source(src)
    check("A2 checks 十键未动", keys == list(CHECKS_BASELINE), f"{where}: {keys}")
    if keys is not None:
        polluted = [k for k in keys if k not in CHECKS_BASELINE]
        check("A2b checks 未被新字段污染", not polluted, f"extra={polluted}")
    base = repo_git("show", f"{PREV}:brain/agentfarm/longrun.py")
    old_fields = _field_names(base, "DayReport")
    new_fields = _field_names(src, "DayReport")
    added = [f for f in new_fields if f not in old_fields]
    removed = [f for f in old_fields if f not in new_fields]
    expect_task25 = {"backpack_capacity_before", "backpack_capacity_after",
                     "backpack_upgrade_ok", "backpack_upgrade_attempts",
                     "backpack_upgrade_failures", "backpack_upgrade_skip"}
    expect_task28 = {"relief_exhausted", "bag_evidence"}   # loot_lost_* 在 0.7.45 task-16 已有
    expect_task27 = {"pending_executable_tiles", "pending_stalled_tiles"}
    got = set(added)
    check("A3 DayReport 新增字段 = 三卡并集", got == (expect_task25 | expect_task28 | expect_task27),
          f"新增 {sorted(got)}；缺 {sorted((expect_task25 | expect_task28 | expect_task27) - got)}；"
          f"多 {sorted(got - (expect_task25 | expect_task28 | expect_task27))}")
    check("A3b 无字段被删", not removed, f"removed={removed}")
    old_ev, new_ev = _journal_names(base), _journal_names(src)
    check("A4 journal 事件名未增未删", not (new_ev - old_ev) and not (old_ev - new_ev),
          f"added={sorted(new_ev - old_ev)} removed={sorted(old_ev - new_ev)}")
    # 公式/护栏 B 逐字未动
    def slice_between(text: str, a: str, b: str) -> str:
        i = text.find(a)
        j = text.find(b, i + 1)
        return text[i:j] if i >= 0 and j > i else ""
    old_no_unmet = slice_between(base, '"no_unmet_stages": unmet_leftover == 0', '"crops_watered":')
    new_no_unmet = slice_between(src, '"no_unmet_stages": unmet_leftover == 0', '"crops_watered":')
    check("A5 no_unmet_stages 公式未动",
          old_no_unmet.split() == new_no_unmet.split() and bool(new_no_unmet),
          f"old={old_no_unmet.strip()!r}")
    old_bound = slice_between(base, "unreachable_bound = max(5,", "\n")
    new_bound = slice_between(src, "unreachable_bound = max(5,", "\n")
    check("A5b unreachable_bound 公式未动", old_bound.strip() == new_bound.strip() and bool(new_bound),
          new_bound.strip())
    old_after = slice_between(base, "rep.unreachable =", "rep.unreachable_bound")
    new_after = slice_between(src, "rep.unreachable =", "rep.unreachable_bound")
    check("A5c 护栏 B（cleared_tiles/unreachable 计数）未动",
          old_after.split() == new_after.split(), "")
    # malformed 一票否决顺序
    body = re.sub(r'""".*?"""', "", _func_body(src, "is_justified_end"), flags=re.S)
    veto = body.find("if int(malformed_tiles) > 0")
    first_white = min([x for x in (body.find("JUSTIFIED_END_REASONS"),
                                   body.find("HONEST_EXHAUSTED_END_REASONS"),
                                   body.find("HONEST_INVENTORY_END_REASONS")) if x >= 0] or [10**9])
    check("A6 malformed 一票否决在所有白名单之前", 0 <= veto < first_white,
          f"veto@{veto} 白名单@{first_white}")
    check("A6b inventory_blocked 已进诚实收工白名单（要求 exec==0）",
          'HONEST_INVENTORY_END_REASONS = ("inventory_blocked",)' in src
          and "HONEST_INVENTORY_END_REASONS" in body and "pending_executable" in body, "")
    check("A7 满包写入端四门槛（accepted=not gaps）",
          "accepted = not gaps" in src and "relief_not_exhausted" in src
          and "pending_executable=" in src, "")
    check("A7b 清障丢失硬上界常量=5 且闸门用它",
          re.search(r"CLEAR_LOOT_LOSS_MAX_STEPS\s*=\s*5", src) is not None
          and "CLEAR_LOOT_LOSS_MAX_STEPS - int(self.loot_lost_steps_today)" in src, "")


def check_card_sources() -> None:
    print("[A] 逐卡改法源码覆盖")
    src = read("brain/agentfarm/longrun.py")
    fw = read("brain/agentfarm/farmwork.py")
    # task-26
    check("A8 task-26 claim_exhausted = exec==0 and malformed==0",
          re.search(r"claim_exhausted = \(int\(snap\[\"executable\"\]\) == 0\s*\n\s*and int\(snap\.get\(\"malformed\", 0\)\) == 0\)", src) is not None,
          "")
    check("A8b task-26 无证据时用 resume_budget_exhausted 前缀",
          "resume_budget_exhausted:" in src, "")
    check("A8c task-26 bursts 事件带 walks/attempts/limits",
          "resume_walk_attempts=self.resume_walk_attempts," in src
          and "resume_walk_attempt_limit=2 * int(self.max_plots_per_day)," in src, "")
    # task-27
    check("A9 task-27 目标池前置过滤 + 四邻全观测证据",
          "pool = self._prefilter_known_enclosed(task, obs, pool)" in src
          and "if any(v is None for v in views):" in src
          and "prefilter=True" in src, "")
    # task-28
    check("A10 task-28 建材/锭移出可卖表（只剩 92/766）",
          'SURPLUS_MATERIAL_IDS = frozenset({\n    "92",    # Sap（树液，树桶副产品）\n    "766",   # Slime（史莱姆掉落）\n})' in fw
          and 'SLOT_RELIEF_MATERIAL_IDS = frozenset({\n    "92",    # Sap\n    "766",   # Slime\n})' in fw, "")
    # task-25
    check("A11 task-25 成功=观测差分（钱-2000 且 12→24）",
          "money_a == money_b - BACKPACK_UPGRADE_PRICE" in src
          and "cap_b == BACKPACK_BASE_CAPACITY" in src and "cap_a == BACKPACK_UPGRADE_CAPACITY" in src,
          "")
    check("A11b task-25 差分窗口歧义检查（sell/ship/day_start/day_end）",
          'in ("sell", "ship", "day_start", "day_end")' in src, "")
    # task-33
    tk = read("mod/AgentFarm.Bridge/TalkSkill.cs")
    check("A12 task-33 talk 唯一入口 found.checkAction(who, loc)",
          "applied = found.checkAction(who, loc);" in tk, "")
    bad = []
    for pat in ("Money =", "Money -=", "Money +=", "MaxItems =", ".increaseBackpackSize(", "SendInput", "keyboardState", "mouseState"):
        if pat in tk:
            bad.append(pat)
    check("A12b talk 源码无写钱/背包/键鼠", not bad, f"命中={bad}")
    check("A12c talk 回执契约字段齐",
          all(k in tk for k in ("Applied", "Code", "NpcTile", "Distance", "Available",
                                "ActiveMenu", "DialogueIsQuestion", "DialogueResponses")), "")
    check("A12d talk 注册进 catalog/Skills",
          any('"talk"' in read(rel) for rel in ("mod/AgentFarm.Bridge/SkillCatalog.cs",
                                                "mod/AgentFarm.Bridge/Skills.cs")), "")


# ================================================================ B 段
def check_ledger_replay() -> None:
    print("[B] 冒烟账本 0.7.45 旧形态重放（旧账本 → INFO）")
    d26, d27 = _smoke_day(26), _smoke_day(27)
    if not d26 or not d27:
        skip("B1 smoke-0745 两天未找到")
        return
    state26, det26 = RP.judge_inventory_blocked(d26)
    check("B1 冬26 四/五门槛逐条可判（旧代码形态）", state26 in ("green", "red", "undecidable"),
          f"state={state26} gates={det26.get('gates')}")
    e = det26.get("gates") or {}
    e1, e2, e3, e4, e5 = (e.get("E1_理由"), e.get("E2_最后观测真满"),
                          e.get("E3_腾格用尽"), e.get("E4_无可执行无残缺"),
                          e.get("E5_浪费有界"))
    check("B1b 冬26 旧代码 E2/E3/E5 不过（0.7.45 不该认）",
          e1 is True and (e2 is not True or e3 is not True or e5 is not True),
          json.dumps(e, ensure_ascii=False)[:400])
    state27, det27 = RP.judge_resume_claim(d27)
    info("B1c 冬27 旧账本 resume_exhausted+exec=7", f"state={state27} detail={json.dumps(det27, ensure_ascii=False)[:300]}")
    a8 = _a8_rows()
    info("B1d A8 账本重放（task-15/22 面）", json.dumps(RP.replay_a8(a8), ensure_ascii=False)[:400])
    # 32 格 till/clear 归属
    shape = RP.judge_till_shape(d26)
    info("B1e 冬26 32 格归属", f"state={shape[0]} {json.dumps(shape[1], ensure_ascii=False)[:400]}")
    sell = RP.judge_sell_discipline(d26)
    check("B1f 冬26 旧账本售材纪律命中（388/330/92）", sell[0] == "red",
          json.dumps(sell[1], ensure_ascii=False)[:400])


def check_is_justified_dynamic() -> None:
    print("[B] is_justified_end 动态（0.7.46 语义）")
    LR = fixtures()["LR"]
    f = LR.is_justified_end
    cases = [
        ("inventory_blocked+exec0+malformed0", ("inventory_blocked", "inventory_blocked:背包满"), {"pending_executable": 0, "malformed_tiles": 0}, True),
        ("inventory_blocked+exec1", ("inventory_blocked", "inventory_blocked:背包满"), {"pending_executable": 1, "malformed_tiles": 0}, False),
        ("inventory_blocked+malformed1", ("inventory_blocked", "inventory_blocked:背包满"), {"pending_executable": 0, "malformed_tiles": 1}, False),
        ("inventory_blocked+exec 缺失（None）", ("inventory_blocked", "inventory_blocked:x"), {"pending_executable": None, "malformed_tiles": 0}, False),
        ("resume_exhausted+exec0", ("sleep", "resume_exhausted:回片区没有目标"), {"pending_executable": 0, "malformed_tiles": 0}, True),
        ("resume_exhausted+exec7", ("sleep", "resume_exhausted:回片区"), {"pending_executable": 7, "malformed_tiles": 0}, False),
        ("resume_budget_exhausted（不进白名单）", ("sleep", "resume_budget_exhausted:预算用尽"), {"pending_executable": 0, "malformed_tiles": 0}, False),
        ("stuck:", ("sleep", "stuck:同一秒连发 5 次"), {"pending_executable": 0, "malformed_tiles": 0}, False),
        ("night", ("sleep", "night:夜里了"), {"pending_executable": 5, "malformed_tiles": 0}, True),
        ("night+malformed1", ("sleep", "night:夜里了"), {"pending_executable": 0, "malformed_tiles": 1}, False),
        ("ended_by=stuck", ("stuck", "stuck:随便"), {"pending_executable": 0, "malformed_tiles": 0}, False),
    ]
    got = []
    for name, args, kw, want in cases:
        try:
            got.append((name, bool(f(*args, **kw)), want))
        except Exception as exc:  # noqa: BLE001
            got.append((name, f"EXC {exc}", want))
    bad = [(n, g, w) for n, g, w in got if g != w]
    check("B2 is_justified_end 11 例（含 malformed 否决/resume_budget 不入白名单）", not bad, f"bad={bad}")
    check("B2b day_justified checks 调用传两证据",
          "malformed_tiles=rep.pending_malformed" in read("brain/agentfarm/longrun.py"), "")


def _water_obs(n_tiles: int, *, malformed: int = 0, player=(61, 10)):
    TL = fixtures()["TL"]
    w = TL.FakeWorld(weeds=0, seeds=0, money=3264)
    tiles = []
    for i in range(n_tiles):
        t = (60 + i, 10)
        tiles.append({"tile": [t[0], t[1]], "kind": "dirt", "standable": True,
                      "actionable": True, "crop": "24", "ripe": False, "ready": False,
                      "watered": False, "dead": False, "plantable": False,
                      "harvestMethod": "Grab", "readySource": "game"})
    if n_tiles:
        # 玩家脚下与邻格也要在 tiles[] 里（standable_next_to 用观测证据）
        tiles.append({"tile": list(player), "kind": "dirt", "standable": True,
                      "actionable": True, "plantable": True, "watered": False})
    for j in range(malformed):
        tiles.append({"tile": [70 + j, 12]})
    obs = {"ok": True, "status": "ok", "schema": "agentfarm-world/6",
           "worldSeq": 1, "hasSaveLoaded": True,
           "clock": {"year": 1, "season": "winter", "day": 26, "timeOfDay": 600},
           "player": {"name": "t", "location": "Farm", "tile": list(player),
                      "stamina": 270.0, "maxStamina": 270.0, "money": 3264,
                      "inventory": [dict(x) for x in w.inventory],
                      "inventoryCount": 12},
           "location": {"name": "Farm", "isOutdoorFarm": True,
                        "tiles": tiles, "tillable": []},
           "farm": {}, "ui": {"isModal": False, "eventUp": False}}
    return obs, w


def check_pending_snapshot() -> None:
    print("[B] pending 快照 / resume 证据闸门（task-26/15/22）")
    run, w = new_run()
    obs7, _ = _water_obs(7)
    run.leftover_targets = {(60 + i, 10) for i in range(7)}
    snap = run._pending_snapshot(obs7)
    check("B3 7 格可执行快照", int(snap.get("executable") or 0) == 7,
          f"snap={ {k: snap.get(k) for k in ('ledger', 'guard', 'stalled', 'blocked', 'executable', 'unobserved', 'malformed')} }")
    claim7 = (int(snap["executable"]) == 0 and int(snap.get("malformed", 0)) == 0)
    check("B3b exec=7 ⇒ claim_exhausted 必 False（冬27 旧形态不可复现）", claim7 is False, "")
    run.leftover_targets = set()
    obs0, _ = _water_obs(0)
    snap0 = run._pending_snapshot(obs0)
    claim0 = (int(snap0["executable"]) == 0 and int(snap0.get("malformed", 0)) == 0)
    check("B3c exec=0/malformed=0 ⇒ claim_exhausted True", claim0 is True,
          f"snap0={snap0}")
    run.leftover_targets = {(60, 10), (70, 12)}
    obs_m, _ = _water_obs(1, malformed=1)
    snapm = run._pending_snapshot(obs_m)
    check("B3d 残缺 tile ⇒ malformed>0 ⇒ claim False",
          int(snapm.get("malformed") or 0) > 0 and (int(snapm["executable"]) == 0 and int(snapm.get("malformed", 0)) == 0) is False,
          f"snapm={ {k: snapm.get(k) for k in ('executable', 'unobserved', 'malformed')} }")
    ok_inv = (snap["ledger"] == snap["guard"] + snap["blocked"]
              and snap["guard"] == snap["executable"] + snap["unobserved"] + snap["malformed"])
    check("B3e 快照不变式 ledger=guard+blocked 且 guard=exec+unobs+malformed", ok_inv,
          f"ledger={snap['ledger']} guard={snap['guard']} exec={snap['executable']} unobs={snap['unobserved']} malformed={snap['malformed']}")


def _enclosed_obs(center=(60, 10), kinds=("tree", "tree", "tree", "tree"),
                  standable_side=None, omit_side=None):
    """造 5x5 全观测障碍：中心是目标格（weed、不可站），其余默认 tree（不可站）。

    kinds 按 (上/右/下/左) 覆盖四邻；standable_side = 第 N 个邻格可站；
    omit_side = 第 N 个邻格不观测（用来看"四邻没全覆盖"）。
    """
    dirs = ((0, -1), (1, 0), (0, 1), (-1, 0))
    grid = {}
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            t = (center[0] + dx, center[1] + dy)
            grid[t] = {"tile": [t[0], t[1]], "kind": "tree",
                       "standable": False, "actionable": True}
    grid[center] = {"tile": [center[0], center[1]], "kind": "weed",
                    "standable": False, "actionable": True}
    for i, (dx, dy) in enumerate(dirs):
        t = (center[0] + dx, center[1] + dy)
        if omit_side is not None and i == omit_side:
            grid.pop(t, None)
            continue
        if i < len(kinds):
            grid[t] = {"tile": [t[0], t[1]], "kind": kinds[i],
                       "standable": (i == standable_side), "actionable": True}
    obs = {"ok": True, "hasSaveLoaded": True, "worldSeq": 1,
           "player": {"name": "t", "location": "Farm", "tile": [62, 14],
                      "stamina": 270.0, "maxStamina": 270.0, "money": 0,
                      "inventory": [], "inventoryCount": 12},
           "location": {"name": "Farm", "isOutdoorFarm": True,
                        "tiles": list(grid.values()), "tillable": []},
           "farm": {}, "ui": {}}
    return obs


def check_enclosed() -> None:
    print("[B] 挡死格证据口径（task-27）")
    LR = fixtures()["LR"]
    obs = _enclosed_obs()
    check("B4 四邻全观测+都不可站+无可清障邻格 ⇒ enclosed", LR.LongRun._known_enclosed(obs, (60, 10)) is True, "")
    obs_part = _enclosed_obs(omit_side=2)   # 缺一个邻格（下）
    check("B4b 四邻没全观测 ⇒ 不判死（False）", LR.LongRun._known_enclosed(obs_part, (60, 10)) is False, "")
    obs_stand = _enclosed_obs(standable_side=1)
    check("B4c 有可站邻格 ⇒ 不判死（False）", LR.LongRun._known_enclosed(obs_stand, (60, 10)) is False, "")
    # frontier kind（weed）+ 乐观可站 ⇒ False
    obs_fr = _enclosed_obs(kinds=("tree", "weed", "tree", "tree"))
    # weed 邻格 (61,10) 自己够得着：(62,10) 是可站格（乐观口径）
    for rec in obs_fr["location"]["tiles"]:
        if rec["tile"] == [62, 10]:
            rec.update({"kind": "dirt", "standable": True, "plantable": True})
    check("B4d 可清障邻格且乐观可站 ⇒ 不判死（False）",
          LR.LongRun._known_enclosed(obs_fr, (60, 10)) is False, "")
    run, _ = new_run()
    run.encircled_day = set()
    kept = run._prefilter_known_enclosed("till_area", obs, [(60, 10)])
    ev = [e for e in run.entries if e.get("event") == "encircled"]
    check("B4e 预过滤剔出目标池 + encircled 留痕（prefilter=True、不进 unreachable）",
          kept == [] and (60, 10) in run.encircled_day and bool(ev) and ev[-1].get("prefilter") is True,
          f"kept={kept} entries={len(ev)}")


def check_sell_discipline() -> None:
    print("[B] 售材白名单（task-28）")
    FW = fixtures()["FW"]
    tables = {
        "SURPLUS_MATERIAL_IDS": set(getattr(FW, "SURPLUS_MATERIAL_IDS", set())),
        "SLOT_RELIEF_MATERIAL_IDS": set(getattr(FW, "SLOT_RELIEF_MATERIAL_IDS", set())),
        "SLOT_RELIEF_CROP_IDS": set(getattr(FW, "SLOT_RELIEF_CROP_IDS", set())),
        "SLOT_RELIEF_HIGH_VALUE_IDS": set(getattr(FW, "SLOT_RELIEF_HIGH_VALUE_IDS", set())),
        "SLOT_RELIEF_NEVER_SELL_IDS": set(getattr(FW, "SLOT_RELIEF_NEVER_SELL_IDS", set())),
    }
    sellable = tables["SURPLUS_MATERIAL_IDS"] | tables["SLOT_RELIEF_MATERIAL_IDS"] | \
        tables["SLOT_RELIEF_CROP_IDS"] | tables["SLOT_RELIEF_HIGH_VALUE_IDS"]
    hits = sorted(FORBIDDEN_SELL_QIDS & sellable)
    check("B5 十类禁售 qid 不在任何可卖表", not hits, f"tables={ {k: sorted(v) for k, v in tables.items()} } hits={hits}")
    check("B5b 材料表只剩 92/766", tables["SURPLUS_MATERIAL_IDS"] == {"92", "766"}
          and tables["SLOT_RELIEF_MATERIAL_IDS"] == {"92", "766"}, "")
    check("B5c 锭/升级材料永不卖（334-338/787）",
          {"334", "335", "336", "337", "338", "787"} <= tables["SLOT_RELIEF_NEVER_SELL_IDS"], "")
    # 动态：满包 + 含禁售项 ⇒ plan 不得挑它们
    TL = fixtures()["TL"]
    w = TL.FakeWorld(weeds=0, seeds=0, money=3264)
    w.inventory = [dict(x) for x in w.inventory] + [
        {"slot": 6, "id": "388", "qualifiedId": "(O)388", "name": "Wood", "stack": 5, "isTool": False},
        {"slot": 7, "id": "330", "qualifiedId": "(O)330", "name": "Clay", "stack": 3, "isTool": False},
        {"slot": 8, "id": "92", "qualifiedId": "(O)92", "name": "Sap", "stack": 4, "isTool": False},
    ]
    obs = w.obs()
    plan = FW.slot_relief_plan(obs, free_slots=0, free_slots_status="ok",
                               trigger_free_slots=1, max_stacks=10)
    qids = [str(x) for x in (plan.get("whitelist") or [])]
    for it in (plan.get("items") or []):
        if isinstance(it, dict) and it.get("qid") is not None:
            qids.append(str(it["qid"]))
    check("B5d 满包压力计划不含禁售建材（388/330）", not ({"388", "330"} & set(qids)),
          f"plan slots={qids} pressure={plan.get('pressure')} skip={plan.get('skipReason')!r}")
    info("B5e 计划里实际可卖叠", f"qids={qids}（Sap 92 属允许材料，但受 keep 约束）")
    # 动态：把"永不卖"锭/电池也放进背包 ⇒ 满包压力下 plan 不得挑它们（双保险）
    w2 = TL.FakeWorld(weeds=0, seeds=0, money=3264)
    w2.inventory = [dict(x) for x in w2.inventory] + [
        {"slot": 9, "id": "334", "qualifiedId": "(O)334", "name": "Copper Bar", "stack": 5, "isTool": False},
        {"slot": 10, "id": "787", "qualifiedId": "(O)787", "name": "Battery Pack", "stack": 2, "isTool": False},
    ]
    plan2 = FW.slot_relief_plan(w2.obs(), free_slots=0, free_slots_status="ok",
                                trigger_free_slots=1, max_stacks=10)
    qids2 = [str(x) for x in (plan2.get("whitelist") or [])]
    for it in (plan2.get("items") or []):
        if isinstance(it, dict) and it.get("qid") is not None:
            qids2.append(str(it["qid"]))
    bare2 = {re.sub(r"^\([A-Z]\)", "", q) for q in qids2}
    check("B5e 满包压力计划不含永不卖锭/电池（334/787）",
          not ({"334", "787"} & bare2), f"plan qids={qids2}")


def check_backpack_dynamic() -> None:
    print("[B] 背包升级对话购买（task-25 观测差分）")
    TL = fixtures()["TL"]

    def scenario(talk_mode="ok", purchase_mode="ok"):
        w = TL.FakeWorld(weeds=0, seeds=0, money=3264)
        w.talk_mode = talk_mode
        w.purchase_mode = purchase_mode
        w.inventory_capacity = 12
        run, _ = new_run(w)
        return w, run, fresh_rep()

    w, run, rep = scenario()
    ok = run._maybe_buy_backpack_upgrade(w.obs(), rep)
    buys = [e for e in run.entries if e.get("event") == "buy"]
    check("B6 成功=钱−2000 且容量 12→24",
          ok is True and w.money == 1264 and w.inventory_capacity == 24
          and rep.backpack_upgrade_ok is True and rep.backpack_capacity_after == 24
          and buys and buys[-1].get("ok") is True and buys[-1].get("source") == "backpack_dialogue",
          f"money={w.money} cap={w.inventory_capacity} rep_ok={rep.backpack_upgrade_ok}")

    w, run, rep = scenario(purchase_mode="money_unchanged")
    ok = run._maybe_buy_backpack_upgrade(w.obs(), rep)
    check("B6b 回执 ok 但钱没动 ⇒ 失败 money_not_deducted",
          ok is False and "money_not_deducted" in rep.backpack_upgrade_failures
          and w.inventory_capacity == 12, f"failures={rep.backpack_upgrade_failures}")

    w, run, rep = scenario(purchase_mode="capacity_unchanged")
    ok = run._maybe_buy_backpack_upgrade(w.obs(), rep)
    check("B6c 钱动了但容量没变 ⇒ 失败 capacity_not_changed",
          ok is False and "capacity_not_changed" in rep.backpack_upgrade_failures, f"failures={rep.backpack_upgrade_failures}")

    w, run, rep = scenario(purchase_mode="dismiss_new_day")
    ok = run._maybe_buy_backpack_upgrade(w.obs(), rep)
    check("B6d 差分窗口跨日 ⇒ money_diff_ambiguous 失败",
          ok is False and "money_diff_ambiguous" in rep.backpack_upgrade_failures, f"failures={rep.backpack_upgrade_failures}")

    for mode, code in (("response_missing", "response_not_found"),
                       ("response_ambiguous", "response_ambiguous"),
                       ("no_question", "dialogue_not_question"),
                       ("npc_not_found", "npc_not_found"),
                       ("no_action", "no_action")):
        w, run, rep = scenario(talk_mode=mode)
        ok = run._maybe_buy_backpack_upgrade(w.obs(), rep)
        check(f"B6e talk 形态 {mode} ⇒ 失败码 {code}",
              ok is False and code in rep.backpack_upgrade_failures and w.money == 3264,
              f"failures={rep.backpack_upgrade_failures} money={w.money}")


def check_csharp_talk() -> None:
    print("[B] task-33 talk 契约（源码面；运行时【无法判定】）")
    tk = read("mod/AgentFarm.Bridge/TalkSkill.cs")
    rules = read("mod/AgentFarm.Bridge/TalkRules.cs")
    prog = read("mod/AgentFarm.Bridge.Tests/Program.cs")
    check("B7 talk 不相邻不自走（not_adjacent + applied=false）",
          "CodeNotAdjacent" in tk and "Applied = false" in tk, "")
    check("B7b talk applied 但无 UI 证据 ⇒ not_supported（fail-closed）",
          "CodeNotSupported" in tk and "DecideCode" in tk, "")
    check("B7c 回执含 available（npc_not_found 时 ≤30 名）",
          "MaxAvailableNames = 30" in tk and "Available = available.Count" in tk, "")
    check("B8 C# 自检断言 talk 红线（禁 Money/MaxItems/increaseBackpackSize/SendInput）",
          "!talksText.Contains(\"Money =\")" in prog
          and "!talksText.Contains(\"MaxItems =\")" in prog
          and "!talksText.Contains(\".increaseBackpackSize(\")" in prog,
          "")
    check("B8b TalkRules 红线条原文（只调 checkAction/不改钱与背包）",
          "NPC.checkAction" in rules and "不改 Money/Items/MaxItems" in rules
          and "increaseBackpackSize" in rules, "")
    info("B8c talk 运行时 drop-in 冒烟", "离线未跑 dotnet 测试/未进游戏 ⇒ 【无法判定】（作者/Lead 报 97 断言）")


# ================================================================ C 段
def judge_inventory_unconditional() -> None:
    LR = fixtures()["LR"]
    f = LR.is_justified_end
    # 反例 1：有可执行格仍想以 inventory_blocked 收工
    bad = f("inventory_blocked", "inventory_blocked:背包满", pending_executable=2, malformed_tiles=0)
    check("C1 inventory_blocked 有可执行格 ⇒ 不得放行（False）", bad is False, "")


def judge_malformed_veto() -> None:
    LR = fixtures()["LR"]
    f = LR.is_justified_end
    check("C2 删 malformed 否决的等价行为（malformed=3 仍 False）",
          f("inventory_blocked", "inventory_blocked:x", pending_executable=0, malformed_tiles=3) is False, "")


def judge_resume_threshold() -> None:
    LR = fixtures()["LR"]
    f = LR.is_justified_end
    check("C3 resume_exhausted 门槛清空（exec>0）⇒ False",
          f("sleep", "resume_exhausted:x", pending_executable=9, malformed_tiles=0) is False, "")
    check("C3b resume_budget_exhausted 永不进白名单（即使 exec=0）",
          f("sleep", "resume_budget_exhausted:x", pending_executable=0, malformed_tiles=0) is False, "")


def judge_sell_bypass() -> None:
    src = read("brain/agentfarm/farmwork.py")
    longrun = read("brain/agentfarm/longrun.py")
    writes = []
    for pat in ("player.Money =", "player.Money -=", "player.Money +=",
                "player.Items.Add", "player.MaxItems =", ".increaseBackpackSize("):
        for file, text in (("farmwork", _code_only(src)), ("longrun", _code_only(longrun))):
            if pat in text:
                writes.append(f"{file}:{pat}")
    check("C4 生产代码无直写钱/物品/背包容量", not writes, f"hits={writes}")
    check("C4b 卖东西仍只走桥 sell（Mod Farm.shipItem）且无直改背包",
          "self.c.sell(" in _code_only(src) and "Farm.shipItem" in src, "")


def judge_loot_bound() -> None:
    src = read("brain/agentfarm/longrun.py")
    check("C5 清障丢失上界=5 且 clear 闸按剩余额度收窄",
          re.search(r"CLEAR_LOOT_LOSS_MAX_STEPS\s*=\s*5", src) is not None
          and "CLEAR_LOOT_LOSS_MAX_STEPS - int(self.loot_lost_steps_today)" in src,
          "")
    check("C5b loot_lost_steps 只作 info、不进 checks",
          '"loot_lost_steps"' not in src.split("rep.checks = {", 1)[1].split("}", 1)[0], "")


def judge_checks_pollution() -> None:
    src = read("brain/agentfarm/longrun.py")
    keys, where = _checks_keys_from_source(src)
    check("C6 checks 恰 10 键且序与基线一致", keys == list(CHECKS_BASELINE), f"{where}")
    check("C6b 新字段不在 checks（无 pending_malformed/loot_lost_*/backpack_*）",
          not any(k in (keys or []) for k in ("pending_malformed", "loot_lost_steps",
                                              "backpack_upgrade_ok", "relief_exhausted",
                                              "pending_executable")), "")


def judge_till_not_already() -> None:
    src = read("brain/agentfarm/longrun.py")
    check("C7 预过滤挡死格归 encircled（prefilter=True）而非 already",
          "prefilter=True" in src and "encircled" in src, "")
    check("C7b 判死格不回填 assigned 成功集合（already 只认 step 成功/跳过）",
          re.search(r'already\s*(\+?=|\+=).{0,80}', src) is not None, "")


def judge_unreachable_bound() -> None:
    old = repo_git("show", f"{PREV}:brain/agentfarm/longrun.py")
    new = read("brain/agentfarm/longrun.py")
    for name, text in (("0.7.45", old), ("0.7.46", new)):
        m = re.search(r"unreachable_bound = max\(5, [^\n]+", text)
        info(f"C8 {name} unreachable_bound", m.group(0) if m else "未找到")
    check("C8 界公式逐字未动",
          re.search(r"unreachable_bound = max\(5, int\(0\.2 \* bound_basis_steps\)\)", old) is not None
          and re.search(r"unreachable_bound = max\(5, int\(0\.2 \* bound_basis_steps\)\)", new) is not None, "")


def judge_bag_gate_evidence() -> None:
    src = read("brain/agentfarm/longrun.py")
    check("C9 满包闸只看可复核证据（free==0 且 exhausted）",
          "if free is None or int(free) > 0:" in src and "if not ev.get(\"exhausted\"):" in src, "")
    check("C9b 证据不可读 ⇒ 不闸（fail-open）而不是猜 0",
          'if free is None or int(free) > 0:' in src, "")


def judge_talk_no_cheat() -> None:
    tk = read("mod/AgentFarm.Bridge/TalkSkill.cs")
    bad = [p for p in ("Money =", "Money -=", "Money +=", "MaxItems =",
                       ".increaseBackpackSize(", "SendInput", "keyboardState", "mouseState")
           if p in tk]
    check("C10 talk 实现无作弊写入（钱/物品/背包/键鼠）", not bad, f"hits={bad}")
    check("C10b talk 只调 NPC.checkAction 且不替脑走路",
          "found.checkAction(who, loc)" in tk and "本技能不代走" in tk, "")
    check("C10c 成功判据是观测差分（不是进背包计数）",
          "capacity_not_changed" in read("brain/agentfarm/longrun.py")
          and "money_not_deducted" in read("brain/agentfarm/longrun.py"), "")


def judge_honest_exit_names() -> None:
    src = _code_only(read("brain/agentfarm/longrun.py"))
    for bad in ("stuck:回片区", "stuck:同一秒连发"):
        check(f"C11 收尾不再写 {bad}", bad not in src, "")
    check("C11b resume 无证据时改 budget 前缀而非冒充无目标",
          "resume_budget_exhausted:" in src, "")


# ================================================================ D 段
AUTHOR_SCRIPTS = [
    ("t25", "tests/_mutate_t25_dialogue.py", "TestTask25BackpackUpgrade", "4"),
    ("t26", "tests/_mutate_t26_budget.py", "TestTask26ResumeBudget", "3"),
    ("t27", "tests/_mutate_t27_enclosed.py", "TestTask27EnclosedBatch", "8"),
    ("t28", "tests/_mutate_t28_bag.py", "TestTask28BagEvidence", "5"),
]


def check_author_mutations() -> None:
    print("[D] 作者变异（冻结副本跑；自报 vs 实测）")
    out_path = REPO / "scratch" / "_t0746b_author_mut.txt"
    chunks: list[str] = []
    for tag, rel, target, claimed in AUTHOR_SCRIPTS:
        if not (ROOT / rel).exists():
            skip(f"D1 {tag} 脚本缺失", rel)
            continue
        proc = run_cmd([PY, str(ROOT / rel), "--from-worktree"], cwd=ROOT,
                       extra_env={"PYTHONUTF8": "1"})
        text = (proc.stdout or "") + (proc.stderr or "")
        chunks.append(f"===== {tag} {rel} (rc={proc.returncode}) =====\n{text}\n")
        m = re.search(r"(?:结论|结果)：(\d+)/(\d+) 条变异被杀；存活 (.+)", text)
        killed = int(m.group(1)) if m else -1
        total = int(m.group(2)) if m else -1
        survived = (m.group(3) if m else "").strip()
        baseline_ok = "基线" not in text or "基线不是绿的" not in text
        check(f"D1 {tag} 实测被杀 {killed}/{total}（自报 {claimed}/{total if total > 0 else claimed}）",
              baseline_ok and total > 0 and killed == total and survived in ("无", "（无）", ""),
              f"rc={proc.returncode} survived={survived!r}")
        out_path.write_text("\n".join(chunks), encoding="utf-8")
    info("D1 证据文件", str(out_path))


def check_my_mutations() -> None:
    print("[D] 我方变异实测（证据文件）")
    p = REPO / "scratch" / "_t0746b_my_mut.txt"
    if not p.exists():
        skip("D2 我方变异证据缺失（先跑 _t0746b_mutate.py）", str(p))
        return
    text = p.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"合计：(\d+)/(\d+) 条变异被杀；未杀 (\d+)", text)
    killed = int(m.group(1)) if m else -1
    total = int(m.group(2)) if m else -1
    survived_n = int(m.group(3)) if m else -1
    check("D2 我方变异全杀", total > 0 and killed == total and survived_n == 0,
          f"{killed}/{total}，未杀 {survived_n}")
    for line in text.splitlines():
        if re.match(r"\[(m31|m0746)", line):
            info("D2 " + line.strip()[:180], "")


# ================================================================ E 读数
def check_readings() -> None:
    print("[E] 读数（py_compile / 定向 / 全量）")
    files = ["brain/agentfarm/longrun.py", "brain/agentfarm/farmwork.py",
             "brain/agentfarm/bridge.py", "tests/test_longrun.py"]
    proc = run_cmd([PY, "-W", "error::SyntaxWarning", "-m", "py_compile", *files], cwd=ROOT)
    check("E1 py_compile -W error::SyntaxWarning rc=0", proc.returncode == 0,
          (proc.stderr or proc.stdout)[-300:])
    targets = ["tests.test_longrun.TestTask25BackpackUpgrade",
               "tests.test_longrun.TestTask26ResumeBudget",
               "tests.test_longrun.TestTask27EnclosedBatch",
               "tests.test_longrun.TestTask28BagEvidence"]
    proc = run_cmd([PY, "-m", "unittest", *targets], cwd=ROOT,
                   extra_env={"PYTHONPATH": str(ROOT / "brain")})
    out = (proc.stdout or "") + (proc.stderr or "")
    m = re.search(r"^Ran (\d+) tests?", out, re.M)
    ran = int(m.group(1)) if m else 0
    check("E2 四卡定向单测绿", ran > 0 and "\nOK" in out and proc.returncode == 0,
          f"Ran {ran}; rc={proc.returncode}")
    proc = run_cmd([PY, "-m", "unittest", "discover", "-s", "tests"], cwd=ROOT,
                   extra_env={"PYTHONPATH": str(ROOT / "brain")})
    out = (proc.stdout or "") + (proc.stderr or "")
    m = re.search(r"^Ran (\d+) tests?", out, re.M)
    ran = int(m.group(1)) if m else 0
    check("E3 冻结树全量单测绿（夹具已补；缺失会红）", ran > 0 and "\nOK" in out and proc.returncode == 0,
          f"Ran {ran}; rc={proc.returncode}")
    info("E3b 与 Lead 自报 1383 的差额", "冻结树读数见上；差额【无法判定】（工作树/冻结树夹具与未提交测试不同，不猜）")


# ================================================================ main
SECTIONS = {
    "A": [check_provenance, check_version, check_checks_and_fields, check_card_sources],
    "B": [check_ledger_replay, check_is_justified_dynamic, check_pending_snapshot,
          check_enclosed, check_sell_discipline, check_backpack_dynamic, check_csharp_talk],
    "C": [judge_inventory_unconditional, judge_malformed_veto, judge_resume_threshold,
          judge_sell_bypass, judge_loot_bound, judge_checks_pollution,
          judge_till_not_already, judge_unreachable_bound, judge_bag_gate_evidence,
          judge_talk_no_cheat, judge_honest_exit_names],
    "D": [check_author_mutations, check_my_mutations],
    "E": [check_readings],
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="A,B,C,D")
    ap.add_argument("--readings", action="store_true")
    args = ap.parse_args(argv)
    want = [x.strip().upper() for x in args.only.split(",") if x.strip()]
    print(f"T0746B_ROOT={ROOT}")
    print(f"COMMIT={COMMIT} PREV={PREV}\n")
    for sec in want:
        if sec == "E" and not args.readings:
            continue
        for fn in SECTIONS.get(sec, []):
            try:
                fn()
            except Exception as exc:  # noqa: BLE001 - 探针 crash 也要落成 FAIL，不静默
                check(f"{sec}:{fn.__name__} 探针异常", False,
                      f"{type(exc).__name__}: {exc}")
    ok = sum(1 for _, s, _ in RESULTS if s == "PASS")
    fail = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    sk = sum(1 for _, s, _ in RESULTS if s == "SKIP")
    inf = sum(1 for _, s, _ in RESULTS if s == "INFO")
    print(f"\n汇总：PASS={ok} FAIL={fail} SKIP={sk} INFO={inf}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
