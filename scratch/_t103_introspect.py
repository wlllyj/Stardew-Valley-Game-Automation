import os, sys, traceback
sys.path.insert(0, r"D:\Deepseek Harness Workspace\星露谷游戏自动化\scratch")
from _t92_adv import TL
import inspect
print("FakeClient methods:", [m for m in dir(TL.FakeClient) if not m.startswith("__")])
print("FakeWorker methods:", [m for m in dir(TL.FakeWorker) if not m.startswith("__")])
print("FakeWorld init sig:", inspect.signature(TL.FakeWorld.__init__))
print("FakeWorld methods:", [m for m in dir(TL.FakeWorld) if not m.startswith("__")])
print("buy sig:", inspect.signature(TL.FakeWorld.buy))
print("sell?" , hasattr(TL.FakeWorld, "sell"), hasattr(TL.FakeClient, "sell"))
