p = 'brain/agentfarm/longrun.py'
s = open(p, encoding='utf-8').read()
s = s.replace('                self._journal("economy_action", kind="buy", changed=bool(changed))\n',
              '')
s = s.replace('                    self._journal("economy_action", kind="upgrade_tool", ok=False,\n                                  reason="exception:" + type(exc).__name__)\n',
              '                    self._journal("upgrade_tool", ok=False, code="exception", reason="exception:" + type(exc).__name__)\n')
s = s.replace('                    self._journal("economy_action", kind="upgrade_tool", ok=changed,\n                                  reason=getattr(st, "reason", ""),\n                                  before=getattr(st, "before", None),\n                                  after=getattr(st, "after", None))\n',
              '                    self._journal("upgrade_tool", ok=changed, code=getattr(st, "code", ""), reason=getattr(st, "reason", ""),\n                                  before=getattr(st, "before", None), after=getattr(st, "after", None))\n')
open(p, 'w', encoding='utf-8').write(s)
print('done')
# verify no economy_action remains
print('remaining economy_action:', s.count('economy_action'))
