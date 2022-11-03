import datetime
import discord


CHANNEL_ID_MAP = {
    "ba-recruiting": 1029102392601497682,
    "ba-gauging-interest": 1029102353535729815,
    "drn-bozja-farming": 1029104917039820870,
    "drs-recruiting": 1029102476156215307,
    "drs-gauging-interest": 1029102431587545261,
    "command": 275741052344860672,
    "roles": 1029906434877558886,
    "rules": 1029060303746506772,
    "guides": 1035114697957064754,
    "guides-archive": 1035462741336531014,
    "bot-testing": 1037625423850389505,
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
    "Member": 1029923728588550214,
    "Not Verified": 1034714964553904178,
}

ACHIEVEMENT_ID_MAP = {
    "DRS Clear": 2765,
    "BA Clear": 2227,
}

EMOJI_ID_MAP = {
    "checkmark": 1035394485435236422,
    "x": 1035394485435236422,
}

ECHO_TOKEN_URL = "https://www.geraldmadethiscool.website/echo/"

LODESTONE_BASE_URL = "https://na.finalfantasyxiv.com/lodestone/character/"
LODESTONE_SEARCH_URL = "https://na.finalfantasyxiv.com/lodestone/community/search/"
LODESTONE_ACHIEVEMENT_BASE_URL = "/achievement/detail/"

XIVAPI_BASE_URL = "https://xivapi.com/"

GRACE_TIME = datetime.datetime.fromisoformat("2022-11-03T08:51:35.333725+00:00")
HALF_DAY = datetime.timedelta(days=0.5)

MIN_MESSAGE_LIFETIME = datetime.timedelta(days=1)
DEFAULT_MESSAGE_LIFETIME = datetime.timedelta(days=7)

MAX_SEARCH_VALUES = 25

OWN_ID = 1029108007264596038

DELETING_SOON_EMOJI = "⏰"
MONITORING_EMOJI = "👀"
DO_NOT_DELETE_EMOJI = discord.PartialEmoji.from_str("<:PillowNo:1029115321044455535>")

MODERATED_CHANNEL_IDS = [
    CHANNEL_ID_MAP["ba-recruiting"],
    CHANNEL_ID_MAP["ba-gauging-interest"],
    CHANNEL_ID_MAP["bot-testing"],
    CHANNEL_ID_MAP["drn-bozja-farming"],
    CHANNEL_ID_MAP["drs-gauging-interest"],
    CHANNEL_ID_MAP["drs-recruiting"],
]
