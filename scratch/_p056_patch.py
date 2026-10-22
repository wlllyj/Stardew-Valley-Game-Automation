p = 'brain/agentfarm/longrun.py'
s = open(p, encoding='utf-8').read()
old = '''                obs = self._snap()
                continue
            if task in STAGE_ACTION:'''
new = '''                obs = self._snap()
                continue
            if task == "buy":
                changed = self._preconditions(obs, rep)
                if changed:
                    try:
                        obs = self._snap()
                    except Exception:
                        pass
                self._journal("economy_action", kind="buy", changed=bool(changed))
                self._record_intent(intent, task=task,
                                    executed_steps=1 if changed else 0,
                                    reasons={} if changed else {"unknown_evidence": 1},
                                    note="buy 由 _preconditions 流程执行（游戏入口 ShopMenu.tryToPurchaseItem）")
                acted = changed or acted
                continue
            if task == "upgrade_tool":
                st = None
                try:
                    mv = self.worker.ensure_location("Blacksmith", timeout_ms=30000)
                    if getattr(mv, "ok", False):
                        obs = self._snap()
                    st = self.worker.upgrade_tool("axe", timeout_ms=60000)
                except Exception as exc:  # noqa: BLE001
                    self._journal("economy_action", kind="upgrade_tool", ok=False,
                                  reason="exception:" + type(exc).__name__)
                changed = bool(getattr(st, "ok", False))
                if st is not None:
                    self._journal("economy_action", kind="upgrade_tool", ok=changed,
                                  reason=getattr(st, "reason", ""),
                                  before=getattr(st, "before", None),
                                  after=getattr(st, "after", None))
                self._record_intent(intent, task=task,
                                    executed_steps=1 if changed else 0,
                                    reasons={} if changed else {"unknown_evidence": 1},
                                    note="upgrade_tool " + ("ok" if changed else "no_effect"))
                acted = changed or acted
                obs = self._snap()
                continue
            if task in STAGE_ACTION:'''
assert old in s, 'anchor not found'
s = s.replace(old, new, 1)
open(p, 'w', encoding='utf-8').write(s)
print('done')
