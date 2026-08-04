"""对话存储服务 — SQLite 记录对话历史

表结构：
    conversations: id, title, model, created_at, updated_at
    messages: id, conversation_id, role, content, created_at
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = None  # 由 paths.py 动态决定


@dataclass
class Conversation:
    id: int
    title: str
    model: str = ""
    auto_name: bool = True
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class Message:
    id: int
    conversation_id: int
    role: str          # user / assistant / system
    content: str
    created_at: float = 0.0


class ChatStore:
    """对话存储 — 线程安全（每调用每连接）"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            try:
                from utils.paths import get_chat_db_path
                db_path = get_chat_db_path()
            except Exception:
                db_path = os.path.join("data", "chat_history.db")
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL DEFAULT '新对话',
                    model TEXT NOT NULL DEFAULT '',
                    auto_name INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                );
                CREATE INDEX IF NOT EXISTS idx_messages_conv
                    ON messages(conversation_id);
            """)
            # 迁移：老库补充 auto_name 列
            cols = [r[1] for r in conn.execute(
                "PRAGMA table_info(conversations)").fetchall()]
            if "auto_name" not in cols:
                conn.execute(
                    "ALTER TABLE conversations "
                    "ADD COLUMN auto_name INTEGER NOT NULL DEFAULT 1"
                )

    # ---------------------------------------------------------- 对话
    def create_conversation(self, title: str = "新对话",
                            model: str = "") -> Conversation:
        now = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO conversations (title, model, auto_name, "
                "created_at, updated_at) VALUES (?, ?, 1, ?, ?)",
                (title, model, now, now),
            )
            conv_id = cur.lastrowid
            return Conversation(id=conv_id, title=title, model=model,
                                auto_name=True,
                                created_at=now, updated_at=now)

    def list_conversations(self) -> list[Conversation]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC"
            ).fetchall()
            return [Conversation(
                id=r["id"], title=r["title"], model=r["model"],
                auto_name=bool(r["auto_name"]),
                created_at=r["created_at"], updated_at=r["updated_at"],
            ) for r in rows]

    def get_conversation(self, conv_id: int) -> Optional[Conversation]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conv_id,)
            ).fetchone()
            if r is None:
                return None
            return Conversation(
                id=r["id"], title=r["title"], model=r["model"],
                auto_name=bool(r["auto_name"]),
                created_at=r["created_at"], updated_at=r["updated_at"],
            )

    def rename_conversation(self, conv_id: int, title: str):
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title, now, conv_id),
            )

    def set_conversation_model(self, conv_id: int, model: str):
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "UPDATE conversations SET model = ?, updated_at = ? WHERE id = ?",
                (model, now, conv_id),
            )

    def set_auto_name(self, conv_id: int, enabled: bool):
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "UPDATE conversations SET auto_name = ?, updated_at = ? "
                "WHERE id = ?",
                (1 if enabled else 0, now, conv_id),
            )

    def delete_conversation(self, conv_id: int):
        with self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
            conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))

    # ---------------------------------------------------------- 消息
    def add_message(self, conv_id: int, role: str, content: str) -> Message:
        now = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (conv_id, role, content, now),
            )
            msg_id = cur.lastrowid
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conv_id),
            )
            return Message(id=msg_id, conversation_id=conv_id,
                           role=role, content=content, created_at=now)

    def list_messages(self, conv_id: int) -> list[Message]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? "
                "ORDER BY created_at ASC",
                (conv_id,),
            ).fetchall()
            return [Message(
                id=r["id"], conversation_id=r["conversation_id"],
                role=r["role"], content=r["content"],
                created_at=r["created_at"],
            ) for r in rows]
