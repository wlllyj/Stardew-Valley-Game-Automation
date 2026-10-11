import sys
sys.path.insert(0, "brain")
sys.path.insert(0, ".")
import unittest

from tests.test_longrun import FakeWorld, FakeClient, make_run


class PassingOut(FakeClient):
    def __init__(self, world):
        super().__init__(world)
        self.n = 0

    def observe(self, detail="summary", *, timeout=None):
        obs = super().observe(detail, timeout=timeout)
        self.n += 1
        if self.n == 3:
            self.w.day += 1
            self.w.time_of_day = 600
            print(f"  [注入 pass-out] n={self.n} day->{self.w.day}")
            return self.w.obs()
        print(f"  [observe] n={self.n} day={self.w.day}")
        return obs


w = FakeWorld(weeds=4, seeds=10, money=500)
run = make_run(w, target_days=1)
run.client_factory = lambda: PassingOut(w)
run.max_days = 1
print("max_days =", run.max_days)
code = run.run()
print("code =", code)
print("days =", [(d.day_key, d.ended_by, d.verified, d.checks) for d in run.days])
for e in run.entries:
    if e.get("event") in ("day_start", "day_end", "day_cap", "no_day_progress", "pass_out", "sleep"):
        print("  journal:", e)
