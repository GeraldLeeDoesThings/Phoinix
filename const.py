import datetime
import discord


CHANNEL_ID_MAP = {
    "ba-recruiting": 1029102392601497682,
    "ba-gauging-interest": 1029102353535729815,
    "drn-bozja-farming": 1029104917039820870,
    "drs-recruiting": 1029102476156215307,
    "drs-oce-recruiting": 1222595308056219782,
    "drs-gauging-interest": 1029102431587545261,
    "drs-schedule": 1169284791775006833,
    "command": 275741052344860672,
    "roles": 1029906434877558886,
    "rules": 1029060303746506772,
    "guides": 1035114697957064754,
    "guides-archive": 1035462741336531014,
    "bot-testing": 1037625423850389505,
    "general-offtopic": 1029120734586486834,
    "na-drs-schedule": 1279872027544653857,
    "ft-recruiting": 1350184451979743362,
    "ft-fills": 1385737144693162034,
}

ROLE_ID_MAP = {
    "BA Learning": 1029114312624705576,
    "BA Reclear": 1029114561363705936,
    "BA Lead": 1029164496431886337,
    "Cleared BA": 1029206200212008971,
    "BA Enjoyer": 1384239518928081037,
    "DRS Learning": 1029114229845917776,
    "DRS Reclear": 1029083391208984597,
    "DRS Lead": 1029164459018698802,
    "Delubrum Normal": 1029136889665560596,
    "Cleared DRS": 1029206045005987840,
    "DRS Enjoyer": 1384239563656007680,
    "Cluster Farm": 1029136967885131826,
    "Frag Farm": 1030557655867084901,
    "Castrum": 1029262566666551296,
    "Dalriada": 1029262596802609272,
    "FT Learning": 1350201714094899282,
    "FT Reclear": 1350200965839585343,
    "Volunteer FT Shotcaller": 1379526858403479682,
    "FT Gold Farm": 1377155818356477992,
    "FT Fills": 1374201233954574417,
    "Sporks": 1374201233954574417,
    "Crescent Levelling": 1350201911550148678,
    "Cleared FT": 1294582065307582564,
    "FT Enjoyer": 1384239568559013989,
    "Admin": 1028878560536035428,
    "Moderator": 1029076383542018108,
    "Member": 1029923728588550214,
    "Not Verified": 1034714964553904178,
    "Bots": 1030286995404099584,
}

REQUIRED_TAGS_MAP = {
    CHANNEL_ID_MAP["ba-recruiting"]: {
        ROLE_ID_MAP["BA Learning"],
        ROLE_ID_MAP["BA Reclear"],
    },
    CHANNEL_ID_MAP["drs-recruiting"]: {
        ROLE_ID_MAP["DRS Learning"],
        ROLE_ID_MAP["DRS Reclear"],
    },
    CHANNEL_ID_MAP["drs-oce-recruiting"]: {
        ROLE_ID_MAP["DRS Learning"],
        ROLE_ID_MAP["DRS Reclear"],
    },
    CHANNEL_ID_MAP["drn-bozja-farming"]: {
        ROLE_ID_MAP["Cluster Farm"],
        ROLE_ID_MAP["Frag Farm"],
        ROLE_ID_MAP["Castrum"],
        ROLE_ID_MAP["Dalriada"],
        ROLE_ID_MAP["Delubrum Normal"],
    },
    CHANNEL_ID_MAP["ft-recruiting"]: {
        ROLE_ID_MAP["FT Learning"],
        ROLE_ID_MAP["FT Reclear"],
    },
}

ACHIEVEMENT_ID_MAP = {
    "DRS Clear": 2765,
    "DRS Clear 10x": 2767,
    "BA Clear": 2227,
    "BA Clear 10x": 2229,
    "FT Clear": 3668,
    "FT Clear 10x": 3669,
}

EMOJI_ID_MAP = {
    "checkmark": 1035394485435236422,
    "x": 1035394485435236422,
}

MOUNT_ID_MAP = {
    "DRS Dog": "2d6f62ca18aaaee158814589037dc12f5d708d89",
    "BA Ball": "e824d1537420ae8c6c872ec9f91c5657423b5fa6",
    "FT Crab": "d1aa1d7e1960efb7ca6e253481ac872bb97d5dad",
}

ECHO_TOKEN_URL = "https://www.geraldmadethiscool.website/echo/"

LODESTONE_BASE_URL = "https://na.finalfantasyxiv.com/lodestone/character/"
LODESTONE_SEARCH_URL = "https://na.finalfantasyxiv.com/lodestone/community/search/"
LODESTONE_ACHIEVEMENT_BASE_URL = "/achievement/detail/"

XIVAPI_BASE_URL = "https://xivapi.com/"

HAMMERTIME_TIMESTAMP_URL = "https://hammertime.cyou/"

GRACE_TIME = datetime.datetime.fromisoformat("2024-04-10T21:44:04.762448+00:00")
HALF_DAY = datetime.timedelta(days=0.5)

