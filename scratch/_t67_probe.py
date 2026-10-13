"""超集探针：task-67 改动后，TestOneDay 的一天为什么变成两天。跑完即弃。"""
import sys

sys.path.insert(0, "brain")
sys.path.insert(0, "tests")

from test_longrun import FakeWorld, make_run  # noqa: E402


def main() -> None:
    w = FakeWorld(weeds=4, seeds=10, money=500)
    run = make_run(w, target_days=1)
    code = run.run()
    print("code =", code, "days =", len(run.days))
    for rep in run.days:
        print("--- day", rep.day_key, "ended_by =", rep.ended_by)
        print("  ended_reason =", rep.ended_reason)
        print("  checks =", rep.checks)
        print("  stages =", [(s.get("task") or s.get("stage"), s.get("ok"), s.get("leftover"))
                             for s in rep.stages])
        print("  notes =", rep.notes[:8])
    print("crops =", len(w.crops), "blockers =", w.blockers, "day =", w.day, "sleeps =", w.sleeps)
    print("unwatered_at_sleep =", w.unwatered_at_sleep)
    print("logs tail:", run.logs[-400:])


if __name__ == "__main__":
    main()
