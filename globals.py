from typing import *

# Maps User ID (Discord) -> (Token, Character ID (FFXIV))
verification_map = {}  # type: Dict[int, Dict[str, Union[bool, int, str]]]