MIN_MESSAGE_LIFETIME = datetime.timedelta(days=1)
DEFAULT_MESSAGE_LIFETIME = datetime.timedelta(days=7)


LIFETIME_MAP = {CHANNEL_ID_MAP["drn-bozja-farming"]: datetime.timedelta(days=1)}


DO_NOTIFICATIONS_MAP = {CHANNEL_ID_MAP["drn-bozja-farming"]: False}

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
    CHANNEL_ID_MAP["drs-oce-recruiting"],
]

BA_RECRUITING_CHANNELS = [
    #  CHANNEL_ID_MAP["ba-recruiting"],
    CHANNEL_ID_MAP["bot-testing"],
]

BA_RED_DPS = "Red DPS"
BA_BLUE_DPS = "Blue DPS"
BA_HEALER = "Healer"
BA_MAIN_TANK = "Main Tank"
BA_PRECEPTOR = "Preceptor"
BA_FEINT = "Feint"
BA_SPIRIT_DART = "Spirit Dart"

BA_ANY_TANK = [BA_MAIN_TANK, BA_BLUE_DPS]
BA_ANY_DPS = [BA_RED_DPS, BA_BLUE_DPS]
BA_ANY_NON_SPECIAL = [BA_ANY_DPS, BA_BLUE_DPS, BA_HEALER]

BA_ROLE_EMOJI_MAPPING = {
    BA_RED_DPS: discord.PartialEmoji.from_str("<:DPS:1041624309514383370>"),
    BA_BLUE_DPS: discord.PartialEmoji.from_str("<:Tank:1041624337544912937>"),
    BA_HEALER: discord.PartialEmoji.from_str("<:Healer:1041624323112304651>"),
    BA_MAIN_TANK: discord.PartialEmoji.from_str("<:MainTank:1041623723083583508>"),
    BA_PRECEPTOR: discord.PartialEmoji.from_str("<:Perception:1029110537042284554>"),
    BA_FEINT: discord.PartialEmoji.from_str("<:Feint:1029080270105747576>"),
    BA_SPIRIT_DART: discord.PartialEmoji.from_str("<:SpiritDart:1029080237369204787>"),
}
PARTY_LEAD_EMOJI = discord.PartialEmoji.from_str("<:PartyLeader:1041624285850124338>")

FFXIV_SERVERS = [
    "Adamantoise",
    "Aegis",
    "Alexander",
    "Anima",
    "Asura",
    "Atomos",
    "Bahamut",
    "Balmung",
    "Behemoth",
    "Belias",
    "Brynhildr",
    "Cactuar",
    "Carbuncle",
    "Cerberus",
    "Chocobo",
    "Coeurl",
    "Diabolos",
    "Durandal",
    "Excalibur",
    "Exodus",
    "Faerie",
    "Famfrit",
    "Fenrir",
    "Garuda",
    "Gilgamesh",
    "Goblin",
    "Gungnir",
    "Hades",
    "Hyperion",
    "Ifrit",
    "Ixion",
    "Jenova",
    "Kujata",
    "Lamia",
    "Leviathan",
    "Lich",
    "Louisoix",
    "Malboro",
    "Mandragora",
    "Masamune",
    "Mateus",
    "Midgardsormr",
    "Moogle",
    "Odin",
    "Omega",
    "Pandaemonium",
    "Phoenix",
    "Ragnarok",
    "Ramuh",
    "Ridill",
    "Sargatanas",
    "Shinryu",
    "Shiva",
    "Siren",
    "Tiamat",
    "Titan",
    "Tonberry",
    "Typhon",
    "Ultima",
    "Ultros",
    "Unicorn",
    "Valefor",
    "Yojimbo",
    "Zalera",
    "Zeromus",
    "Zodiark",
    "Spriggan",
    "Twintania",
    "Bismarck",
    "Ravana",
    "Sephirot",
    "Sophia",
    "Zurvan",
    "Halicarnassus",
    "Maduin",
    "Marilith",
    "Seraph",
    "HongYuHai",
    "ShenYiZhiDi",
    "LaNuoXiYa",
    "HuanYingQunDao",
    "MengYaChi",
    "YuZhouHeYin",
    "WoXianXiRan",
    "ChenXiWangZuo",
    "BaiYinXiang",
    "BaiJinHuanXiang",
    "ShenQuanHen",
    "ChaoFengTing",
    "LvRenZhanQiao",
    "FuXiaoZhiJian",
    "Longchaoshendian",
    "MengYuBaoJing",
    "ZiShuiZhanQiao",
    "YanXia",
    "JingYuZhuangYuan",
    "MoDuNa",
    "HaiMaoChaWu",
    "RouFengHaiWan",
    "HuPoYuan",
    "ShuiJingTa2",
    "YinLeiHu2",
    "TaiYangHaiAn2",
    "YiXiuJiaDe2",
    "HongChaChuan2",
    "Alpha",
    "Phantom",
    "Raiden",
    "Sagittarius",
    "Cuchulainn",
    "Golem",
    "Kraken",
    "Rafflesia",
    "Innocence",
    "Pixie",
    "Titania",
    "Tycoon",
]
