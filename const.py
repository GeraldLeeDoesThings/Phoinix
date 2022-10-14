import datetime


CHANNEL_ID_MAP = {
    "ba-recruiting": 1029102392601497682,
    "drs-recruiting": 1029102476156215307,
    "command": 275741052344860672,
    "roles": 1029906434877558886,
}

ROLE_ID_MAP = {
    "BA Learning": 1029114312624705576,
    "BA Reclear": 1029114561363705936,
    "BA Lead": 1029164496431886337,
    "Cleared BA": 1029206200212008971,
    "DRS Learning": 1029114229845917776,
    "DRS Reclear": 1029083391208984597,
    "DRS Lead": 1029164459018698802,
    "Cleared DRS": 1029206045005987840,
    "Admin": 1028878560536035428,
    "Moderator": 1029076383542018108,
}

ACHIEVEMENT_ID_MAP = {
    "DRS Clear": 2765,
    "BA Clear": 2227,
}

LODESTONE_BASE_URL = "https://na.finalfantasyxiv.com/lodestone/character/"
LODESTONE_ACHIEVEMENT_BASE_URL = f"{LODESTONE_BASE_URL}achievement/detail/"

GRACE_TIME = datetime.datetime.fromisoformat("2022-10-10 23:16:42.262194+00:00")
HALF_DAY = datetime.timedelta(days=0.5)
