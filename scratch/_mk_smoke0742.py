# -*- coding: utf-8 -*-
"""一次性转换脚本：scratch/smoke-0741.py → scratch/smoke-0742.py（0.7.42 版）。

不改 0741 原件；所有替换都带唯一性断言（replace 前 count 必须为 1，否则直接抛错）。
0.7.42 新增（Lead m04423 / `docs/_release-0.7.42.md` §3）：
  * 步 8 = 三条硬判据：8.1 冬季可验证性（≥1 天 verified=true + 旧守卫文案不得出现）
                     8.2① 清障「单发 tool_ineffective 就封格」必须为 0（合法放弃 = tool_ineffective_bound + calls>=2）
                     8.2② farm.trees 日降幅 > 2（用 observe?detail=full 前后差；wait/launch 期间可选抓快照）
                     8.2③ deferred_by_budget 理由必须含「预算 N / 已砍 M」
  * 参数化：--tag / --capture-observe / --observe-every；journal 与产物默认走 logs/longrun-smoke-0742.*
  * 沿用：步 3 A2、步 6 只认 save-chain-check verdict、harvest 冬季【无法判定·无作物】
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / "smoke-0741.py"
DST = HERE / "smoke-0742.py"


def rep(src: str, old: str, new: str, tag: str) -> str:
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"[transform] 锚点 '{tag}' 命中 {n} 次（必须 1 次）\n---\n{old[:400]}\n---")
    print(f"[transform] OK {tag}")
    return src.replace(old, new)


def main() -> int:
    src = SRC.read_text(encoding="utf-8")

    # 1) 全局改名（journal/产物/用法示例）
    src = src.replace("smoke-0741", "smoke-0742")
    src = rep(src, 'EXPECT_VERSION = "0.7.41"', 'EXPECT_VERSION = "0.7.42"', "EXPECT_VERSION")

    # 2) 顶部 docstring 标题 + 步 8 说明
    src = rep(
        src,
        '"""0.7.41 装机后「7 步真机冒烟」编排骨架（machine-runner 待命期准备，可提前 py_compile 自测）。',
        '"""0.7.42 装机后「7 步真机冒烟 + 步 8 的 0.7.42 三条硬判据」编排骨架（由 smoke-0741.py 升级，可提前 py_compile 自测）。',
        "docstring-title")
    src = rep(
        src,
        "；`tools/verify-run3.py` 对 §8 只出 info\n",
        "；`tools/verify-run3.py` 对 §8 只出 info\n"
        "  8. **0.7.42 三条硬判据**（`docs/_release-0.7.42.md` §3，Lead m04423）：\n"
        "     8.1 **冬季可验证性**：日报告里**至少 1 天 `verified=true`**（冬 0 作物时应是 `ended_by=night`/`no_work`、`day_justified=true`），"
        "且**不得再出现** `stuck:…守卫仍说还有活：…耕地空着（手上有 N 粒种子）⇒ 该去种` 这条文案（出现即 FAIL，task-240 验收面）\n"
        "     8.2 **清障吞吐**：①`clear_area` 的 blocked 里「单发 `tool_ineffective` 就封格」条数 = **0**（合法放弃必须 reason 含 `tool_ineffective_bound` 且 calls≥2）；"
        "②`farm.trees` **日降幅 > 2 棵**（`observe?detail=full` 前后差）；③`deferred_by_budget` 理由必须含「预算 N / 已砍 M」\n"
        "     8.3 **沿用 0.7.41**：步 3 A2（有界多次 `use_tool`）、步 6 只认 `save-chain-check --freeze-smapi` verdict、`harvest` 冬季记【无法判定·无作物】不改判\n",
        "docstring-step8")

    # 3) PLAN 追加步 8
    src = rep(
        src,
        '    (7, "analyzer §8 无红 + `missed:intent_no_reason:*` 必消失 + slot_relief 带 demand/target_free/reached 且≥1 天 harvest ok>0 + verify-run3 对 §8 只 info"),\n]',
        '    (7, "analyzer §8 无红 + `missed:intent_no_reason:*` 必消失 + slot_relief 带 demand/target_free/reached 且≥1 天 harvest ok>0 + verify-run3 对 §8 只 info"),\n'
        '    (8, "0.7.42 三条硬判据：8.1 冬季≥1 天 verified 且旧守卫文案 0 次 / 8.2① 单发 tool_ineffective 封格 = 0 / 8.2② farm.trees 日降幅>2 / 8.2③ 预算理由含「预算 N/已砍 M」"),\n]',
        "PLAN-step8")
    src = rep(src, '    print(f"0.7.41 真机冒烟 7 步（期望版本 {EXPECT_VERSION}）")',
              '    print(f"0.7.42 真机冒烟 8 步（期望版本 {EXPECT_VERSION}）")', "plan-title")
    src = rep(src,
              '    print("phase 编排：pre(1-3) → launch(4) → wait(4 完成) → post(5-7，建议带 --freeze-smapi 先冻结 SMAPI)")',
              '    print("phase 编排：pre(1-3) → launch(4) → wait(4 完成) → post(5-8，建议带 --freeze-smapi 先冻结 SMAPI)")',
              "plan-phase")

    # 4) 观测抓取 helper（步 8.2② 需要 farm.trees 逐日差）
    obs_helpers = '''
# ---------------------------------------------------------------- 观测抓取（步 8.2② 用；只读）
def _obs_day_key(obs: dict) -> str | None:
    c = obs.get("clock") or {}
    if not c:
        return None
    return f"{c.get('season')}{c.get('day')}"


def _capture_observe(tag: str) -> dict | None:
    """只读抓一份 `observe?detail=full` 落 `scratch/smoke-0742-observe-<day>-<tag>.json`（不写世界）。"""
    try:
        obs = bridge().observe(detail="full")
    except Exception as exc:  # noqa: BLE001
        print(f"  [obs] 抓取失败：{type(exc).__name__}: {exc}")
        return None
    day = _obs_day_key(obs) or "unknown"
    p = HERE / f"smoke-0742-observe-{day}-{tag}.json"
    try:
        p.write_text(json.dumps({"captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                 "tag": tag, "observe": obs}, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        print(f"  [obs] 写盘失败：{exc}")
        return None
    return {"path": p.name, "day": day, "trees": (obs.get("farm") or {}).get("trees")}


'''
    src = rep(src, "\n# ---------------------------------------------------------------- 4：1 日长跑（脱离式）\n",
              obs_helpers + "# ---------------------------------------------------------------- 4：1 日长跑（脱离式）\n",
              "obs-helpers")

    # 5) launch 阶段抓基线
    src = rep(
        src,
        '    if not launcher.exists():\n        rec["verdict"], rec["reason"] = "无法判定", f"起跑器不存在：{launcher}"\n        return rec\n',
        '    if not launcher.exists():\n        rec["verdict"], rec["reason"] = "无法判定", f"起跑器不存在：{launcher}"\n        return rec\n'
        '    if getattr(args, "capture_observe", False):\n'
        '        ob = _capture_observe("t0")\n'
        '        rec["evidence"]["obs_baseline"] = None if ob is None else ob\n'
        '        if ob:\n'
        '            print(f"  [obs] 起跑前基线 {ob[\'path\']} day={ob[\'day\']} trees={ob[\'trees\']}")\n',
        "launch-obs-baseline")

    # 6) wait 阶段周期抓观测
    src = rep(src, "    deadline = time.time() + args.wait_minutes * 60\n    last = None\n",
              "    deadline = time.time() + args.wait_minutes * 60\n    last = None\n"
              "    next_obs = 0.0\n", "wait-next-obs")
    src = rep(
        src,
        '        if cur != last:\n            print(f"  [wait] alive={alive} journal={n}行 last={last_ev} finish={\'有\' if fin else \'无\'}")\n            last = cur\n',
        '        if cur != last:\n            print(f"  [wait] alive={alive} journal={n}行 last={last_ev} finish={\'有\' if fin else \'无\'}")\n            last = cur\n'
        '        if getattr(args, "capture_observe", False) and time.time() >= next_obs:\n'
        '            ob = _capture_observe(f"{int(time.time()) % 100000:05d}")\n'
        '            if ob:\n'
        '                print(f"  [obs] {ob[\'path\']} day={ob[\'day\']} trees={ob[\'trees\']}")\n'
        '            next_obs = time.time() + max(30.0, float(args.observe_every))\n',
        "wait-obs-capture")
    src = rep(src,
              '    rec["evidence"] = {"pid": pid, "journal_lines": n, "last_event": last_ev, "finish": fin}',
              '    rec["evidence"] = {"pid": pid, "journal_lines": n, "last_event": last_ev, "finish": fin,\n'
              '                       "obs_files": len(list(LOGS.glob("smoke-0742-observe-*.json")))}',
              "wait-evidence-obs")

    # 7) 步 8 实现
    step8_code = '''
# ---------------------------------------------------------------- 8：0.7.42 三条硬判据
GUARD_PLANT_PAT = re.compile(r"耕地空着（手上有\\s*\\d+\\s*粒种子）⇒\\s*该去种")


def _step8_winter(recs: list[dict]) -> dict:
    """8.1 冬季可验证性：≥1 天 verified=true，且旧「该去种」守卫文案不得再出现（task-240 验收面）。"""
    ends = [r for r in recs if r.get("event") == "day_end"]
    verified = [r.get("day") for r in ends if r.get("verified") is True]
    guard_hits = []
    for r in recs:
        blob = json.dumps(r, ensure_ascii=False)
        if GUARD_PLANT_PAT.search(blob):
            guard_hits.append({"event": r.get("event"), "day": r.get("day"), "t": r.get("t")})
    out: dict = {"day_end": len(ends), "verified_days": verified,
                 "guard_text_hits": guard_hits[:5], "guard_text_hits_total": len(guard_hits)}
    if not ends:
        out.update(status="无法判定", reason="账本里没有 day_end ⇒ 冬季可验证性无法判定")
    elif guard_hits:
        out.update(status="FAIL", reason=(f"旧守卫文案「耕地空着（手上有 N 粒种子）⇒ 该去种」仍出现 "
                                          f"{len(guard_hits)} 次（task-240 验收面未过）：{guard_hits[:2]}"))
    elif not verified:
        out.update(status="FAIL", reason=f"{len(ends)} 个日报告里没有一天 verified=true（冬季必须能验证）")
    else:
        out.update(status="PASS", reason=f"{len(verified)}/{len(ends)} 天 verified=true（{verified}），旧守卫文案 0 次")
    return out


def _step8_clear_illegal(recs: list[dict]) -> dict:
    """8.2① 清障：单发 tool_ineffective 就封格 = 0；合法放弃 = reason 含 tool_ineffective_bound 且 calls>=2。"""
    illegal: list[dict] = []
    insufficient: list[dict] = []
    legal: list[dict] = []
    for r in recs:
        if r.get("event") != "blocked":
            continue
        blob = json.dumps(r, ensure_ascii=False)
        if "tool_ineffective" not in blob:
            continue
        m = re.search(r'"calls"\\s*:\\s*(\\d+)', blob)
        calls = int(m.group(1)) if m else None
        item = {"day": r.get("day"), "t": r.get("t"), "zone": r.get("zone"),
                "tile": r.get("tile") or r.get("tiles"), "calls": calls}
        if "tool_ineffective_bound" not in blob:
            illegal.append(item)
        elif calls is None or calls < 2:
            insufficient.append(item)
        else:
            legal.append(item)
    out: dict = {"blocked_tool_ineffective": len(illegal) + len(insufficient) + len(legal),
                 "illegal_single_shot": illegal[:5], "illegal_total": len(illegal),
                 "bound_without_calls_or_lt2": insufficient[:5], "insufficient_total": len(insufficient),
                 "legal_bound_giveup": legal[:5], "legal_total": len(legal)}
    if illegal:
        out.update(status="FAIL", reason=(f"{len(illegal)} 条 blocked 是「单发 tool_ineffective 就封格」"
                                          f"（task-241 验收面未过）：{illegal[:2]}"))
    elif insufficient:
        out.update(status="无法判定", reason=(f"{len(insufficient)} 条 blocked 带 bound 但 calls 缺失/<2 "
                                             f"⇒ 无法判定是否合法放弃：{insufficient[:2]}"))
    elif not legal:
        out.update(status="无法判定", reason="整跑没有 tool_ineffective 类 blocked ⇒ 该判据本批无读数（缺失≠通过）")
    else:
        out.update(status="PASS", reason=f"{len(legal)} 条 tool_ineffective 类 blocked 全部是 bound 且 calls>=2")
    return out


def _load_obs_doc(path: Path) -> dict | None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    o = doc.get("observe") if isinstance(doc.get("observe"), dict) else doc
    for _ in range(3):
        if isinstance(o, dict) and isinstance(o.get("observe"), dict):
            o = o["observe"]
        else:
            break
    return o if isinstance(o, dict) and isinstance(o.get("clock"), dict) else None


def _step8_trees(obs_files: list[Path]) -> dict:
    """8.2② 清障吞吐：farm.trees 日降幅 > 2 棵（只用 observe?detail=full 的全场计数）。"""
    rows: list[dict] = []
    for p in sorted(obs_files):
        o = _load_obs_doc(p)
        if not o:
            continue
        trees = (o.get("farm") or {}).get("trees")
        if not isinstance(trees, int):
            continue
        rows.append({"path": p.name, "day": _obs_day_key(o), "trees": trees,
                     "worldSeq": o.get("worldSeq")})
    if not rows:
        return {"observations": 0, "status": "无法判定",
                "reason": ("没有可用的 observe?detail=full 快照（farm.trees 是全场计数，账本 day_end 里没有）"
                           "⇒ 清障吞吐无法判定（缺失≠通过）；wait/launch 请带 --capture-observe")}
    per_day: dict[str, list[dict]] = {}
    for r in rows:
        per_day.setdefault(str(r["day"]), []).append(r)
    deltas: dict[str, dict] = {}
    for day, rr in sorted(per_day.items()):
        if len(rr) < 2:
            continue
        deltas[day] = {"first": rr[0]["trees"], "last": rr[-1]["trees"],
                       "delta": rr[-1]["trees"] - rr[0]["trees"], "n": len(rr)}
    out: dict = {"observations": len(rows), "days_with_two_obs": len(deltas), "per_day_delta": deltas,
                 "interpretation": ("日降幅 = 当天最后一份 − 当天第一份（跨天看 absolute：first/last）；"
                                    "PASS 口径 = 至少一天降幅 ≥3 棵（即 >2 棵），全 <3 才 FAIL")}
    if not deltas:
        out.update(status="无法判定",
                   reason=f"有 {len(rows)} 份观测但没有一天有 ≥2 份同一天快照 ⇒ 算不出日降幅")
        return out
    best = min(v["delta"] for v in deltas.values())
    out["best_delta"] = best
    if best <= -3:
        out.update(status="PASS", reason=f"至少一天 farm.trees 日降幅 {best} 棵（>2 棵）：{deltas}")
    else:
        out.update(status="FAIL", reason=f"所有天 farm.trees 日降幅都 ≤2 棵（最好 {best}）：{deltas}")
    return out


def _step8_budget(recs: list[dict]) -> dict:
    """8.2③ deferred_by_budget 理由必须含「预算 N / 已砍 M」。"""
    evs = [r for r in recs if r.get("event") == "deferred_by_budget"]
    if not evs:
        return {"count": 0, "status": "无法判定",
                "reason": "整跑没有 deferred_by_budget 事件 ⇒ 预算理由文案本批无读数（缺失≠通过）"}
    bad: list[dict] = []
    for r in evs:
        blob = json.dumps(r, ensure_ascii=False)
        if not (re.search(r"预算\\s*\\d+", blob) and re.search(r"已砍\\s*\\d+", blob)):
            bad.append({"day": r.get("day"), "t": r.get("t"), "blob": blob[:220]})
    out: dict = {"count": len(evs), "bad": bad[:5], "bad_total": len(bad)}
    if bad:
        out.update(status="FAIL",
                   reason=f"{len(bad)}/{len(evs)} 条 deferred_by_budget 的理由缺「预算 N / 已砍 M」：{bad[:2]}")
    else:
        out.update(status="PASS", reason=f"{len(evs)} 条 deferred_by_budget 理由都含「预算 N / 已砍 M」")
    return out


def step8(rec: dict, args) -> dict:
    journal = Path(args.journal) if getattr(args, "journal", None) else SMOKE_JOURNAL
    if not journal.exists():
        rec["verdict"], rec["reason"] = "无法判定", f"账本不存在：{journal}"
        return rec
    recs = _journal_records(journal)
    w = _step8_winter(recs)
    c = _step8_clear_illegal(recs)
    t = _step8_trees(sorted(LOGS.glob("smoke-0742-observe-*.json")))
    b = _step8_budget(recs)
    rec["evidence"] = {"winter": w, "clear_throughput": c, "trees": t, "budget_reason": b,
                       "inherit_0741": ("步 3 A2 / 步 6 只认 save-chain-check verdict / harvest 冬季【无法判定·无作物】"
                                        "—— 本步未改动这三条")}
    pairs = [("8.1 冬季可验证性", w), ("8.2① 清障单发封格", c),
             ("8.2② farm.trees 日降幅", t), ("8.2③ 预算理由", b)]
    fails = [(k, v["reason"]) for k, v in pairs if v.get("status") == "FAIL"]
    undet = [(k, v["reason"]) for k, v in pairs if v.get("status") == "无法判定"]
    if fails:
        rec["verdict"], rec["reason"] = "FAIL", "；".join(f"{k}：{why}" for k, why in fails)
    elif undet:
        rec["verdict"], rec["reason"] = "无法判定", "；".join(f"{k}：{why}" for k, why in undet)
    else:
        rec["verdict"] = "PASS"
        rec["reason"] = "；".join(f"{k} ✅" for k, _v in pairs)
    return rec


'''
    src = rep(src, "\n# ---------------------------------------------------------------- 环境体检 / 计划\n",
              step8_code + "# ---------------------------------------------------------------- 环境体检 / 计划\n",
              "step8-code")

    # 8) main() 接线
    src = rep(src, "    ap.add_argument(\"--journal\", default=str(SMOKE_JOURNAL))",
              "    ap.add_argument(\"--journal\", default=None, help=\"账本路径（默认 logs/longrun-<tag>.jsonl）\")",
              "arg-journal")
    src = rep(src, "    ap.add_argument(\"--json\", dest=\"json_out\", default=str(HERE / \"smoke-0742.json\"))",
              "    ap.add_argument(\"--json\", dest=\"json_out\", default=None, help=\"结果 JSON（默认 scratch/<tag>.json）\")",
              "arg-json")
    src = rep(src, "    ap.add_argument(\"--wait-minutes\", type=float, default=40.0)",
              "    ap.add_argument(\"--wait-minutes\", type=float, default=40.0)\n"
              "    ap.add_argument(\"--tag\", default=\"smoke-0742\", help=\"产物前缀（默认 smoke-0742）\")\n"
              "    ap.add_argument(\"--capture-observe\", dest=\"capture_observe\", action=\"store_true\",\n"
              "                    help=\"launch/wait 期间只读抓 observe?detail=full（步 8.2② 需要 farm.trees 逐日差）\")\n"
              "    ap.add_argument(\"--observe-every\", type=float, default=120.0, help=\"抓观测间隔秒（默认 120）\")",
              "arg-new")
    src = rep(
        src,
        '    SMOKE_JOURNAL = Path(args.journal)\n    SMOKE_GAPS = SMOKE_JOURNAL.with_name(SMOKE_JOURNAL.stem + "-gaps.json")\n    global NO_CROPS\n    NO_CROPS = bool(args.no_crops)',
        '    global NO_CROPS, SMOKE_SMAPI, SMOKE_SAVECHAIN_JSON\n'
        '    SMOKE_JOURNAL = Path(args.journal) if args.journal else LOGS / f"longrun-{args.tag}.jsonl"\n'
        '    SMOKE_GAPS = SMOKE_JOURNAL.with_name(SMOKE_JOURNAL.stem + "-gaps.json")\n'
        '    SMOKE_SMAPI = LOGS / f"{args.tag}-smapi-window.txt"\n'
        '    SMOKE_SAVECHAIN_JSON = HERE / f"{args.tag}-save-chain.json"\n'
        '    args.json_out = args.json_out or str(HERE / f"{args.tag}.json")\n'
        '    NO_CROPS = bool(args.no_crops)',
        "main-tag-globals")
    src = rep(src, '        if want & {5, 6, 7}:', '        if want & {5, 6, 7, 8}:', "phase-want")
    src = rep(src, '    out_json = HERE / "smoke-0742-save-chain.json"',
              '    out_json = SMOKE_SAVECHAIN_JSON', "savechain-json")
    src = rep(src,
              "        recs = [step5(step_record(5, PLAN[4][1])), step6(step_record(6, PLAN[5][1]), args),\n                step7(step_record(7, PLAN[6][1]))]",
              "        recs = [step5(step_record(5, PLAN[4][1])), step6(step_record(6, PLAN[5][1]), args),\n"
              "                step7(step_record(7, PLAN[6][1])), step8(step_record(8, PLAN[7][1]), args)]",
              "post-step8")
    src = rep(src, "    for step in range(1, 8):", "    for step in range(1, 9):", "cumulative-range")

    DST.write_text(src, encoding="utf-8")
    print(f"[transform] 已写 {DST}（{len(src.splitlines())} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
