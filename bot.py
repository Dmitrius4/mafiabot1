import telebot

from config import BOT_TOKEN, DB_PATH
from engine import Engine, EngineResponse
from storage import SQLiteStorage
from models import MAFIA_ROLES, YAKUZA_ROLES


bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
storage = SQLiteStorage(DB_PATH)
engine = Engine(storage)


def is_group(message) -> bool:
    return message.chat.type in ("group", "supergroup")


def safe_send_dm(user_id: int, text: str) -> None:
    try:
        bot.send_message(user_id, text)
    except Exception:
        pass


def apply_response(message, response: EngineResponse) -> None:
    if response.reply:
        bot.reply_to(message, response.reply)

    for chat_id, text in response.broadcasts:
        bot.send_message(chat_id, text)

    for user_id, text in response.dms:
        safe_send_dm(user_id, text)


def command_name(text: str) -> str:
    first = text.strip().split()[0]
    first = first.split("@")[0]
    return first.lower()


def command_args(text: str) -> list:
    return text.strip().split()[1:]


def require_digits(args: list, count: int, usage: str) -> tuple:
    if len(args) != count:
        return False, usage

    for arg in args:
        if not arg.isdigit():
            return False, usage

    return True, ""


def reply_usage(message, usage: str) -> None:
    bot.reply_to(
        message,
        f"Неверный формат команды.\n\nИспользование:\n{usage}"
    )


def run_named_night_action(message, pseudo_text: str, allowed_roles: set, usage: str) -> None:
    response = engine.submit_named_action(
        user_id=message.from_user.id,
        pseudo_text=pseudo_text,
        allowed_roles=allowed_roles,
        usage_text=usage,
    )
    apply_response(message, response)


# -------------------------
# Группа: основные команды
# -------------------------

@bot.message_handler(commands=["newgame"])
def cmd_newgame(message):
    if not is_group(message):
        return

    response = engine.create_game(
        chat_id=message.chat.id,
        host_id=message.from_user.id,
        host_name=message.from_user.first_name or "Ведущий",
    )
    apply_response(message, response)


@bot.message_handler(commands=["join"])
def cmd_join(message):
    if not is_group(message):
        return

    response = engine.join_game(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        name=message.from_user.first_name or "Игрок",
        username=message.from_user.username or "",
    )
    apply_response(message, response)


@bot.message_handler(commands=["leave"])
def cmd_leave(message):
    if not is_group(message):
        return

    response = engine.leave_game(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
    )
    apply_response(message, response)


@bot.message_handler(commands=["players"])
def cmd_players(message):
    if not is_group(message):
        return

    response = engine.players_list(message.chat.id)
    apply_response(message, response)


@bot.message_handler(commands=["roles"])
def cmd_roles(message):
    if not is_group(message):
        return

    response = engine.roles_list(message.chat.id)
    apply_response(message, response)


@bot.message_handler(commands=["closegame"])
def cmd_closegame(message):
    if not is_group(message):
        return

    response = engine.close_game(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
    )
    apply_response(message, response)


@bot.message_handler(commands=["startgame"])
def cmd_startgame(message):
    if not is_group(message):
        return

    response = engine.start_game(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
    )
    apply_response(message, response)


@bot.message_handler(commands=["status"])
def cmd_status(message):
    if not is_group(message):
        return

    response = engine.status(message.chat.id)
    apply_response(message, response)


@bot.message_handler(commands=["night"])
def cmd_night(message):
    if not is_group(message):
        return

    response = engine.open_night(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
    )
    apply_response(message, response)


@bot.message_handler(commands=["day"])
def cmd_day(message):
    if not is_group(message):
        return

    response = engine.open_day(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
    )
    apply_response(message, response)


@bot.message_handler(commands=["openvote"])
def cmd_openvote(message):
    if not is_group(message):
        return

    response = engine.open_vote(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
    )
    apply_response(message, response)


@bot.message_handler(commands=["vote"])
def cmd_vote(message):
    if not is_group(message):
        return

    parts = message.text.split()

    if len(parts) != 2 or not parts[1].isdigit():
        bot.reply_to(message, "Использование: /vote N")
        return

    response = engine.vote(
        chat_id=message.chat.id,
        voter_id=message.from_user.id,
        seat=int(parts[1]),
    )
    apply_response(message, response)


