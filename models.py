from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


MAFIA_ROLES = {"Босс Мафии", "Киллер Мафии", "Подручный Мафии"}

YAKUZA_ROLES = {"Босс Якудзы", "Ниндзя", "Подручный Якудзы"}

TOWN_ROLES = {
    "Шериф",
    "Сержант",
    "Куртизанка",
    "Доктор",
    "Журналист",
    "Бомж",
    "Почтальон",
    "Тюремщик",
    "Стрелок",
    "Амур",
    "Судья",
    "Ветеран",
}

NEUTRAL_ROLES = {"Маньяк", "Путана", "Ведьма"}


BALANCES = {
    4: [
        "Босс Мафии",
        "Шериф",
        "Доктор",
        "Судья",
    ],

    6: [
        "Босс Мафии",
        "Киллер Мафии",
        "Шериф",
        "Доктор",
        "Судья",
        "Куртизанка",
    ],

    8: [
        "Босс Мафии",
        "Киллер Мафии",
        "Маньяк",
        "Шериф",
        "Доктор",
        "Судья",
        "Куртизанка",
        "Журналист",
    ],

    10: [
        "Босс Мафии",
        "Киллер Мафии",
        "Босс Якудзы",
        "Ниндзя",
        "Шериф",
        "Сержант",
        "Доктор",
        "Судья",
        "Куртизанка",
        "Стрелок",
    ],

    12: [
        "Босс Мафии",
        "Киллер Мафии",
        "Подручный Мафии",
        "Босс Якудзы",
        "Ниндзя",
        "Маньяк",
        "Шериф",
        "Сержант",
        "Доктор",
        "Судья",
        "Куртизанка",
        "Журналист",
    ],

    15: [
        "Босс Мафии",
        "Киллер Мафии",
        "Подручный Мафии",
        "Босс Якудзы",
        "Ниндзя",
        "Подручный Якудзы",
        "Маньяк",
        "Ведьма",
        "Шериф",
        "Сержант",
        "Доктор",
        "Судья",
        "Куртизанка",
        "Журналист",
        "Тюремщик",
    ],

    21: [
        "Босс Мафии",
        "Киллер Мафии",
        "Подручный Мафии",
        "Босс Якудзы",
        "Ниндзя",
        "Подручный Якудзы",
        "Маньяк",
        "Путана",
        "Ведьма",
        "Шериф",
        "Сержант",
        "Куртизанка",
        "Доктор",
        "Журналист",
        "Бомж",
        "Почтальон",
        "Тюремщик",
        "Стрелок",
        "Амур",
        "Судья",
        "Ветеран",
    ],

    30: [
        "Босс Мафии",
        "Киллер Мафии",
        "Подручный Мафии",
        "Подручный Мафии",
        "Подручный Мафии",
        "Босс Якудзы",
        "Ниндзя",
        "Подручный Якудзы",
        "Подручный Якудзы",
        "Подручный Якудзы",
        "Маньяк",
        "Маньяк",
        "Путана",
        "Ведьма",
        "Шериф",
        "Шериф",
        "Сержант",
        "Куртизанка",
        "Доктор",
        "Доктор",
        "Журналист",
        "Бомж",
        "Почтальон",
        "Тюремщик",
        "Стрелок",
        "Стрелок",
        "Амур",
        "Судья",
        "Судья",
        "Ветеран",
    ],
}


def team_of(role: str) -> str:
    if role in MAFIA_ROLES:
        return "mafia"

    if role in YAKUZA_ROLES:
        return "yakuza"

    if role in TOWN_ROLES:
        return "town"

    return "neutral"


def journalist_group(role: str) -> str:
    if role in MAFIA_ROLES or role in YAKUZA_ROLES:
        return "crime"

    if role in {"Маньяк", "Путана", "Ведьма"}:
        return "solo"

    return "town"


def sheriff_view(role: str) -> str:
    if role == "Ниндзя":
        return "мирный"

    if role in MAFIA_ROLES or role in YAKUZA_ROLES:
        return "мафия"

    if role == "Маньяк":
        return "мирный"

    return "мирный"


