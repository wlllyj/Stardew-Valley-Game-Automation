"""一次性：查 FakeWorld 模态在 _cleanup_modals_before_finish 里怎么看不到。"""
import sys, pathlib
sys.stdout.reconfigure(encoding="utf-8")
REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "brain"))
from tests import test_longrun as TL

w = TL.FakeWorld()
w.ui_script = [{"activeMenu": "LevelUpMenu", "isModal": True,
                "professionsToChoose": [{"index": 0, "name": "Tiller"}]}] * 5
print("current_ui:", w.current_ui())
r = TL.make_run(w, target_days=1, max_days=1)
print("worker/client:", r.worker is not None, r.client is not None)
obs = r._snap()
print("obs ui:", obs.get("ui"))
print("_modal_info:", r._modal_info(obs))
print("cleanup:", r._cleanup_modals_before_finish())
print("dismiss_calls:", w.dismiss_calls)

w2 = TL.FakeWorld()
w2.ui_script = [{"activeMenu": "DialogueBox", "isModal": True, "eventUp": True}] * 5
r2 = TL.make_run(w2, target_days=1, max_days=1)
print("obs2 ui:", r2._snap().get("ui"))
print("cleanup2:", r2._cleanup_modals_before_finish())
