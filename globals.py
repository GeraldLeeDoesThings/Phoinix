import ba_recruiting
from typing import *

# Maps User ID (Discord) -> (Token, Character ID (FFXIV))
verification_map = {}  # type: Dict[int, Dict[str, Union[bool, int, str]]]

ba_run_post_map = {}  # type: Dict[int, ba_recruiting.BARun]

background_tasks = set()
