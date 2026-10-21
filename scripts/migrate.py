import json
from typing import Union

from models import User
from db import get_session


session = next(get_session())

with open("data/verification_map.json", "r") as loadfile:
    str_verification_map: dict[str, dict[str, Union[bool, int, str]]] = json.load(
        loadfile
    )
    count = 0
    for key, value in str_verification_map.items():
        session.merge(
            User(
                discord_id=int(key),
                ffxiv_id=value["id"],
                ffxiv_name=value["name"],
                ffxiv_server=value["server"],
                valid=value["valid"],
                token=value["token"],
            )
        )
        count += 1
        if count % 100 == 0:
            print(count)
    session.commit()
