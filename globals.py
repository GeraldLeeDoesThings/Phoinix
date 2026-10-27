from __future__ import annotations
from typing import *

if TYPE_CHECKING:
    from ba_recruiting import BARun

ba_run_post_map = {}  # type: Dict[int, BARun]

background_tasks = set()
