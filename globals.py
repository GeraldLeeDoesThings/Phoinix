from __future__ import annotations
from typing import *

if TYPE_CHECKING:
    from ba_recruiting import BARun

# Maps User ID (Discord) -> (Token, Character ID (FFXIV))
verification_map = {}  # type: Dict[int, Dict[str, Union[bool, int, str]]]

ba_run_post_map = {}  # type: Dict[int, BARun]

background_tasks = set()
