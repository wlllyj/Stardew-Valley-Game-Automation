"""task-218 探针：登记表口径自检（只读）。"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm import farmwork as F  # noqa: E402
from agentfarm import longrun as L  # noqa: E402
from agentfarm import planner as P  # noqa: E402

print("SKIP_KINDS:", sorted(F.SKIP_KINDS))
print("DEFERRED_KINDS:", sorted(P.DEFERRED_KINDS))
print("NOT_CLEARABLE_KINDS:", sorted(F.NOT_CLEARABLE_KINDS))
print("CLEARABLE_KINDS:", L.CLEARABLE_KINDS)
kinds = tuple(P.OBSTACLE_KINDS) + tuple(F.CLUMP_KINDS)
print("all obstacle-ish kinds:", sorted(set(kinds)))
print("gaps:", P.capability_gaps(obstacle_kinds=kinds, clearable_kinds=L.CLEARABLE_KINDS,
                                 deferred_kinds=P.DEFERRED_KINDS,
                                 not_clearable_kinds=F.NOT_CLEARABLE_KINDS))
