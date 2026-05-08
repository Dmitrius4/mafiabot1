import copy
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from models import (
    BALANCES,
    Game,
    Player,
    MAFIA_ROLES,
    YAKUZA_ROLES,
    TOWN_ROLES,
    team_of,
    journalist_group,
    sheriff_view,
)
from storage import SQLiteStorage


@dataclass
class EngineResponse:
    ok: bool = True
    reply: str = ""
    broadcasts: List[Tuple[int, str]] = field(default_factory=list)
    dms: List[Tuple[int, str]] = field(default_factory=list)


class Engine:
    def __init__(self, storage: SQLiteStorage):
        self.storage = storage

    # -------------------------
    # Общие хелперы
    # -------------------------

    @staticmethod
    def player_label(player: Player) -> str:
        return f"#{player.seat} {player.name}"

    @staticmethod
    def alive_players(game: Game) -> List[Player]:
        return [p for p in game.players.values() if p.alive]

    @staticmethod
    def seat_to_player(game: Game, seat: int) -> Optional[Player]:
        uid = game.seat_to_uid.get(seat)
        if uid is None:
            return None
        return game.players.get(uid)

    @staticmethod
    def effective_role(game: Game, player: Player) -> str:
        if player.role == "Сержант":
            sheriff_alive = any(p.alive and p.role == "Шериф" for p in game.players.values())
            if not sheriff_alive:
                return "Шериф"
        return player.role or ""

    @staticmethod
    def is_crime_team(role: str) -> bool:
        return role in MAFIA_ROLES or role in YAKUZA_ROLES

    def _reindex_seats(self, game: Game) -> None:
        players = sorted(game.players.values(), key=lambda p: p.seat)
        game.seat_to_uid.clear()
        for index, player in enumerate(players, start=1):
            player.seat = index
            game.seat_to_uid[index] = player.user_id

    @staticmethod
    def _start_night(game: Game) -> None:
        game.phase = "NIGHT"
        game.night += 1
        game.actions.clear()
        game.votes.clear()
        game.current_jail = []
        game.jailer_uid = None

    @staticmethod
    def _start_day(game: Game) -> None:
        game.phase = "DAY"
        game.day += 1
        game.votes.clear()
        game.current_jail = []
        game.jailer_uid = None

    def _active_judge(self, game: Game) -> Optional[Player]:
        judges = [p for p in game.players.values() if p.alive and p.role == "Судья"]
        if not judges:
            return None
        return sorted(judges, key=lambda p: p.seat)[0]

    def _find_user_game(self, user_id: int) -> Optional[Game]:
        return self.storage.find_game_by_user(user_id)

    def _kill_player(self, game: Game, uid: int, public_lines: List[str], public_prefix: str) -> None:
        player = game.players[uid]
        if not player.alive:
            return

        player.alive = False
        public_lines.append(f"💀 {public_prefix} {self.player_label(player)}. Роль: <b>{player.role}</b>")

        if team_of(player.role or "") == "town":
            game.last_dead_town_uid = uid

        lover_uid = game.lovers.get(uid)
        if lover_uid and lover_uid in game.players and game.players[lover_uid].alive:
            lover = game.players[lover_uid]
            lover.alive = False
            public_lines.append(f"💔 {self.player_label(lover)} умирает от горя. Роль: <b>{lover.role}</b>")
            if team_of(lover.role or "") == "town":
                game.last_dead_town_uid = lover_uid

        def _roles_composition_text(self, game: Game) -> str:
        if game.phase == "LOBBY":
            count = len(game.players)

            if count in BALANCES:
                roles = BALANCES[count]
                title = f"🎭 Роли для партии на {count} игроков:"
            else:
                supported = ", ".join(map(str, sorted(BALANCES.keys())))
                return (
                    f"🎭 Сейчас игроков: <b>{count}</b>\n"
                    f"Для такого количества игроков баланс не задан.\n"
                    f"Доступные составы: <b>{supported}</b>"
                )
        else:
            roles = [p.role for p in game.players.values() if p.role]
            title = "🎭 Роли в этой партии:"

        counter = Counter(roles)

        if not counter:
            return "🎭 Роли пока не распределены."

        group_order = {
            "mafia": 1,
            "yakuza": 2,
            "neutral": 3,
            "town": 4,
        }

        def sort_key(item):
            role, amount = item
            return group_order.get(team_of(role), 99), role

        lines = [title]

        for role, amount in sorted(counter.items(), key=sort_key):
            lines.append(f"— {role} ×{amount}")

        return "\n".join(lines)

    def roles_list(self, chat_id: int) -> EngineResponse:
        game = self.storage.load_game(chat_id)

        if not game:
            return EngineResponse(ok=False, reply="Игры нет.")

        return EngineResponse(reply=self._roles_composition_text(game))

    def _role_commands_text(self, role: str) -> str:
        if role == "Шериф":
            return (
                "Команды:\n"
                "/проверить N — проверить игрока\n"
                "/убить N — выстрелить ночью\n"
                "/участок_добавить N — добавить в участок\n"
                "/участок_убрать N — убрать из участка\n"
                "/участок — список участка\n"
                "/охранять_участок — охранять участок ночью"
            )

        if role == "Сержант":
            return (
                "Команды:\n"
                "Пока жив Шериф — вы связаны с ним через /team.\n"
                "Если Шериф умрёт, вы получите его функции:\n"
                "/проверить N\n"
                "/убить N\n"
                "/охранять_участок"
            )

        if role == "Доктор":
            return (
                "Команда:\n"
                "/лечить N — лечить игрока ночью\n"
                "Ограничения: одного игрока максимум 2 раза за игру и не две ночи подряд."
            )

        if role == "Куртизанка":
            return (
                "Команда:\n"
                "/соблазнить N — забрать игрока к себе ночью\n"
                "Нельзя соблазнять одного и того же игрока две ночи подряд."
            )

        if role == "Журналист":
            return "Команда:\n/сравнить N M — сравнить двух игроков ночью"

        if role == "Бомж":
            return "Команда:\n/следить N — следить за игроком ночью"

        if role == "Почтальон":
            return (
                "Команда:\n"
                "/письмо N M — проверить игрока N и отправить результат игроку M\n"
                "Одному игроку нельзя отправить письмо дважды."
            )

        if role == "Тюремщик":
            return (
                "Команды:\n"
                "/посадить N M — посадить двух игроков ночью\n"
                "/оружие N — дать оружие одному заключённому\n"
                "/team текст — говорить с заключёнными"
            )

        if role == "Стрелок":
            return (
                "Команда:\n"
                "/стрелять N — дневной выстрел\n"
                "В первый день стрелять нельзя. Всего 3 пули."
            )

        if role == "Амур":
            return "Команда:\n/влюбить N M — выбрать пару ночью"

        if role == "Судья":
            return (
                "Команды:\n"
                "/помиловать — отменить казнь\n"
                "/казнить N — казнить кандидата"
            )

        if role == "Ветеран":
            return "Команда:\n/защищаться — встать на защиту дома ночью"

        if role == "Маньяк":
            return "Команда:\n/зарезать N — выбрать жертву ночью"

        if role == "Путана":
            return "Команда:\n/заразить N — заразить игрока ночью"

        if role == "Ведьма":
            return "Команда:\n/контроль N M — контролировать игрока N и направить его к игроку M"

        if role == "Босс Мафии":
            return (
                "Команды:\n"
                "/мафия_убить N — выбрать жертву мафии\n"
                "/team текст — чат мафии"
            )

        if role == "Киллер Мафии":
            return (
                "Команды:\n"
                "/мафия_убить N — выбрать жертву мафии\n"
                "/доп_выстрел N — дополнительный выстрел киллера\n"
                "/team текст — чат мафии"
            )

        if role == "Подручный Мафии":
            return (
                "Команды:\n"
                "/мафия_убить N — выбрать жертву мафии\n"
                "/team текст — чат мафии"
            )

        if role == "Босс Якудзы":
            return (
                "Команды:\n"
                "/якудза_убить N — выбрать жертву Якудзы\n"
                "/team текст — чат Якудзы"
            )

        if role == "Ниндзя":
            return (
                "Команды:\n"
                "/якудза_убить N — выбрать жертву Якудзы\n"
                "/team текст — чат Якудзы\n"
                "Для проверки Шерифа вы выглядите мирным."
            )

        if role == "Подручный Якудзы":
            return (
                "Команды:\n"
                "/якудза_убить N — выбрать жертву Якудзы\n"
                "/team текст — чат Якудзы"
            )

        return "Для вашей роли специальные команды пока не указаны."

    def action_help(self, user_id: int) -> EngineResponse:
        game = self._find_user_game(user_id)

        if not game:
            return EngineResponse(ok=False, reply="Вы сейчас не в активной игре.")

        player = game.players[user_id]
        role = self.effective_role(game, player)

        return EngineResponse(
            reply=(
                f"🎭 Ваша роль: <b>{player.role}</b>\n"
                f"Текущая активная роль: <b>{role}</b>\n\n"
                f"{self._role_commands_text(role)}"
            )
        )

        def _action_public_notice(self, game: Game, player: Player, payload: dict) -> str:
        role = self.effective_role(game, player)
        verb = payload.get("verb")

        if role == "Шериф":
            if verb == "inspect":
                return "👮 Шериф вышел на проверку."
            if verb == "kill":
                return "👮 Шериф вышел с оружием."
            if verb == "guard_station":
                return "👮 Шериф отправился охранять участок."

        if role == "Доктор":
            return "🩺 Доктор выбрал пациента."

        if role == "Куртизанка":
            return "💃 Куртизанка выбрала клиента."

        if role == "Журналист":
            return "📰 Журналист начал сравнение."

        if role == "Бомж":
            return "🧥 Бомж вышел следить."

        if role == "Почтальон":
            return "📨 Почтальон отправился с письмом."

        if role == "Тюремщик":
            return "🔒 Тюремщик выбрал заключённых."

        if role == "Амур":
            return "💘 Амур выбрал пару."

        if role == "Ветеран":
            return "🛡 Ветеран встал на защиту."

        if role == "Маньяк":
            return "🩸 Маньяк выбрал жертву."

        if role == "Путана":
            return "☣️ Путана распространила заразу."

        if role == "Ведьма":
            return "🪄 Ведьма выбрала цель контроля."

        if role in MAFIA_ROLES:
            if verb == "extra":
                return "🤵 Киллер мафии сделал дополнительный выстрел."

            return "🤵 Мафия сделала выбор."

        if role in YAKUZA_ROLES:
            return "🎌 Якудза сделала выбор."

        return "🌙 Один из игроков сделал ночной ход."

    def _action_private_confirmation(self, game: Game, player: Player, payload: dict) -> str:
        role = self.effective_role(game, player)
        verb = payload.get("verb")
        targets = payload.get("targets", [])

        def label_by_seat(seat: int) -> str:
            target = self.seat_to_player(game, seat)

            if not target:
                return f"#{seat}"

            return self.player_label(target)

        if role == "Шериф":
            if verb == "inspect" and targets:
                return f"✅ Ход принят.\nВы проверяете {label_by_seat(targets[0])}."

            if verb == "kill" and targets:
                return f"✅ Ход принят.\nВы стреляете в {label_by_seat(targets[0])}."

            if verb == "guard_station":
                return "✅ Ход принят.\nВы охраняете полицейский участок."

        if role == "Доктор" and targets:
            return f"✅ Ход принят.\nВы лечите {label_by_seat(targets[0])}."

        if role == "Куртизанка" and targets:
            return f"✅ Ход принят.\nВы соблазняете {label_by_seat(targets[0])}."

        if role == "Журналист" and len(targets) == 2:
            return f"✅ Ход принят.\nВы сравниваете {label_by_seat(targets[0])} и {label_by_seat(targets[1])}."

        if role == "Бомж" and targets:
            return f"✅ Ход принят.\nВы следите за {label_by_seat(targets[0])}."

        if role == "Почтальон" and len(targets) == 2:
            return (
                f"✅ Ход принят.\n"
                f"Вы проверяете {label_by_seat(targets[0])} "
                f"и отправляете письмо {label_by_seat(targets[1])}."
            )

        if role == "Тюремщик" and len(targets) == 2:
            return f"✅ Ход принят.\nВы сажаете {label_by_seat(targets[0])} и {label_by_seat(targets[1])}."

        if role == "Амур" and len(targets) == 2:
            return f"✅ Ход принят.\nВы создаёте пару: {label_by_seat(targets[0])} и {label_by_seat(targets[1])}."

        if role == "Ветеран":
            return "✅ Ход принят.\nВы встали на защиту дома."

        if role == "Маньяк" and targets:
            return f"✅ Ход принят.\nВы выбрали жертву: {label_by_seat(targets[0])}."

        if role == "Путана" and targets:
            return f"✅ Ход принят.\nВы заражаете {label_by_seat(targets[0])}."

        if role == "Ведьма" and len(targets) == 2:
            return (
                f"✅ Ход принят.\n"
                f"Вы контролируете {label_by_seat(targets[0])} "
                f"и направляете к {label_by_seat(targets[1])}."
            )

        if role in MAFIA_ROLES and targets:
            if verb == "extra":
                return f"✅ Дополнительный выстрел принят.\nЦель: {label_by_seat(targets[0])}."

            return f"✅ Ход мафии принят.\nЦель: {label_by_seat(targets[0])}."

        if role in YAKUZA_ROLES and targets:
            return f"✅ Ход Якудзы принят.\nЦель: {label_by_seat(targets[0])}."

        return "✅ Ход принят."

    def _check_winner(self, game: Game) -> Optional[str]:
        alive = [p for p in game.players.values() if p.alive]
        if not alive:
            return "Ничья"

        putana_alive = [p for p in alive if p.role == "Путана"]
        if putana_alive:
            others = [p for p in alive if p.role != "Путана"]
            if others and all(p.infected for p in others):
                return "Победа Путаны"

        teams = set(team_of(p.role or "") for p in alive)
        if teams == {"town"}:
            return "Победа мирных"
        if teams == {"mafia"}:
            return "Победа мафии"
        if teams == {"yakuza"}:
            return "Победа якудзы"

        if len(alive) == 1:
            p = alive[0]
            return f"Победа: {self.player_label(p)} ({p.role})"

        return None

    def _role_cards(self, game: Game) -> List[Tuple[int, str]]:
        dms: List[Tuple[int, str]] = []

        for p in game.players.values():
            extra = []
            if p.role == "Стрелок":
                extra.append("Пули: 3")
            if p.role == "Ветеран":
                extra.append("Защиты: 3")
            if p.role == "Ведьма":
                extra.append("Магический барьер: 1")
            txt = f"🎭 Ваша роль: <b>{p.role}</b>\nМесто: <b>#{p.seat}</b>"