@dataclass
class Player:
    user_id: int
    name: str
    username: str
    seat: int

    role: Optional[str] = None
    alive: bool = True

    left: bool = False
    left_reason: Optional[str] = None

    # Стрелок
    bullets: int = 0
    last_shot_day: int = 0

    # Ветеран
    alerts_left: int = 0

    # Куртизанка
    last_courtesan_target: Optional[int] = None

    # Ведьма
    witch_barrier: bool = False

    # Путана
    infected: bool = False

    # Доктор
    doctor_heal_counts: Dict[str, int] = field(default_factory=dict)
    doctor_last_target: Optional[int] = None

    # Почтальон
    postman_sent_to: List[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "Player":
        data.setdefault("bullets", 0)
        data.setdefault("last_shot_day", 0)
        data.setdefault("alerts_left", 0)
        data.setdefault("last_courtesan_target", None)
        data.setdefault("witch_barrier", False)
        data.setdefault("infected", False)
        data.setdefault("doctor_heal_counts", {})
        data.setdefault("doctor_last_target", None)
        data.setdefault("postman_sent_to", [])

        return Player(**data)


@dataclass
class Game:
    chat_id: int
    host_id: int
    host_name: str

    phase: str = "LOBBY"
    day: int = 0
    night: int = 0

    players: Dict[int, Player] = field(default_factory=dict)
    seat_to_uid: Dict[int, int] = field(default_factory=dict)

    votes: Dict[int, int] = field(default_factory=dict)
    actions: Dict[int, dict] = field(default_factory=dict)

    lovers: Dict[int, int] = field(default_factory=dict)

    police_verified_town_uids: List[int] = field(default_factory=list)
    police_station_uids: List[int] = field(default_factory=list)

    judge_candidates: List[int] = field(default_factory=list)
    judge_decider_uid: Optional[int] = None
    last_dead_town_uid: Optional[int] = None

    # Тюрьма
    current_jail: List[int] = field(default_factory=list)
    jailer_uid: Optional[int] = None
    jail_weapon_holder_uid: Optional[int] = None
    jail_shot_target_uid: Optional[int] = None

    # Полицейский участок
    police_station: List[int] = field(default_factory=list)
    station_guarded: bool = False

    # Лог ведущему
    host_log: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "chat_id": self.chat_id,
            "host_id": self.host_id,
            "host_name": self.host_name,
            "phase": self.phase,
            "day": self.day,
            "night": self.night,
            "players": {str(uid): p.to_dict() for uid, p in self.players.items()},
            "seat_to_uid": {str(seat): uid for seat, uid in self.seat_to_uid.items()},
            "votes": {str(voter): target for voter, target in self.votes.items()},
            "actions": {str(uid): payload for uid, payload in self.actions.items()},
            "lovers": {str(uid): lover_uid for uid, lover_uid in self.lovers.items()},
            "judge_candidates": self.judge_candidates,
            "judge_decider_uid": self.judge_decider_uid,
            "last_dead_town_uid": self.last_dead_town_uid,
            "current_jail": self.current_jail,
            "jailer_uid": self.jailer_uid,
            "jail_weapon_holder_uid": self.jail_weapon_holder_uid,
            "jail_shot_target_uid": self.jail_shot_target_uid,
            "police_station": self.police_station,
            "station_guarded": self.station_guarded,
            "host_log": self.host_log,
        }

    @staticmethod
    def from_dict(data: dict) -> "Game":
        game = Game(
            chat_id=data["chat_id"],
            host_id=data["host_id"],
            host_name=data["host_name"],
            phase=data.get("phase", "LOBBY"),
            day=data.get("day", 0),
            night=data.get("night", 0),
        )

        game.players = {
            int(uid): Player.from_dict(player_data)
            for uid, player_data in data.get("players", {}).items()
        }

        game.seat_to_uid = {
            int(seat): int(uid)
            for seat, uid in data.get("seat_to_uid", {}).items()
        }

        game.votes = {
            int(voter): int(target)
            for voter, target in data.get("votes", {}).items()
        }

        game.actions = {
            int(uid): payload
            for uid, payload in data.get("actions", {}).items()
        }

        game.lovers = {
            int(uid): int(lover_uid)
            for uid, lover_uid in data.get("lovers", {}).items()
        }

        game.judge_candidates = [int(x) for x in data.get("judge_candidates", [])]
        game.judge_decider_uid = data.get("judge_decider_uid")
        game.last_dead_town_uid = data.get("last_dead_town_uid")

        game.current_jail = [int(x) for x in data.get("current_jail", [])]
        game.jailer_uid = data.get("jailer_uid")
        game.jail_weapon_holder_uid = data.get("jail_weapon_holder_uid")
        game.jail_shot_target_uid = data.get("jail_shot_target_uid")

        game.police_station = [int(x) for x in data.get("police_station", [])]
        game.station_guarded = data.get("station_guarded", False)

        game.host_log = data.get("host_log", [])

        return game
