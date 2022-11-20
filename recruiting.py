from const import *
import discord
from typing import *


class RunMember:
    def __init__(self, name: str, role: str, id: int):
        self.name = name
        self.role = role
        self.id = id

    def to_dict(self) -> Dict[str, str]:
        return {"name": self.name, "role": self.role, "id": self.id}

    def __eq__(self, other):
        return (type(other) is RunMember and other.id == self.id) or (
            type(other) is int and other == self.id
        )


class Group:
    def __init__(
        self,
        members: List[Union[Dict[str, str], RunMember]],
        leader: Optional[Union[str, int]],
        index: int,
    ):
        self.leader = int(leader) if leader is not None else None
        self.members = [
            member if type(member) is RunMember else RunMember(**member)
            for member in members
        ]
        self.index = index

    def count_roles(self) -> Dict[str, int]:
        roles = {}
        for member in self.members:
            roles[member.role] = roles.get(member.role, 0) + 1
        return roles

    def to_dict(self):
        return {
            "leader": self.leader,
            "members": [member.to_dict() for member in self.members],
            "index": self.index,
        }

    def __len__(self):
        return len(self.members)

    def __int__(self):
        return len(self.members)