if extra:
    txt += "\n" + "\n".join(extra)

txt += "\n\n" + self._role_commands_text(p.role or "")

dms.append((p.user_id, txt))

        mafia = [p for p in game.players.values() if p.role in MAFIA_ROLES]
        yakuza = [p for p in game.players.values() if p.role in YAKUZA_ROLES]
        police = [p for p in game.players.values() if p.role in {"Шериф", "Сержант"}]

        if len(mafia) > 1:
            members = "\n".join(f"{self.player_label(p)} — {p.role}" for p in sorted(mafia, key=lambda x: x.seat))
            for p in mafia:
                dms.append((p.user_id, f"🤝 Ваша фракция:\n{members}"))

        if len(yakuza) > 1:
            members = "\n".join(f"{self.player_label(p)} — {p.role}" for p in sorted(yakuza, key=lambda x: x.seat))
            for p in yakuza:
                dms.append((p.user_id, f"🤝 Ваша фракция:\n{members}"))

        if len(police) > 1:
            members = "\n".join(f"{self.player_label(p)} — {p.role}" for p in sorted(police, key=lambda x: x.seat))
            for p in police:
                dms.append((p.user_id, f"👮 Полицейская связка:\n{members}"))

        return dms

    # -------------------------
    # Команды
    # -------------------------

    def private_start(self, user_id: int) -> EngineResponse:
        self.storage.mark_private_started(user_id)
        return EngineResponse(reply="Привет. Теперь можешь входить в игру через /join в группе.")

    def create_game(self, chat_id: int, host_id: int, host_name: str) -> EngineResponse:
        current = self.storage.load_game(chat_id)
        if current and current.phase != "ENDED":
            return EngineResponse(ok=False, reply="Игра уже существует в этом чате.")

        game = Game(chat_id=chat_id, host_id=host_id, host_name=host_name)
        self.storage.save_game(game)
        return EngineResponse(
            broadcasts=[(
                chat_id,
                "🎲 Игра создана.\n"
                "Игроки входят через /join\n"
                "Перед входом каждый должен написать боту в личку: /start"
            )]
        )

    def join_game(self, chat_id: int, user_id: int, name: str, username: str) -> EngineResponse:
        game = self.storage.load_game(chat_id)
        if not game or game.phase != "LOBBY":
            return EngineResponse(ok=False, reply="Сейчас нет открытого лобби.")

        if not self.storage.has_private_started(user_id):
            return EngineResponse(ok=False, reply="Сначала напишите боту в личку /start")

        if user_id in game.players:
            return EngineResponse(ok=False, reply="Вы уже в игре.")

        seat = len(game.players) + 1
        player = Player(
            user_id=user_id,
            name=name,
            username=username,
            seat=seat
        )
        game.players[user_id] = player
        game.seat_to_uid[seat] = user_id
        self.storage.save_game(game)

        return EngineResponse(
            broadcasts=[(chat_id, f"➕ {self.player_label(player)} вошёл(ла) в игру.")]
        )

    def leave_game(self, chat_id: int, user_id: int) -> EngineResponse:
        game = self.storage.load_game(chat_id)
        if not game or game.phase != "LOBBY":
            return EngineResponse(ok=False, reply="Выйти можно только из лобби.")

        player = game.players.pop(user_id, None)
        if not player:
            return EngineResponse(ok=False, reply="Вас нет в лобби.")

        game.seat_to_uid.pop(player.seat, None)
        self._reindex_seats(game)
        self.storage.save_game(game)

        return EngineResponse(
            broadcasts=[(chat_id, f"➖ {self.player_label(player)} вышел(ла) из лобби.")]
        )

        def players_list(self, chat_id: int) -> EngineResponse:
        game = self.storage.load_game(chat_id)

        if not game:
            return EngineResponse(ok=False, reply="Игры нет.")

        plist = sorted(game.players.values(), key=lambda x: x.seat)

        if not plist:
            return EngineResponse(reply="Игроков пока нет.")

        lines = ["👥 Игроки:"]

        for p in plist:
            if game.phase == "LOBBY":
                lines.append(f"{self.player_label(p)}")
            else:
                if p.alive:
                    lines.append(f"{self.player_label(p)} — жив")
                else:
                    lines.append(f"{self.player_label(p)} — мёртв, роль: <b>{p.role}</b>")

        text = "\n".join(lines)
        text += "\n\n" + self._roles_composition_text(game)

        return EngineResponse(reply=text)

    def close_game(self, chat_id: int, user_id: int) -> EngineResponse:
        game = self.storage.load_game(chat_id)
        if not game:
            return EngineResponse(ok=False, reply="Игры нет.")
        if game.host_id != user_id:
            return EngineResponse(ok=False, reply="Только ведущий может закрыть игру.")
        if game.phase != "LOBBY":
            return EngineResponse(ok=False, reply="После старта игра так не закрывается.")

        self.storage.delete_game(chat_id)
        return EngineResponse(broadcasts=[(chat_id, "❌ Игра закрыта.")])

    def start_game(self, chat_id: int, user_id: int) -> EngineResponse:
        game = self.storage.load_game(chat_id)
        if not game:
            return EngineResponse(ok=False, reply="Игры нет.")
        if game.host_id != user_id:
            return EngineResponse(ok=False, reply="Только ведущий может начать игру.")

        count = len(game.players)
        if count not in BALANCES:
            return EngineResponse(
                ok=False,
                reply=f"Неподдерживаемое число игроков: {count}. Доступно: {', '.join(map(str, BALANCES.keys()))}"
            )

        roles = BALANCES[count][:]
        random.shuffle(roles)

        players = list(game.players.values())
        random.shuffle(players)

        for p, role in zip(players, roles):
            p.role = role
            p.alive = True
            p.bullets = 3 if role == "Стрелок" else 0
            p.alerts_left = 3 if role == "Ветеран" else 0
            p.witch_barrier = role == "Ведьма"
            p.infected = False
            p.last_shot_day = 0
            p.last_courtesan_target = None

        game.lovers.clear()
        game.last_dead_town_uid = None
        game.judge_candidates.clear()
        game.judge_decider_uid = None
        self._start_night(game)
        self.storage.save_game(game)

        return EngineResponse(
            broadcasts=[(chat_id, f"🎭 Игра началась.\n🌙 Ночь {game.night}\nВсе ночные ходы — в личку боту.")],
            dms=self._role_cards(game)
        )

    def submit_named_action(
        self,
        user_id: int,
        pseudo_text: str,
        allowed_roles: set,
        usage_text: str,
    ) -> EngineResponse:
        game = self._find_user_game(user_id)

        if not game:
            return EngineResponse(ok=False, reply="Вы не в игре.")

        if game.phase != "NIGHT":
            return EngineResponse(ok=False, reply="Ночные действия принимаются только ночью.")

        player = game.players[user_id]

        if not player.alive:
            return EngineResponse(ok=False, reply="Мёртвые не ходят.")

        role = self.effective_role(game, player)

        if role not in allowed_roles and player.role not in allowed_roles:
            return EngineResponse(
                ok=False,
                reply=(
                    "Эта команда недоступна вашей роли.\n\n"
                    f"Ваша роль: <b>{player.role}</b>\n\n"
                    f"{self._role_commands_text(role)}"
                ),
            )

        response = self.submit_action(user_id, pseudo_text)

        if not response.ok:
            response.reply += f"\n\nПравильный формат:\n{usage_text}"

        return response

    def _night_action_status(self, game: Game) -> Tuple[List[str], List[int]]:
        lines: List[str] = []
        remind_user_ids: List[int] = []

        if game.phase != "NIGHT":
            return ["Сейчас не ночь."], []

        alive = [p for p in game.players.values() if p.alive]

        def has_action(uid: int) -> bool:
            return uid in game.actions

        def action_mark(done: bool) -> str:
            return "✅" if done else "❌"

        lines.append(f"🌙 Ночь {game.night}. Статус ходов:")

        individual_roles = {
            "Шериф",
            "Доктор",
            "Куртизанка",
            "Журналист",
            "Бомж",
            "Почтальон",
            "Тюремщик",
            "Маньяк",
            "Путана",
            "Ведьма",
        }

        if game.night == 1:
            individual_roles.add("Амур")

        for p in sorted(alive, key=lambda x: x.seat):
            effective = self.effective_role(game, p)

            if effective not in individual_roles:
                continue

            done = has_action(p.user_id)
            lines.append(f"{action_mark(done)} {effective}: {self.player_label(p)}")

            if not done:
                remind_user_ids.append(p.user_id)

        veterans = [
            p for p in alive
            if self.effective_role(game, p) == "Ветеран"
        ]

        for p in sorted(veterans, key=lambda x: x.seat):
            done = has_action(p.user_id)
            mark = "✅" if done else "➖"
            lines.append(f"{mark} Ветеран: {self.player_label(p)} — ход опциональный")

        mafia_alive = [
            p for p in alive
            if p.role in MAFIA_ROLES
        ]

        if mafia_alive:
            mafia_done = any(
                uid in game.actions and game.players[uid].role in MAFIA_ROLES
                for uid in game.actions
            )

            lines.append(f"{action_mark(mafia_done)} Мафия: клановый ход")

            if not mafia_done:
                for p in mafia_alive:
                    remind_user_ids.append(p.user_id)

            killers = [
                p for p in mafia_alive
                if p.role == "Киллер Мафии"
            ]

            for killer in killers:
                extra_done = (
                    killer.user_id in game.actions
                    and game.actions[killer.user_id].get("verb") == "extra"
                )

                mark = "✅" if extra_done else "➖"
                lines.append(f"{mark} Киллер Мафии: {self.player_label(killer)} — доп. выстрел опциональный")

        yakuza_alive = [
            p for p in alive
            if p.role in YAKUZA_ROLES
        ]

        if yakuza_alive:
            yakuza_done = any(
                uid in game.actions and game.players[uid].role in YAKUZA_ROLES
                for uid in game.actions
            )

            lines.append(f"{action_mark(yakuza_done)} Якудза: клановый ход")

            if not yakuza_done:
                for p in yakuza_alive:
                    remind_user_ids.append(p.user_id)

        remind_user_ids = list(dict.fromkeys(remind_user_ids))

        return lines, remind_user_ids

    def night_actions_status(self, chat_id: int, user_id: int) -> EngineResponse:
        game = self.storage.load_game(chat_id)

        if not game:
            return EngineResponse(ok=False, reply="Игры нет.")

        if game.host_id != user_id:
            return EngineResponse(ok=False, reply="Только ведущий может смотреть статус ходов.")

        lines, _ = self._night_action_status(game)

        return EngineResponse(reply="\n".join(lines))

    def remind_night_actions(self, chat_id: int, user_id: int) -> EngineResponse:
        game = self.storage.load_game(chat_id)

        if not game:
            return EngineResponse(ok=False, reply="Игры нет.")

        if game.host_id != user_id:
            return EngineResponse(ok=False, reply="Только ведущий может отправлять напоминания.")

        if game.phase != "NIGHT":
            return EngineResponse(ok=False, reply="Напоминать о ночных ходах можно только ночью.")

        lines, remind_user_ids = self._night_action_status(game)

        if not remind_user_ids:
            return EngineResponse(reply="✅ Все обязательные ночные ходы уже сделаны.")

        dms: List[Tuple[int, str]] = []

        for uid in remind_user_ids:
            player = game.players.get(uid)

            if not player or not player.alive:
                continue

            role = self.effective_role(game, player)

            dms.append((
                uid,
                "🌙 Напоминание от ведущего.\n"
                "Вы ещё не сделали ночной ход.\n\n"
                f"Ваша роль: <b>{player.role}</b>\n\n"
                f"{self._role_commands_text(role)}"
            ))

        return EngineResponse(
            reply=f"🔔 Напоминание отправлено: {len(dms)} игрокам.",
            dms=dms,
        )

    def status(self, chat_id: int) -> EngineResponse:
        game = self.storage.load_game(chat_id)
        if not game:
            return EngineResponse(ok=False, reply="Игры нет.")

        alive = [self.player_label(p) for p in sorted(game.players.values(), key=lambda x: x.seat) if p.alive]
        dead = [self.player_label(p) for p in sorted(game.players.values(), key=lambda x: x.seat) if not p.alive]

        txt = (
            f"Фаза: <b>{game.phase}</b>\n"
            f"День: <b>{game.day}</b>\n"
            f"Ночь: <b>{game.night}</b>\n\n"
            f"Живые ({len(alive)}):\n" + ("\n".join(alive) if alive else "—") +
            "\n\nМёртвые:\n" + ("\n".join(dead) if dead else "—")
        )
        txt += "\n\n" + self._roles_composition_text(game)
        return EngineResponse(reply=txt)

    def open_night(self, chat_id: int, user_id: int) -> EngineResponse:
        game = self.storage.load_game(chat_id)
        if not game:
            return EngineResponse(ok=False, reply="Игры нет.")
        if game.host_id != user_id:
            return EngineResponse(ok=False, reply="Только ведущий может открыть ночь.")
        if game.phase != "DAY":
            return EngineResponse(ok=False, reply="Ночь можно открыть только после дня.")

        self._start_night(game)
        self.storage.save_game(game)
        return EngineResponse(
            broadcasts=[(chat_id, f"🌙 Наступила ночь {game.night}\nВсе ночные ходы — в личку боту.")]
        )

    def open_day(self, chat_id: int, user_id: int) -> EngineResponse:
        game = self.storage.load_game(chat_id)
        if not game:
            return EngineResponse(ok=False, reply="Игры нет.")
        if game.host_id != user_id:
            return EngineResponse(ok=False, reply="Только ведущий может открыть день.")
        if game.phase != "NIGHT":
            return EngineResponse(ok=False, reply="Сейчас не ночь.")

        public_lines, dms = self._resolve_night(game)
        if game.phase != "ENDED":
            self._start_day(game)

        self.storage.save_game(game)
        text = f"☀️ Наступил день {game.day}\n" + "\n".join(public_lines)
        return EngineResponse(
            broadcasts=[(chat_id, text)],
            dms=dms
        )

    def open_vote(self, chat_id: int, user_id: int) -> EngineResponse:
        game = self.storage.load_game(chat_id)
        if not game:
            return EngineResponse(ok=False, reply="Игры нет.")
        if game.host_id != user_id:
            return EngineResponse(ok=False, reply="Только ведущий может открыть голосование.")
        if game.phase != "DAY":
            return EngineResponse(ok=False, reply="Голосование можно открыть только днём.")

        game.phase = "VOTING"
        game.votes.clear()
        self.storage.save_game(game)
        return EngineResponse(
            broadcasts=[(chat_id, "🗳 Голосование открыто. Команда: /vote N")]
        )

    def vote(self, chat_id: int, voter_id: int, seat: int) -> EngineResponse:
        game = self.storage.load_game(chat_id)
        if not game or game.phase != "VOTING":
            return EngineResponse(ok=False, reply="Голосование сейчас закрыто.")

        voter = game.players.get(voter_id)
        if not voter or not voter.alive:
            return EngineResponse(ok=False, reply="Вы не можете голосовать.")
        if voter_id in game.votes:
            return EngineResponse(ok=False, reply="Повторно голосовать нельзя.")

        target = self.seat_to_player(game, seat)
        if not target or not target.alive:
            return EngineResponse(ok=False, reply="Такой живой цели нет.")
        if target.user_id == voter_id:
            return EngineResponse(ok=False, reply="Против себя голосовать нельзя.")

        game.votes[voter_id] = target.user_id
        self.storage.save_game(game)
        return EngineResponse(
            broadcasts=[(chat_id, f"🗳 {self.player_label(voter)} голосует против {self.player_label(target)}")]
        )

    def close_vote(self, chat_id: int, user_id: int) -> EngineResponse:
        game = self.storage.load_game(chat_id)
        if not game:
            return EngineResponse(ok=False, reply="Игры нет.")
        if game.host_id != user_id:
            return EngineResponse(ok=False, reply="Только ведущий может закрыть голосование.")
        if game.phase != "VOTING":
            return EngineResponse(ok=False, reply="Голосование сейчас не открыто.")

        lines, dms = self._resolve_vote(game)
        winner = None
        if game.phase != "JUDGE":
            winner = self._check_winner(game)
            if winner:
                lines.append(f"🏆 {winner}")
                game.phase = "ENDED"

        self.storage.save_game(game)
        return EngineResponse(
            broadcasts=[(chat_id, "\n".join(lines))],
            dms=dms
        )

    def my_role(self, user_id: int) -> EngineResponse:
        game = self._find_user_game(user_id)
        if not game:
            return EngineResponse(ok=False, reply="Вы сейчас не в активной игре.")

        player = game.players[user_id]
        status = "жив" if player.alive else "мёртв"
        effect = self.effective_role(game, player)
        extra = ""
        if effect != player.role:
            extra = f"\nТекущая активная роль: <b>{effect}</b>"

        return EngineResponse(
            reply=(
                f"🎭 Роль: <b>{player.role}</b>\n"
                f"Место: <b>#{player.seat}</b>\n"
                f"Статус: <b>{status}</b>{extra}"
            )
        )

    # -------------------------
    # Голосование / Судья
    # -------------------------

    def _resolve_vote(self, game: Game) -> Tuple[List[str], List[Tuple[int, str]]]:
        lines: List[str] = []
        dms: List[Tuple[int, str]] = []

        if not game.votes:
            game.phase = "DAY"
            lines.append("Голосов нет. Казнь не состоялась.")
            return lines, dms

        lines.append("🗳 Поимённый список голосов:")
        for voter_uid, target_uid in sorted(game.votes.items(), key=lambda item: game.players[item[0]].seat):
            voter = game.players[voter_uid]
            target = game.players[target_uid]
            lines.append(f"— {self.player_label(voter)} -> {self.player_label(target)}")

        tally: Dict[int, int] = {}
        for target_uid in game.votes.values():
            tally[target_uid] = tally.get(target_uid, 0) + 1

        lines.append("\n📊 Итоги:")
        for uid, cnt in sorted(tally.items(), key=lambda item: (-item[1], game.players[item[0]].seat)):
            lines.append(f"— {self.player_label(game.players[uid])}: {cnt}")

        max_votes = max(tally.values())
        candidates = [uid for uid, cnt in tally.items() if cnt == max_votes]
        judge = self._active_judge(game)

        if len(candidates) == 1:
            cand_uid = candidates[0]
            cand = game.players[cand_uid]

            if judge and judge.user_id == cand_uid:
                game.phase = "DAY"
                self._kill_player(game, cand_uid, lines, "Казнён(а) автоматически")
                return lines, dms

            if judge:
                game.phase = "JUDGE"
                game.judge_candidates = candidates
                game.judge_decider_uid = judge.user_id
                dms.append((
                    judge.user_id,
                    f"⚖️ Решение по {self.player_label(cand)}:\n"
                    f"/judge pardon\nили\n"
                    f"/judge {cand.seat}"
                ))
                lines.append("\nОжидаем решение Судьи.")
                return lines, dms

            game.phase = "DAY"
            self._kill_player(game, cand_uid, lines, "Казнён(а)")
            return lines, dms

        # Несколько кандидатов
        candidate_labels = ", ".join(self.player_label(game.players[uid]) for uid in candidates)
        lines.append(f"\nНичья между: {candidate_labels}")

        if judge and judge.user_id in candidates:
            game.phase = "DAY"
            self._kill_player(game, judge.user_id, lines, "Казнён(а) автоматически как подозреваемый Судья")
            return lines, dms

        if judge:
            game.phase = "JUDGE"
            game.judge_candidates = candidates
            game.judge_decider_uid = judge.user_id
            seats = ", ".join(f"#{game.players[uid].seat}" for uid in candidates)
            dms.append((
                judge.user_id,
                f"⚖️ Ничья.\nКандидаты: {seats}\n/judge pardon\nили\n/judge N"
            ))
            lines.append("Ожидаем решение Судьи.")
            return lines, dms

        if game.last_dead_town_uid and game.last_dead_town_uid in game.players:
            decider = game.players[game.last_dead_town_uid]
            game.phase = "JUDGE"
            game.judge_candidates = candidates
            game.judge_decider_uid = decider.user_id
            seats = ", ".join(f"#{game.players[uid].seat}" for uid in candidates)
            dms.append((
                decider.user_id,
                f"⚖️ Вы получили решающий голос.\nКандидаты: {seats}\n/judge pardon\nили\n/judge N"
            ))
            lines.append("Ожидаем решающий голос последнего убитого мирного.")
            return lines, dms

        chosen = random.choice(candidates)
        game.phase = "DAY"
        lines.append("🎲 При равенстве сработал ГСЧ.")
        self._kill_player(game, chosen, lines, "Казнён(а)")
        return lines, dms

    def judge(self, user_id: int, raw_text: str) -> EngineResponse:
        game = self._find_user_game(user_id)
        if not game or game.phase != "JUDGE":
            return EngineResponse(ok=False, reply="Сейчас решение Судьи не ожидается.")
        if game.judge_decider_uid != user_id:
            return EngineResponse(ok=False, reply="Сейчас решение принимаете не вы.")

        parts = raw_text.split()
        if len(parts) != 2:
            return EngineResponse(ok=False, reply="Использование: /judge pardon или /judge N")

        lines: List[str] = []

        if parts[1] == "pardon":
            game.phase = "DAY"
            game.judge_candidates.clear()
            game.judge_decider_uid = None
            self.storage.save_game(game)
            return EngineResponse(
                broadcasts=[(game.chat_id, "⚖️ Решение Судьи: помиловать.")]
            )

        if not parts[1].isdigit():
            return EngineResponse(ok=False, reply="Нужно указать номер места или pardon.")

        seat = int(parts[1])
        target = self.seat_to_player(game, seat)
        if not target or target.user_id not in game.judge_candidates:
            return EngineResponse(ok=False, reply="Этот игрок не входит в список кандидатов.")

        self._kill_player(game, target.user_id, lines, "Казнён(а) по решению Судьи")
        game.phase = "DAY"
        game.judge_candidates.clear()
        game.judge_decider_uid = None

        winner = self._check_winner(game)
        if winner:
            lines.append(f"🏆 {winner}")
            game.phase = "ENDED"

        self.storage.save_game(game)
        return EngineResponse(
            broadcasts=[(game.chat_id, "\n".join(lines))]
        )

    # -------------------------
    # Стрелок
    # -------------------------

    def shoot(self, user_id: int, raw_text: str) -> EngineResponse:
        game = self._find_user_game(user_id)
        if not game or game.phase not in {"DAY", "VOTING"}:
            return EngineResponse(ok=False, reply="Стрелять можно только днём.")

        player = game.players[user_id]
        if not player.alive or player.role != "Стрелок":
            return EngineResponse(ok=False, reply="У вас нет этой способности.")
        if game.day < 2:
            return EngineResponse(ok=False, reply="В первый день стрелять нельзя.")
        if player.bullets <= 0:
            return EngineResponse(ok=False, reply="Пули закончились.")
        if player.last_shot_day == game.day:
            return EngineResponse(ok=False, reply="Сегодня вы уже стреляли.")

        parts = raw_text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            return EngineResponse(ok=False, reply="Использование: /shoot N")

        target = self.seat_to_player(game, int(parts[1]))
        if not target or not target.alive:
            return EngineResponse(ok=False, reply="Цель не найдена.")
        if target.user_id == player.user_id:
            return EngineResponse(ok=False, reply="В себя стрелять нельзя.")

        player.bullets -= 1
        player.last_shot_day = game.day

        lines: List[str] = []
        self._kill_player(game, target.user_id, lines, "Убит(а) дневным выстрелом")

        if target.role in MAFIA_ROLES or target.role in YAKUZA_ROLES:
            text = "🔫 Днём был произведён выстрел.\n" + "\n".join(lines)
        else:
            text = f"🔫 Стрелок раскрылся: {self.player_label(player)}\n" + "\n".join(lines)

        winner = self._check_winner(game)
        if winner:
            text += f"\n🏆 {winner}"
            game.phase = "ENDED"

        self.storage.save_game(game)
        return EngineResponse(
            broadcasts=[(game.chat_id, text)],
            reply="✅ Выстрел принят."
        )

    # -------------------------
    # Командный чат
    # -------------------------

    def team_message(self, user_id: int, raw_text: str) -> EngineResponse:
        game = self._find_user_game(user_id)
        if not game:
            return EngineResponse(ok=False, reply="Вы не в игре.")

        sender = game.players[user_id]
        if not sender.alive:
            return EngineResponse(ok=False, reply="Мёртвые не пишут в чат.")

        text = raw_text.replace("/team", "", 1).strip()
        if not text:
            return EngineResponse(ok=False, reply="Использование: /team ваш текст")

        dms: List[Tuple[int, str]] = []

        # Чат тюрьмы
        if game.phase == "NIGHT" and user_id in game.current_jail:
            others = [uid for uid in game.current_jail if uid != user_id and game.players[uid].alive]
            for uid in others:
                dms.append((uid, f"🔒 {self.player_label(sender)}: {text}"))
            if game.jailer_uid and game.jailer_uid in game.players and game.players[game.jailer_uid].alive:
                dms.append((game.jailer_uid, f"👂 [Тюрьма] {self.player_label(sender)}: {text}"))
            if not others:
                return EngineResponse(ok=False, reply="В тюрьме сейчас некому писать.")
            return EngineResponse(reply="Сообщение отправлено.", dms=dms)

        # Тюремщик пишет в тюрьму
        if game.phase == "NIGHT" and sender.role == "Тюремщик" and game.current_jail:
            for uid in game.current_jail:
                if game.players[uid].alive:
                    dms.append((uid, f"🔐 Тюремщик: {text}"))
            return EngineResponse(reply="Сообщение отправлено.", dms=dms)

        recipients: List[Player] = []

        if sender.role in MAFIA_ROLES:
            recipients = [p for p in game.players.values() if p.alive and p.role in MAFIA_ROLES and p.user_id != user_id]
        elif sender.role in YAKUZA_ROLES:
            recipients = [p for p in game.players.values() if p.alive and p.role in YAKUZA_ROLES and p.user_id != user_id]
        elif sender.role in {"Шериф", "Сержант"}:
            recipients = [p for p in game.players.values() if p.alive and p.role in {"Шериф", "Сержант"} and p.user_id != user_id]
        elif user_id in game.lovers:
            lover_uid = game.lovers[user_id]
            lover = game.players.get(lover_uid)
            if lover and lover.alive:
                recipients = [lover]

        if not recipients:
            return EngineResponse(ok=False, reply="Сейчас у вас нет доступного командного чата.")

        for rec in recipients:
            dms.append((rec.user_id, f"💬 {self.player_label(sender)}: {text}"))

        return EngineResponse(reply="Сообщение отправлено.", dms=dms)

    # -------------------------
    # Ночные ходы
    # -------------------------

    def submit_action(self, user_id: int, raw_text: str) -> EngineResponse:
        game = self._find_user_game(user_id)
        if not game:
            return EngineResponse(ok=False, reply="Вы не в игре.")
        if game.phase != "NIGHT":
            return EngineResponse(ok=False, reply="Ночные действия принимаются только ночью.")

        player = game.players[user_id]
        if not player.alive:
            return EngineResponse(ok=False, reply="Мёртвые не ходят.")

        role = self.effective_role(game, player)
        parts = raw_text.split()

        def target_alive(seat: int) -> Optional[Player]:
            p = self.seat_to_player(game, seat)
            if not p or not p.alive:
                return None
            return p

        try:
            if role == "Шериф":
                if len(parts) != 3 or parts[1] not in {"inspect", "kill"} or not parts[2].isdigit():
                    raise ValueError("Использование: /act inspect N или /act kill N")
                seat = int(parts[2])
                target = target_alive(seat)
                if not target or target.user_id == player.user_id:
                    raise ValueError("Некорректная цель.")
                game.actions[user_id] = {"verb": parts[1], "targets": [seat]}

            elif role == "Доктор":
                if len(parts) != 2 or not parts[1].isdigit():
                    raise ValueError("Использование: /act N")
                seat = int(parts[1])
                target = target_alive(seat)
                if not target:
                    raise ValueError("Некорректная цель.")
                game.actions[user_id] = {"verb": "heal", "targets": [seat]}

            elif role == "Куртизанка":
                if len(parts) != 2 or not parts[1].isdigit():
                    raise ValueError("Использование: /act N")
                seat = int(parts[1])
                target = target_alive(seat)
                if not target or target.user_id == player.user_id:
                    raise ValueError("Некорректная цель.")
                game.actions[user_id] = {"verb": "visit", "targets": [seat]}

            elif role == "Журналист":
                if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
                    raise ValueError("Использование: /act N M")
                s1 = int(parts[1])
                s2 = int(parts[2])
                p1 = target_alive(s1)
                p2 = target_alive(s2)
                if not p1 or not p2 or s1 == s2:
                    raise ValueError("Некорректные цели.")
                game.actions[user_id] = {"verb": "compare", "targets": [s1, s2]}

            elif role == "Бомж":
                if len(parts) != 2 or not parts[1].isdigit():
                    raise ValueError("Использование: /act N")
                seat = int(parts[1])
                target = target_alive(seat)
                if not target:
                    raise ValueError("Некорректная цель.")
                game.actions[user_id] = {"verb": "watch", "targets": [seat]}

            elif role == "Амур":
                if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
                    raise ValueError("Использование: /act N M")
                s1 = int(parts[1])
                s2 = int(parts[2])
                p1 = target_alive(s1)
                p2 = target_alive(s2)
                if not p1 or not p2 or s1 == s2:
                    raise ValueError("Некорректные цели.")
                game.actions[user_id] = {"verb": "love", "targets": [s1, s2]}

            elif role == "Ветеран":
                if len(parts) == 1 or (len(parts) == 2 and parts[1] in {"alert", "on"}):
                    game.actions[user_id] = {"verb": "alert", "targets": []}
                else:
                    raise ValueError("Использование: /act alert")

            elif role == "Маньяк":
                if len(parts) != 2 or not parts[1].isdigit():
                    raise ValueError("Использование: /act N")
                seat = int(parts[1])
                target = target_alive(seat)
                if not target or target.user_id == player.user_id:
                    raise ValueError("Некорректная цель.")
                game.actions[user_id] = {"verb": "kill", "targets": [seat]}

            elif role == "Путана":
                if len(parts) != 2 or not parts[1].isdigit():
                    raise ValueError("Использование: /act N")
                seat = int(parts[1])
                target = target_alive(seat)
                if not target or target.user_id == player.user_id:
                    raise ValueError("Некорректная цель.")
                game.actions[user_id] = {"verb": "infect", "targets": [seat]}

            elif role == "Почтальон":
                if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
                    raise ValueError("Использование: /act КОГО КОМУ")
                target_seat = int(parts[1])
                recipient_seat = int(parts[2])
                target = target_alive(target_seat)
                recipient = target_alive(recipient_seat)
                if not target or not recipient:
                    raise ValueError("Некорректные цели.")
                game.actions[user_id] = {"verb": "mail", "targets": [target_seat, recipient_seat]}

            elif role == "Тюремщик":
                if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
                    raise ValueError("Использование: /act N M")
                s1 = int(parts[1])
                s2 = int(parts[2])
                p1 = target_alive(s1)
                p2 = target_alive(s2)
                if not p1 or not p2 or s1 == s2 or p1.user_id == user_id or p2.user_id == user_id:
                    raise ValueError("Некорректные цели.")
                game.actions[user_id] = {"verb": "jail", "targets": [s1, s2]}
                game.current_jail = [p1.user_id, p2.user_id]
                game.jailer_uid = user_id

            elif role == "Ведьма":
                if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
                    raise ValueError("Использование: /act КОГО_КОНТРОЛИТЬ КУДА_ОТПРАВИТЬ")
                actor_seat = int(parts[1])
                target_seat = int(parts[2])
                actor_target = target_alive(actor_seat)
                force_target = target_alive(target_seat)
                if not actor_target or not force_target or actor_target.user_id == player.user_id:
                    raise ValueError("Некорректные цели.")
                game.actions[user_id] = {"verb": "control", "targets": [actor_seat, target_seat]}

            elif role in MAFIA_ROLES:
                if len(parts) == 2 and parts[1].isdigit():
                    seat = int(parts[1])
                    target = target_alive(seat)
                    if not target or target.role in MAFIA_ROLES:
                        raise ValueError("Некорректная цель.")
                    game.actions[user_id] = {"verb": "kill", "targets": [seat]}
                elif role == "Киллер Мафии" and len(parts) == 3 and parts[1] == "extra" and parts[2].isdigit():
                    seat = int(parts[2])
                    target = target_alive(seat)
                    if not target or target.role in MAFIA_ROLES:
                        raise ValueError("Некорректная цель.")
                    game.actions[user_id] = {"verb": "extra", "targets": [seat]}
                else:
                    raise ValueError("Использование: /act N или /act extra N")

            elif role in YAKUZA_ROLES:
                if len(parts) != 2 or not parts[1].isdigit():
                    raise ValueError("Использование: /act N")
                seat = int(parts[1])
                target = target_alive(seat)
                if not target or target.role in YAKUZA_ROLES:
                    raise ValueError("Некорректная цель.")
                game.actions[user_id] = {"verb": "kill", "targets": [seat]}

            else:
                return EngineResponse(ok=False, reply="Для вашей роли ночной ход пока не нужен в этой версии.")

        except ValueError as exc:
            return EngineResponse(ok=False, reply=str(exc))

        payload = game.actions.get(user_id, {})
