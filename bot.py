import telebot

from config import BOT_TOKEN, DB_PATH
from engine import Engine, EngineResponse
from storage import SQLiteStorage


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


# -------------------------
# Группа
# -------------------------

@bot.message_handler(commands=["newgame"])
def cmd_newgame(message):
    if not is_group(message):
        return
    response = engine.create_game(
        chat_id=message.chat.id,
        host_id=message.from_user.id,
        host_name=message.from_user.first_name or "Ведущий"
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
        username=message.from_user.username or ""
    )
    apply_response(message, response)


@bot.message_handler(commands=["leave"])
def cmd_leave(message):
    if not is_group(message):
        return
    response = engine.leave_game(
        chat_id=message.chat.id,
        user_id=message.from_user.id
    )
    apply_response(message, response)


@bot.message_handler(commands=["players"])
def cmd_players(message):
    if not is_group(message):
        return
    response = engine.players_list(message.chat.id)
    apply_response(message, response)


@bot.message_handler(commands=["closegame"])
def cmd_closegame(message):
    if not is_group(message):
        return
    response = engine.close_game(
        chat_id=message.chat.id,
        user_id=message.from_user.id
    )
    apply_response(message, response)


@bot.message_handler(commands=["startgame"])
def cmd_startgame(message):
    if not is_group(message):
        return
    response = engine.start_game(
        chat_id=message.chat.id,
        user_id=message.from_user.id
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
        user_id=message.from_user.id
    )
    apply_response(message, response)


@bot.message_handler(commands=["day"])
def cmd_day(message):
    if not is_group(message):
        return
    response = engine.open_day(
        chat_id=message.chat.id,
        user_id=message.from_user.id
    )
    apply_response(message, response)


@bot.message_handler(commands=["openvote"])
def cmd_openvote(message):
    if not is_group(message):
        return
    response = engine.open_vote(
        chat_id=message.chat.id,
        user_id=message.from_user.id
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
        seat=int(parts[1])
    )
    apply_response(message, response)


@bot.message_handler(commands=["closevote"])
def cmd_closevote(message):
    if not is_group(message):
        return
    response = engine.close_vote(
        chat_id=message.chat.id,
        user_id=message.from_user.id
    )
    apply_response(message, response)


# -------------------------
# Личка
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


if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)