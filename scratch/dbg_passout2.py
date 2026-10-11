import sys
sys.path.insert(0, "brain")
sys.path.insert(0, ".")
from tests.test_longrun import FakeWorld, FakeClient, make_run

w = FakeWorld(weeds=4, seeds=10, money=500)
run = make_run(w, target_days=1)
print("factory before:", run.client_factory)


class PassingOut(FakeClient):
    def __init__(self, world):
        super().__init__(world)
        self.n = 0

    def observe(self, detail="summary", *, timeout=None):
        print("  >>> PassingOut.observe called", detail)
        return super().observe(detail, timeout=timeout)


run.client_factory = lambda: PassingOut(w)
print("factory after :", run.client_factory)
print("has attr _client_factory?", hasattr(run, "_client_factory"),
      getattr(run, "_client_factory", None))
code = run.run()
print("code =", code, "days =", [(d.day_key, d.ended_by) for d in run.days],
      "observed client type =", type(run.client).__name__)
