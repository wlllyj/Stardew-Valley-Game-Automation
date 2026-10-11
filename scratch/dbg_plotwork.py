"""一次性排查：w2 有未浇作物的那格为什么没被 _plot_has_work 认出来。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "brain"))
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tests.test_longrun import FakeWorld, FakeWorker, make_run  # noqa: E402
from agentfarm.farmwork import FarmWorker  # noqa: E402

w2 = FakeWorld(weeds=0, seeds=0, money=0)
w2.dirt.add((60, 10))
w2.crops[(60, 10)] = {"watered": False, "ripe": False}
run2 = make_run(w2)
run2.worker = FakeWorker(w2)
obs = w2.obs()
print("tiles[]:", obs["location"]["tiles"])
print("tillable[]:", obs["location"]["tillable"])
print("tiles_of keys:", sorted(FarmWorker.tiles_of(obs)))
cands = run2._plot_candidates(obs)
print("候选数:", len(cands))
for c in cands:
    print("  zone", c.get("zone"), "anchor", c.get("anchor"), "n", len(c["tiles"]),
          "tiles", c["tiles"], "note", c.get("note"))
    print("    has_work =", run2._plot_has_work(obs, c["tiles"]))
zones = run2._zones(obs)
print("zones:", [(z.name, z.bounds, z.tillable, z.blockers) for z in zones])
print("ordered:", [z.name for z in run2._ordered_zones(zones)])
