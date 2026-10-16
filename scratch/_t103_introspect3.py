import inspect, sys
sys.path.insert(0, r"D:\Deepseek Harness Workspace\星露谷游戏自动化\scratch")
from _t92_adv import TL
from agentfarm.farmwork import seed_offers_from, seed_items, farm_empty_dirt
print(inspect.getsource(seed_offers_from))
print("--- FakeWorker.buy ---")
print(inspect.getsource(TL.FakeWorker.buy))
print("--- FakeWorker.__init__ ---")
print(inspect.getsource(TL.FakeWorker.__init__))
print("--- FakeWorld.dismiss ---")
print(inspect.getsource(TL.FakeWorld.dismiss))
print("--- FarmWorker.sleep sig ---")
from agentfarm.farmwork import FarmWorker
print(inspect.signature(FarmWorker.sleep))