@bot.message_handler(commands=["closevote"])
def cmd_closevote(message):
    if not is_group(message):
        return

    response = engine.close_vote(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
    )
    apply_response(message, response)


@bot.message_handler(commands=["actions"])
def cmd_actions(message):
    if not is_group(message):
        return

    response = engine.night_actions_status(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
    )
    apply_response(message, response)


@bot.message_handler(commands=["remind"])
def cmd_remind(message):
    if not is_group(message):
        return

    response = engine.remind_night_actions(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
    )
    apply_response(message, response)


# -------------------------
# Личка: старые резервные команды
# -------------------------

@bot.message_handler(commands=["start"])
def cmd_start(message):
    if is_group(message):
        return

    response = engine.private_start(message.from_user.id)
    apply_response(message, response)


@bot.message_handler(commands=["myrole"])
def cmd_myrole(message):
    if is_group(message):
        return

    response = engine.my_role(message.from_user.id)
    apply_response(message, response)


@bot.message_handler(commands=["act"])
def cmd_act(message):
    if is_group(message):
        return

    response = engine.submit_action(message.from_user.id, message.text)
    apply_response(message, response)


@bot.message_handler(commands=["judge"])
def cmd_judge(message):
    if is_group(message):
        return

    response = engine.judge(message.from_user.id, message.text)
    apply_response(message, response)


@bot.message_handler(commands=["shoot"])
def cmd_shoot(message):
    if is_group(message):
        return

    response = engine.shoot(message.from_user.id, message.text)
    apply_response(message, response)


@bot.message_handler(commands=["team"])
def cmd_team(message):
    if is_group(message):
        return

    response = engine.team_message(message.from_user.id, message.text)
    apply_response(message, response)


@bot.message_handler(commands=["station"])
def cmd_station(message):
    if is_group(message):
        return

    response = engine.station(message.from_user.id, message.text)
    apply_response(message, response)


@bot.message_handler(commands=["jailgun"])
def cmd_jailgun(message):
    if is_group(message):
        return

    response = engine.jailgun(message.from_user.id, message.text)
    apply_response(message, response)


@bot.message_handler(commands=["jailshoot"])
def cmd_jailshoot(message):
    if is_group(message):
        return

    response = engine.jailshoot(message.from_user.id, message.text)
    apply_response(message, response)


# -------------------------
# Группа: русские команды
# -------------------------

@bot.message_handler(func=lambda message: is_group(message) and bool(message.text) and message.text.startswith("/"))
def cmd_group_russian(message):
    text = message.text.strip()
    cmd = command_name(text)
    args = command_args(text)

    if cmd == "/игроки":
        if args:
            reply_usage(message, "/игроки")
            return

        response = engine.players_list(message.chat.id)
        apply_response(message, response)
        return

    if cmd == "/роли":
        if args:
            reply_usage(message, "/роли")
            return

        response = engine.roles_list(message.chat.id)
        apply_response(message, response)
        return

    if cmd == "/ходы":
        if args:
            reply_usage(message, "/ходы")
            return

        response = engine.night_actions_status(
            chat_id=message.chat.id,
            user_id=message.from_user.id,
        )
        apply_response(message, response)
        return

    if cmd == "/напомнить":
        if args:
            reply_usage(message, "/напомнить")
            return

        response = engine.remind_night_actions(
            chat_id=message.chat.id,
            user_id=message.from_user.id,
        )
        apply_response(message, response)
        return


# -------------------------
# Личка: русские команды ролей
# -------------------------

