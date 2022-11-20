from ba_recruiting import BARun
from typing import *

# Maps User ID (Discord) -> (Token, Character ID (FFXIV))
verification_map = {}  # type: Dict[int, Dict[str, Union[bool, int, str]]]

ba_run_post_map = {}  # type: Dict[int, BARun]

background_tasks = set()