self.storage.save_game(game)

confirmation = self._action_private_confirmation(game, player, payload)
notice = self._action_public_notice(game, player, payload)

broadcasts = []

if notice:
    broadcasts.append((game.chat_id, notice))

return EngineResponse(
    reply=confirmation,
    broadcasts=broadcasts,
)

    # -------------------------
    # Ночной резолвер
    # -------------------------

    def _pick_clan_action(
        self,
        game: Game,
        actions: Dict[int, dict],
        role_priority: List[str],
        role_set: Set[str],
    ) -> Optional[Tuple[int, int, str]]:
        candidates = [
            p for p in game.players.values()
            if p.alive and p.role in role_set
        ]
        candidates = sorted(candidates, key=lambda p: (role_priority.index(p.role), p.seat))

        for actor in candidates:
            act = actions.get(actor.user_id)
            if not act or act.get("verb") != "kill":
                continue
            target = self.seat_to_player(game, act["targets"][0])
            if not target or not target.alive:
                continue
            return actor.user_id, target.user_id, self.player_label(actor)
        return None

    def _default_controlled_action(self, role: str, forced_seat: int) -> Optional[dict]:
        if role == "Шериф":
            return {"verb": "inspect", "targets": [forced_seat]}
        if role == "Доктор":
            return {"verb": "heal", "targets": [forced_seat]}
        if role == "Куртизанка":
            return {"verb": "visit", "targets": [forced_seat]}
        if role == "Бомж":
            return {"verb": "watch", "targets": [forced_seat]}
        if role == "Маньяк":
            return {"verb": "kill", "targets": [forced_seat]}
        if role == "Путана":
            return {"verb": "infect", "targets": [forced_seat]}
        if role in MAFIA_ROLES or role in YAKUZA_ROLES:
            return {"verb": "kill", "targets": [forced_seat]}
        return None

    def _resolve_night(self, game: Game) -> Tuple[List[str], List[Tuple[int, str]]]:
        actions = copy.deepcopy(game.actions)
        dms: List[Tuple[int, str]] = []
        public_lines: List[str] = []

        blocked: Set[int] = set()
        protected: Set[int] = set()
        healed_targets: Set[int] = set()
        attacked_map: Dict[int, List[str]] = {}
        attacks: List[Tuple[str, int]] = []
        bum_watchers: List[Tuple[int, int]] = []
        visits: List[Tuple[int, int]] = []
        direct_infected: Set[int] = set()
        bum_saw_killer = False
        alerted_veterans: Set[int] = set()
        jailed: Set[int] = set()

        def valid_target(seat: int) -> Optional[Player]:
            p = self.seat_to_player(game, seat)
            if not p or not p.alive:
                return None
            return p

        def can_act(actor: Player) -> bool:
            return actor.alive and actor.user_id not in blocked and actor.user_id not in jailed

        def add_visit(actor_uid: int, target_uid: int) -> None:
            if actor_uid != target_uid:
                visits.append((actor_uid, target_uid))

        # 1. Амур
        if game.night == 1:
            for uid, act in actions.items():
                actor = game.players[uid]
                if not actor.alive or self.effective_role(game, actor) != "Амур":
                    continue
                targets = act.get("targets", [])
                if len(targets) != 2:
                    continue
                p1 = valid_target(targets[0])
                p2 = valid_target(targets[1])
                if not p1 or not p2 or p1.user_id == p2.user_id:
                    continue
                game.lovers[p1.user_id] = p2.user_id
                game.lovers[p2.user_id] = p1.user_id
                dms.append((p1.user_id, f"💘 Вы влюблены в {self.player_label(p2)}"))
                dms.append((p2.user_id, f"💘 Вы влюблены в {self.player_label(p1)}"))

        # 2. Ветеран
        for uid, act in actions.items():
            actor = game.players[uid]
            if not actor.alive or self.effective_role(game, actor) != "Ветеран":
                continue
            if act.get("verb") == "alert" and actor.alerts_left > 0:
                actor.alerts_left -= 1
                alerted_veterans.add(actor.user_id)
                protected.add(actor.user_id)
                dms.append((actor.user_id, f"🛡 Вы встали на защиту. Осталось защит: {actor.alerts_left}"))

        # 3. Ведьма
        for uid, act in actions.items():
            actor = game.players[uid]
            if not actor.alive or actor.role != "Ведьма":
                continue
            if act.get("verb") != "control":
                continue

            controlled_player = valid_target(act["targets"][0])
            forced_target = valid_target(act["targets"][1])
            if not controlled_player or not forced_target:
                continue

            controlled_role = self.effective_role(game, controlled_player)
            dms.append((actor.user_id, f"🪄 Вы узнали роль цели: <b>{controlled_player.role}</b>"))
            dms.append((controlled_player.user_id, "🪄 Этой ночью вами управляла Ведьма."))

            default_action = self._default_controlled_action(controlled_role, forced_target.seat)
            if not default_action:
                dms.append((actor.user_id, "🪄 Эту роль в MVP нельзя полноценно контролировать."))
                continue

            current = actions.get(controlled_player.user_id)
            if current and current.get("targets"):
                current["targets"][0] = forced_target.seat
                actions[controlled_player.user_id] = current
            else:
                actions[controlled_player.user_id] = default_action

        # 4. Тюремщик
        for uid, act in actions.items():
            actor = game.players[uid]
            if not actor.alive or actor.role != "Тюремщик":
                continue
            if act.get("verb") != "jail":
                continue
            targets = act.get("targets", [])
            if len(targets) != 2:
                continue
            p1 = valid_target(targets[0])
            p2 = valid_target(targets[1])
            if not p1 or not p2 or p1.user_id == p2.user_id:
                continue

            jailed.add(p1.user_id)
            jailed.add(p2.user_id)
            blocked.add(p1.user_id)
            blocked.add(p2.user_id)
            protected.add(p1.user_id)
            protected.add(p2.user_id)
            game.current_jail = [p1.user_id, p2.user_id]
            game.jailer_uid = actor.user_id

            dms.append((actor.user_id, f"🔒 В тюрьму помещены {self.player_label(p1)} и {self.player_label(p2)}"))
            dms.append((p1.user_id, f"🔒 Вы в тюрьме вместе с {self.player_label(p2)}"))
            dms.append((p2.user_id, f"🔒 Вы в тюрьме вместе с {self.player_label(p1)}"))

            same_mafia = p1.role in MAFIA_ROLES and p2.role in MAFIA_ROLES
            same_yakuza = p1.role in YAKUZA_ROLES and p2.role in YAKUZA_ROLES
            if same_mafia or same_yakuza:
                attacks.append(("Побег из тюрьмы", actor.user_id))

        # 5. Куртизанка
        for uid, act in actions.items():
            actor = game.players[uid]
            if self.effective_role(game, actor) != "Куртизанка" or not actor.alive:
                continue
            if not can_act(actor):
                continue
            if act.get("verb") != "visit":
                continue

            target = valid_target(act["targets"][0])
            if not target or target.user_id == actor.user_id:
                continue
            if actor.last_courtesan_target == target.user_id:
                dms.append((actor.user_id, "❌ Нельзя соблазнять одного и того же игрока две ночи подряд."))
                continue

            blocked.add(target.user_id)
            protected.add(target.user_id)
            actor.last_courtesan_target = target.user_id
            add_visit(actor.user_id, target.user_id)
            dms.append((actor.user_id, f"🌙 Вы забрали к себе {self.player_label(target)}"))

        # 6. Почтальон
        for uid, act in actions.items():
            actor = game.players[uid]
            if actor.role != "Почтальон" or not can_act(actor):
                continue
            if act.get("verb") != "mail":
                continue
            target = valid_target(act["targets"][0])
            recipient = valid_target(act["targets"][1])
            if not target or not recipient:
                continue
            add_visit(actor.user_id, target.user_id)
            dms.append((recipient.user_id, f"📨 Почтальон сообщает: роль {self.player_label(target)} — <b>{target.role}</b>"))
            dms.append((actor.user_id, f"📨 Письмо отправлено игроку {self.player_label(recipient)}"))

        # 7. Журналист
        for uid, act in actions.items():
            actor = game.players[uid]
            if self.effective_role(game, actor) != "Журналист" or not can_act(actor):
                continue
            if act.get("verb") != "compare":
                continue
            a = valid_target(act["targets"][0])
            b = valid_target(act["targets"][1])
            if not a or not b:
                continue
            res = "одинаковые" if journalist_group(a.role or "") == journalist_group(b.role or "") else "разные"
            dms.append((actor.user_id, f"📰 Проверка: {self.player_label(a)} и {self.player_label(b)} — {res}"))

        # 8. Шериф / Сержант
        for uid, act in actions.items():
            actor = game.players[uid]
            if not actor.alive or self.effective_role(game, actor) != "Шериф":
                continue
            if not can_act(actor):
                continue
            target = valid_target(act["targets"][0]) if act.get("targets") else None
            if not target:
                continue
            verb = act.get("verb")
            add_visit(actor.user_id, target.user_id)
            if verb == "inspect":
                dms.append((actor.user_id, f"👮 Проверка {self.player_label(target)}: {sheriff_view(target.role or '')}"))
            elif verb == "kill":
                attacks.append((f"Шериф ({self.player_label(actor)})", target.user_id))

        # 9. Доктор
        for uid, act in actions.items():
            actor = game.players[uid]
            if self.effective_role(game, actor) != "Доктор" or not can_act(actor):
                continue
            if act.get("verb") != "heal":
                continue
            target = valid_target(act["targets"][0])
            if not target:
                continue
            protected.add(target.user_id)
            healed_targets.add(target.user_id)
            add_visit(actor.user_id, target.user_id)
            dms.append((actor.user_id, f"🩺 Вы лечили {self.player_label(target)}"))

        # 10. Мафия
        mafia_choice = self._pick_clan_action(
            game,
            actions,
            ["Босс Мафии", "Киллер Мафии", "Подручный Мафии"],
            MAFIA_ROLES
        )
        if mafia_choice:
            actor_uid, target_uid, actor_label = mafia_choice
            actor = game.players[actor_uid]
            if can_act(actor):
                add_visit(actor_uid, target_uid)
                attacks.append((f"Мафия ({actor_label})", target_uid))

        # доп. выстрел киллера
        for uid, act in actions.items():
            actor = game.players[uid]
            if actor.role != "Киллер Мафии" or not can_act(actor):
                continue
            if act.get("verb") != "extra":
                continue
            target = valid_target(act["targets"][0])
            if not target or target.role in MAFIA_ROLES:
                continue
            add_visit(actor.user_id, target.user_id)
            attacks.append((f"Доп. выстрел мафии ({self.player_label(actor)})", target.user_id))

        # 11. Якудза
        yakuza_choice = self._pick_clan_action(
            game,
            actions,
            ["Босс Якудзы", "Ниндзя", "Подручный Якудзы"],
            YAKUZA_ROLES
        )
        if yakuza_choice:
            actor_uid, target_uid, actor_label = yakuza_choice
            actor = game.players[actor_uid]
            if can_act(actor):
                add_visit(actor_uid, target_uid)
                attacks.append((f"Якудза ({actor_label})", target_uid))

        # 12. Маньяк
        for uid, act in actions.items():
            actor = game.players[uid]
            if actor.role != "Маньяк" or not can_act(actor):
                continue
            if act.get("verb") != "kill":
                continue
            target = valid_target(act["targets"][0])
            if not target or target.user_id == actor.user_id:
                continue
            add_visit(actor.user_id, target.user_id)
            attacks.append((f"Маньяк ({self.player_label(actor)})", target.user_id))

        # 13. Путана
        for uid, act in actions.items():
            actor = game.players[uid]
            if actor.role != "Путана" or not can_act(actor):
                continue
            if act.get("verb") != "infect":
                continue
            target = valid_target(act["targets"][0])
            if not target or target.user_id == actor.user_id:
                continue
            add_visit(actor.user_id, target.user_id)
            direct_infected.add(target.user_id)
            dms.append((actor.user_id, f"☣️ Вы заразили {self.player_label(target)}"))

        # 14. Бомж
        for uid, act in actions.items():
            actor = game.players[uid]
            if self.effective_role(game, actor) != "Бомж" or not can_act(actor):
                continue
            if act.get("verb") != "watch":
                continue
            target = valid_target(act["targets"][0])
            if not target:
                continue
            bum_watchers.append((actor.user_id, target.user_id))

        # Ветеран убивает посетителей
        for veteran_uid in alerted_veterans:
            veteran = game.players[veteran_uid]
            for visitor_uid, target_uid in visits:
                if target_uid == veteran_uid and game.players[visitor_uid].alive:
                    attacks.append((f"Ветеран ({self.player_label(veteran)})", visitor_uid))

        # Инфекция путаны
        infected_now = {p.user_id for p in game.players.values() if p.alive and p.infected}
        infected_now |= direct_infected

        for visitor_uid, target_uid in visits:
            if visitor_uid in infected_now or target_uid in infected_now:
                if game.players[visitor_uid].role != "Путана":
                    infected_now.add(visitor_uid)
                if game.players[target_uid].role != "Путана":
                    infected_now.add(target_uid)

        for uid in infected_now:
            if uid in game.players and game.players[uid].alive and game.players[uid].role != "Путана":
                game.players[uid].infected = True

        for uid in healed_targets:
            if uid in game.players and game.players[uid].role != "Путана":
                game.players[uid].infected = False

        # Разбор атак
        for source_name, target_uid in attacks:
            target = game.players[target_uid]
            if not target.alive:
                continue
            if target.user_id in protected:
                continue
            if target.role == "Ведьма" and target.witch_barrier:
                target.witch_barrier = False
                dms.append((target.user_id, "🪄 Магический барьер сработал и исчез."))
                continue
            attacked_map.setdefault(target_uid, []).append(source_name)

        if not attacked_map:
            public_lines.append("🌙 Ночь прошла без смертей.")
        else:
            for target_uid in sorted(attacked_map.keys(), key=lambda uid: game.players[uid].seat):
                self._kill_player(game, target_uid, public_lines, "Ночью погиб(ла)")

        # Бомж
        for watcher_uid, watched_uid in bum_watchers:
            if watched_uid in attacked_map:
                killers = ", ".join(attacked_map[watched_uid])
                dms.append((watcher_uid, f"🧥 Вашу цель убили. Убийца(ы): {killers}"))
                bum_saw_killer = True
            else:
                dms.append((watcher_uid, "🧥 Игрок жив."))

        if bum_saw_killer:
            public_lines.append("🧥 Этой ночью Бомж видел убийцу.")

        winner = self._check_winner(game)
        if winner:
            public_lines.append(f"🏆 {winner}")
            game.phase = "ENDED"

        return public_lines, dms
