# -*- coding: utf-8 -*-
"""产品旁观审计：逐日 LLM 意图 -> 校验/执行结果 -> review 笔记。只读。"""
import json, sys, collections

path = sys.argv[1]
OUT = open(sys.argv[2], 'w', encoding='utf-8') if len(sys.argv) > 2 else None

def print(*a, **kw):  # noqa: A001
    s = ' '.join(str(x) for x in a)
    if OUT:
        OUT.write(s + '\n')
    else:
        sys.stdout.write(s + '\n')

rows = []
with open(path, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        line = line.strip()
        if line:
            rows.append((i, json.loads(line)))

cur = None
days = collections.OrderedDict()
for i, r in rows:
    d = r.get('day') or r.get('day_key')
    if d:
        cur = tuple(d)
    key = cur or ('?', '?', 0)
    days.setdefault(key, []).append((i, r))

for day, items in days.items():
    label = f'{day[1]} {day[2]}'
    print('=' * 78)
    print(f'DAY {label}  events={len(items)}')
    llm_ids = set()
    llm_dec = []
    det_n = 0
    for i, r in items:
        if r.get('event') != 'decision':
            continue
        if r.get('source') == 'llm' or r.get('llm') is True:
            llm_dec.append((i, r))
            for p in r.get('plans') or []:
                llm_ids.add(str(p.get('intent_id')))
        else:
            det_n += 1
    for i, r in llm_dec:
        print(f'  [LLM 决策 L{i}] boundary={r.get("boundary")} zone={r.get("zone")} '
              f'problems={r.get("problems")} fallback={r.get("fallback")} truncated={r.get("truncated")}')
        for p in r.get('plans') or []:
            it = next((x for x in r.get('intents') or [] if x.get('task') == p.get('task')
                       and x.get('area_hint') == p.get('area_hint')), {})
            print(f'      {p.get("intent_id")} task={p.get("task")} area={p.get("area_hint")}')
            print(f'          reason={it.get("reason")}')
    print(f'  当天 decision 总数={len(llm_dec) + det_n}（LLM {len(llm_dec)} / 确定性 {det_n}）')
    # verdicts split
    vt = collections.Counter()
    llm_v = collections.Counter()
    cancels = collections.Counter()
    for i, r in items:
        if r.get('event') != 'intent_verdict':
            continue
        for v in r.get('verdicts') or []:
            vt[v.get('verdict')] += 1
            if str(v.get('intent_id')) in llm_ids:
                llm_v[v.get('verdict')] += 1
                if v.get('verdict') == 'cancel':
                    cancels[v.get('reason')] += 1
    print(f'  intent_verdict 合计={dict(vt)}；其中 LLM 意图={dict(llm_v)}')
    for k, v in cancels.most_common():
        print(f'      LLM 意图被取消 x{v}: {k}')
    # outcomes
    oc = collections.Counter()
    for i, r in items:
        if r.get('event') == 'outcome':
            oc[(r.get('kind'), r.get('terminal'), r.get('postcondition_met'))] += 1
    print('  outcome 分布:')
    for k, v in oc.most_common():
        print(f'      x{v}: kind={k[0]} terminal={k[1]} post={k[2]}')
    # review/policy/day_end
    for i, r in items:
        e = r.get('event')
        if e == 'policy':
            print(f'  policy L{i}: {r.get("note")} intents={r.get("intents")}')
        if e == 'review_llm':
            print(f'  review_llm L{i}（{len(r.get("notes") or [])} 条）:')
            for n in r.get('notes') or []:
                print(f'      - {n}')
        if e == 'review_llm_failed':
            print(f'  review_llm_failed L{i}: {json.dumps({k: v for k, v in r.items() if k not in ("event",)}, ensure_ascii=False)[:300]}')
    for i, r in items:
        if r.get('event') != 'day_end':
            continue
        chk = r.get('checks') or {}
        print(f'  DAY_END L{i}: ended_by={r.get("ended_by")} verified={r.get("verified")} '
              f'day_justified={chk.get("day_justified")} slept={chk.get("slept_by_us")}')
        print(f'      ended_reason={r.get("ended_reason")}')
        print(f'      steps_ok={r.get("steps")} skipped={r.get("skipped_steps")} failed={r.get("failed_steps")} '
              f'plot_pending={r.get("plot_pending")} unreachable={r.get("unreachable")} refused={r.get("refused")}')
        print(f'      checks={chk}')
        print(f'      stages={[(s.get("stage"), s.get("tiles"), s.get("ok"), s.get("failed"), s.get("unreachable")) for s in (r.get("stages") or [])][-4:]}')
        print(f'      stamina_budget={json.dumps(r.get("stamina_budget") or {}, ensure_ascii=False)[:300]}')
    # 其它关键事件
    for i, r in items:
        if r.get('event') in ('deal', 'buy', 'ship', 'sell', 'tool_upgrade', 'tool_upgrade_skipped',
                              'upgrade', 'seed_gate', 'no_seed_for_sale', 'seed_unavailable_today',
                              'inventory_blocked', 'slot_relief_noted', 'plot_exhausted',
                              'stamina_deferred', 'crop_gate', 'money'):
            print(f'  {r.get("event")} L{i}: ' + json.dumps({k: v for k, v in r.items() if k not in ('event', 'day', 'note')}, ensure_ascii=False)[:400])
