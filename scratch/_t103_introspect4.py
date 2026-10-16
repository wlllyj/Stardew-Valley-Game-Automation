import inspect
from agentfarm import farmwork as F
print(inspect.getsource(F.seed_items))
print(inspect.getsource(F.is_seed_item) if hasattr(F, "is_seed_item") else "no is_seed_item")
print("SEED_ID =", getattr(F, "SEED_ID", None), "SEED_NAME =", getattr(F, "SEED_NAME", None))
print(inspect.getsource(F.pick_seed_offer))