@bot.message_handler(func=lambda message: (not is_group(message)) and bool(message.text) and message.text.startswith("/"))
def cmd_private_russian(message):
    text = message.text.strip()
    cmd = command_name(text)
    args = command_args(text)

    if cmd == "/ход":
        response = engine.action_help(message.from_user.id)
        apply_response(message, response)
        return

    # Шериф / Сержант

    if cmd == "/проверить":
        usage = "/проверить N\nПример: /проверить 5"
        ok, err = require_digits(args, 1, usage)
        if not ok:
            reply_usage(message, err)
            return

        run_named_night_action(
            message,
            pseudo_text=f"/act inspect {args[0]}",
            allowed_roles={"Шериф"},
            usage=usage,
        )
        return

    if cmd == "/убить":
        usage = "/убить N\nПример: /убить 5"
        ok, err = require_digits(args, 1, usage)
        if not ok:
            reply_usage(message, err)
            return

        run_named_night_action(
            message,
            pseudo_text=f"/act kill {args[0]}",
            allowed_roles={"Шериф"},
            usage=usage,
        )
        return

    if cmd == "/охранять_участок":
        usage = "/охранять_участок"

        if args:
            reply_usage(message, usage)
            return

        run_named_night_action(
            message,
            pseudo_text="/act guard_station",
            allowed_roles={"Шериф"},
            usage=usage,
        )
        return

    if cmd == "/участок":
        if args:
            reply_usage(message, "/участок")
            return

        response = engine.station(message.from_user.id, "/station list")
        apply_response(message, response)
        return

    if cmd == "/участок_добавить":
        usage = "/участок_добавить N\nПример: /участок_добавить 5"
        ok, err = require_digits(args, 1, usage)

        if not ok:
            reply_usage(message, err)
            return

        response = engine.station(message.from_user.id, f"/station add {args[0]}")
        apply_response(message, response)
        return

    if cmd == "/участок_убрать":
        usage = "/участок_убрать N\nПример: /участок_убрать 5"
        ok, err = require_digits(args, 1, usage)

        if not ok:
            reply_usage(message, err)
            return

        response = engine.station(message.from_user.id, f"/station remove {args[0]}")
        apply_response(message, response)
        return

    # Доктор

    if cmd == "/лечить":
        usage = "/лечить N\nПример: /лечить 5"
        ok, err = require_digits(args, 1, usage)

        if not ok:
            reply_usage(message, err)
            return

        run_named_night_action(
            message,
            pseudo_text=f"/act {args[0]}",
            allowed_roles={"Доктор"},
            usage=usage,
        )
        return

    # Куртизанка

    if cmd == "/соблазнить":
        usage = "/соблазнить N\nПример: /соблазнить 5"
        ok, err = require_digits(args, 1, usage)

        if not ok:
            reply_usage(message, err)
            return

        run_named_night_action(
            message,
            pseudo_text=f"/act {args[0]}",
            allowed_roles={"Куртизанка"},
            usage=usage,
        )
        return

    # Журналист

    if cmd == "/сравнить":
        usage = "/сравнить N M\nПример: /сравнить 3 7"
        ok, err = require_digits(args, 2, usage)

        if not ok:
            reply_usage(message, err)
            return

        run_named_night_action(
            message,
            pseudo_text=f"/act {args[0]} {args[1]}",
            allowed_roles={"Журналист"},
            usage=usage,
        )
        return

    # Бомж

    if cmd == "/следить":
        usage = "/следить N\nПример: /следить 5"
        ok, err = require_digits(args, 1, usage)

        if not ok:
            reply_usage(message, err)
            return

        run_named_night_action(
            message,
            pseudo_text=f"/act {args[0]}",
            allowed_roles={"Бомж"},
            usage=usage,
        )
        return

    # Почтальон

    if cmd == "/письмо":
        usage = "/письмо КОГО КОМУ\nПример: /письмо 3 7"
        ok, err = require_digits(args, 2, usage)

        if not ok:
            reply_usage(message, err)
            return

        run_named_night_action(
            message,
            pseudo_text=f"/act {args[0]} {args[1]}",
            allowed_roles={"Почтальон"},
            usage=usage,
        )
        return

    # Тюремщик

    if cmd == "/посадить":
        usage = "/посадить N M\nПример: /посадить 3 7"
        ok, err = require_digits(args, 2, usage)

        if not ok:
            reply_usage(message, err)
            return

        run_named_night_action(
            message,
            pseudo_text=f"/act {args[0]} {args[1]}",
            allowed_roles={"Тюремщик"},
            usage=usage,
        )
        return

    if cmd == "/оружие":
        usage = "/оружие N\nПример: /оружие 3"
        ok, err = require_digits(args, 1, usage)

        if not ok:
            reply_usage(message, err)
            return

        response = engine.jailgun(message.from_user.id, f"/jailgun {args[0]}")
        apply_response(message, response)
        return

    if cmd == "/тюрьма_выстрел":
        usage = "/тюрьма_выстрел N\nПример: /тюрьма_выстрел 7"
        ok, err = require_digits(args, 1, usage)

        if not ok:
            reply_usage(message, err)
            return

        response = engine.jailshoot(message.from_user.id, f"/jailshoot {args[0]}")
        apply_response(message, response)
        return

    # Стрелок

    if cmd == "/стрелять":
        usage = "/стрелять N\nПример: /стрелять 5"
        ok, err = require_digits(args, 1, usage)

        if not ok:
            reply_usage(message, err)
            return

        response = engine.shoot(message.from_user.id, f"/shoot {args[0]}")
        apply_response(message, response)
        return

    # Амур

    if cmd == "/влюбить":
        usage = "/влюбить N M\nПример: /влюбить 3 8"
        ok, err = require_digits(args, 2, usage)

        if not ok:
            reply_usage(message, err)
            return

        run_named_night_action(
            message,
            pseudo_text=f"/act {args[0]} {args[1]}",
            allowed_roles={"Амур"},
            usage=usage,
        )
        return

    # Ветеран

    if cmd == "/защищаться":
        usage = "/защищаться"

        if args:
            reply_usage(message, usage)
            return

        run_named_night_action(
            message,
            pseudo_text="/act alert",
            allowed_roles={"Ветеран"},
            usage=usage,
        )
        return

    # Маньяк

    if cmd == "/зарезать":
        usage = "/зарезать N\nПример: /зарезать 5"
        ok, err = require_digits(args, 1, usage)

        if not ok:
            reply_usage(message, err)
            return

        run_named_night_action(
            message,
            pseudo_text=f"/act {args[0]}",
            allowed_roles={"Маньяк"},
            usage=usage,
        )
        return

    # Путана

    if cmd == "/заразить":
        usage = "/заразить N\nПример: /заразить 5"
        ok, err = require_digits(args, 1, usage)

        if not ok:
            reply_usage(message, err)
            return

        run_named_night_action(
            message,
            pseudo_text=f"/act {args[0]}",
            allowed_roles={"Путана"},
            usage=usage,
        )
        return

    # Ведьма

    if cmd == "/контроль":
        usage = "/контроль КОГО КУДА\nПример: /контроль 3 7"
        ok, err = require_digits(args, 2, usage)

        if not ok:
            reply_usage(message, err)
            return

        run_named_night_action(
            message,
            pseudo_text=f"/act {args[0]} {args[1]}",
            allowed_roles={"Ведьма"},
            usage=usage,
        )
        return

    # Мафия

    if cmd == "/мафия_убить":
        usage = "/мафия_убить N\nПример: /мафия_убить 5"
        ok, err = require_digits(args, 1, usage)

        if not ok:
            reply_usage(message, err)
            return

        run_named_night_action(
            message,
            pseudo_text=f"/act {args[0]}",
            allowed_roles=set(MAFIA_ROLES),
            usage=usage,
        )
        return

    if cmd == "/доп_выстрел":
        usage = "/доп_выстрел N\nПример: /доп_выстрел 5"
        ok, err = require_digits(args, 1, usage)

        if not ok:
            reply_usage(message, err)
            return

        run_named_night_action(
            message,
            pseudo_text=f"/act extra {args[0]}",
            allowed_roles={"Киллер Мафии"},
            usage=usage,
        )
        return

    # Якудза

    if cmd == "/якудза_убить":
        usage = "/якудза_убить N\nПример: /якудза_убить 5"
        ok, err = require_digits(args, 1, usage)

        if not ok:
            reply_usage(message, err)
            return

        run_named_night_action(
            message,
            pseudo_text=f"/act {args[0]}",
            allowed_roles=set(YAKUZA_ROLES),
            usage=usage,
        )
        return

    # Судья

    if cmd == "/помиловать":
        usage = "/помиловать"

        if args:
            reply_usage(message, usage)
            return

        response = engine.judge(message.from_user.id, "/judge pardon")
        apply_response(message, response)
        return

    if cmd == "/казнить":
        usage = "/казнить N\nПример: /казнить 5"
        ok, err = require_digits(args, 1, usage)

        if not ok:
            reply_usage(message, err)
            return

        response = engine.judge(message.from_user.id, f"/judge {args[0]}")
        apply_response(message, response)
        return


if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30,
    )
