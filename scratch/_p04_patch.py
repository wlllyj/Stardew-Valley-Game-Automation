p = 'tools/verify-run3.py'
s = open(p, encoding='utf-8').read()
old = '        "strict_problem_count": len(problems) + len(history_problems),\n'
new = old + '''        # P0-4 双轨（仅呈现，不参与 rc）：empty_day 单列，不计入严格口径。
        "empty_days": [d["key"] for d in days if not _day_non_empty(d)],
        "non_empty_day_count": sum(1 for d in days if _day_non_empty(d)),
'''
assert old in s, 'anchor not found'
s = s.replace(old, new, 1)
open(p, 'w', encoding='utf-8').write(s)
print('done')
