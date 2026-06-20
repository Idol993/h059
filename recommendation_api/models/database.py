import aiosqlite
from typing import List, Dict, Any, Optional, Tuple
import json
import os
from core.config import settings


class Database:
    _instance: Optional["Database"] = None

    def __new__(cls) -> "Database":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def init(self) -> None:
        os.makedirs(os.path.dirname(settings.items_db_path), exist_ok=True)
        os.makedirs(os.path.dirname(settings.behaviors_db_path), exist_ok=True)
        await self._init_items_db()
        await self._init_behaviors_db()

    async def _init_items_db(self) -> None:
        async with aiosqlite.connect(settings.items_db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    categories TEXT,
                    tags TEXT,
                    features_json TEXT,
                    likes INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    views INTEGER DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_items_categories ON items(categories)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_items_created_at ON items(created_at)"
            )
            await db.commit()

    async def _init_behaviors_db(self) -> None:
        async with aiosqlite.connect(settings.behaviors_db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS behaviors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    item_id INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    ab_group TEXT DEFAULT 'default'
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_behaviors_user ON behaviors(user_id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_behaviors_item ON behaviors(item_id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_behaviors_timestamp ON behaviors(timestamp)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_behaviors_user_item ON behaviors(user_id, item_id)"
            )
            await db.commit()

    async def add_item(
        self,
        title: str,
        description: str = "",
        categories: List[str] = None,
        tags: List[str] = None,
        features: Dict[str, Any] = None,
        created_at: int = None,
    ) -> int:
        import time
        if created_at is None:
            created_at = int(time.time())
        if categories is None:
            categories = []
        if tags is None:
            tags = []
        if features is None:
            features = {}

        features_json = json.dumps(features, ensure_ascii=False)
        categories_str = json.dumps(categories, ensure_ascii=False)
        tags_str = json.dumps(tags, ensure_ascii=False)

        async with aiosqlite.connect(settings.items_db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO items
                (title, description, categories, tags, features_json, likes, comments, views, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
                """,
                (title, description, categories_str, tags_str, features_json, created_at, created_at),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_item(self, item_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(settings.items_db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM items WHERE id = ?", (item_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._row_to_item_dict(row)
                return None

    async def get_items(self, item_ids: List[int]) -> List[Dict[str, Any]]:
        if not item_ids:
            return []
        placeholders = ",".join(["?" for _ in item_ids])
        async with aiosqlite.connect(settings.items_db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                f"SELECT * FROM items WHERE id IN ({placeholders})",
                item_ids,
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_item_dict(row) for row in rows]

    async def get_all_items(self, limit: int = 10000) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(settings.items_db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM items ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_item_dict(row) for row in rows]

    async def update_item_stats(self, item_id: int, action_type: str) -> None:
        column_map = {
            "view": "views",
            "like": "likes",
            "favorite": "likes",
            "comment": "comments",
            "click": "views",
        }
        column = column_map.get(action_type)
        if not column:
            return

        async with aiosqlite.connect(settings.items_db_path) as db:
            await db.execute(
                f"UPDATE items SET {column} = {column} + 1, updated_at = ? WHERE id = ?",
                (int(__import__("time").time()), item_id),
            )
            await db.commit()

    async def add_behavior(
        self,
        user_id: int,
        item_id: int,
        action_type: str,
        timestamp: int,
        ab_group: str = "default",
    ) -> int:
        async with aiosqlite.connect(settings.behaviors_db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO behaviors (user_id, item_id, action_type, timestamp, ab_group)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, item_id, action_type, timestamp, ab_group),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_user_behaviors(self, user_id: int, limit: int = 1000) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(settings.behaviors_db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM behaviors WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
                (user_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_user_behavior_count(self, user_id: int) -> int:
        async with aiosqlite.connect(settings.behaviors_db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM behaviors WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_all_behaviors_for_training(
        self, since_timestamp: int = 0
    ) -> List[Tuple[int, int, float]]:
        action_weights = {
            "view": 1.0,
            "click": 1.5,
            "like": 3.0,
            "favorite": 4.0,
            "comment": 5.0,
            "share": 6.0,
        }

        async with aiosqlite.connect(settings.behaviors_db_path) as db:
            async with db.execute(
                """
                SELECT user_id, item_id, action_type, MAX(timestamp) as latest_time
                FROM behaviors
                WHERE timestamp >= ?
                GROUP BY user_id, item_id, action_type
                """,
                (since_timestamp,),
            ) as cursor:
                rows = await cursor.fetchall()
                result = []
                seen = set()
                for row in rows:
                    user_id, item_id, action_type, _ = row
                    key = (user_id, item_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    rating = action_weights.get(action_type, 1.0)
                    result.append((user_id, item_id, rating))
                return result

    async def get_recent_behaviors(self, limit: int = 10000) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(settings.behaviors_db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM behaviors ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    def _row_to_item_dict(self, row: aiosqlite.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "description": row["description"] or "",
            "categories": json.loads(row["categories"]) if row["categories"] else [],
            "tags": json.loads(row["tags"]) if row["tags"] else [],
            "features": json.loads(row["features_json"]) if row["features_json"] else {},
            "likes": row["likes"],
            "comments": row["comments"],
            "views": row["views"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


database = Database()


async def get_database() -> Database:
    await database.init()
    return database
