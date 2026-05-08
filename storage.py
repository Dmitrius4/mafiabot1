import json
import sqlite3
from typing import List, Optional

from models import Game


class SQLiteStorage:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    chat_id INTEGER PRIMARY KEY,
                    state_json TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS private_users (
                    user_id INTEGER PRIMARY KEY
                )
            """)

            conn.commit()

    def save_game(self, game: Game) -> None:
        state_json = json.dumps(game.to_dict(), ensure_ascii=False)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO games(chat_id, state_json)
                VALUES (?, ?)
                """,
                (game.chat_id, state_json),
            )
            conn.commit()

    def load_game(self, chat_id: int) -> Optional[Game]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT state_json
                FROM games
                WHERE chat_id = ?
                """,
                (chat_id,),
            ).fetchone()

        if not row:
            return None

        data = json.loads(row["state_json"])
        return Game.from_dict(data)

    def delete_game(self, chat_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM games
                WHERE chat_id = ?
                """,
                (chat_id,),
            )
            conn.commit()

    def load_all_games(self) -> List[Game]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT state_json
                FROM games
                """
            ).fetchall()

        result = []

        for row in rows:
            data = json.loads(row["state_json"])
            result.append(Game.from_dict(data))

        return result

    def mark_private_started(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO private_users(user_id)
                VALUES (?)
                """,
                (user_id,),
            )
            conn.commit()

    def has_private_started(self, user_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT user_id
                FROM private_users
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()

        return row is not None

    def find_game_by_user(self, user_id: int) -> Optional[Game]:
        for game in self.load_all_games():
            if game.phase != "ENDED" and user_id in game.players:
                return game

        return None
