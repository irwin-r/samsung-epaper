"""SQLite database with aiosqlite — schema, migrations, repositories."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from .models import Asset, Collection, Favourite, HistoryEntry, Preset, Schedule

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    filename_original TEXT NOT NULL,
    filename_processed TEXT,
    filename_thumbnail TEXT,
    source_type TEXT NOT NULL,
    source_id TEXT,
    title TEXT,
    width INTEGER,
    height INTEGER,
    file_size INTEGER,
    mime_type TEXT DEFAULT 'image/png',
    sha256 TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS display_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id TEXT NOT NULL REFERENCES assets(id),
    displayed_at TEXT NOT NULL DEFAULT (datetime('now')),
    content_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS presets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    source_config_json TEXT NOT NULL,
    image_config_json TEXT,
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS collections (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    parent_id TEXT REFERENCES collections(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS favourites (
    id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES assets(id),
    collection_id TEXT REFERENCES collections(id),
    name TEXT,
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(asset_id, collection_id)
);

CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    preset_id TEXT NOT NULL REFERENCES presets(id),
    name TEXT NOT NULL,
    cron_expression TEXT NOT NULL,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    last_run_at TEXT,
    next_run_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_assets_sha256 ON assets(sha256);
CREATE INDEX IF NOT EXISTS idx_assets_source ON assets(source_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_displayed ON display_history(displayed_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_content_id ON display_history(content_id);
CREATE INDEX IF NOT EXISTS idx_presets_active ON presets(is_active);
CREATE INDEX IF NOT EXISTS idx_favourites_asset ON favourites(asset_id);
CREATE INDEX IF NOT EXISTS idx_favourites_collection ON favourites(collection_id);
CREATE INDEX IF NOT EXISTS idx_collections_parent ON collections(parent_id);
CREATE INDEX IF NOT EXISTS idx_schedules_enabled ON schedules(is_enabled);
"""


async def init_db(db_path: str) -> aiosqlite.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")

    # Migrate existing database: add columns that may not exist
    try:
        await db.execute("ALTER TABLE assets ADD COLUMN sha256 TEXT")
        logger.info("Migration: added sha256 column to assets")
    except Exception:
        pass  # Column already exists

    await db.executescript(SCHEMA_SQL)
    # Record schema version
    await db.execute(
        "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
        (SCHEMA_VERSION,),
    )
    await db.commit()
    logger.info(f"Database initialized at {db_path} (schema v{SCHEMA_VERSION})")
    return db


class AssetRepository:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def create(
        self,
        source_type: str,
        filename_original: str,
        source_id: Optional[str] = None,
        title: Optional[str] = None,
        metadata_json: Optional[str] = None,
        sha256: Optional[str] = None,
    ) -> str:
        asset_id = str(uuid.uuid4())
        await self.db.execute(
            """INSERT INTO assets (id, filename_original, source_type, source_id, title, metadata_json, sha256)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (asset_id, filename_original, source_type, source_id, title, metadata_json, sha256),
        )
        await self.db.commit()
        return asset_id

    async def update_processed(
        self,
        asset_id: str,
        filename_processed: str,
        filename_thumbnail: Optional[str],
        width: int,
        height: int,
        file_size: int,
        sha256: Optional[str] = None,
    ) -> None:
        if sha256 is not None:
            await self.db.execute(
                """UPDATE assets
                   SET filename_processed = ?, filename_thumbnail = ?,
                       width = ?, height = ?, file_size = ?, sha256 = ?
                   WHERE id = ?""",
                (filename_processed, filename_thumbnail, width, height, file_size, sha256, asset_id),
            )
        else:
            await self.db.execute(
                """UPDATE assets
                   SET filename_processed = ?, filename_thumbnail = ?,
                       width = ?, height = ?, file_size = ?
                   WHERE id = ?""",
                (filename_processed, filename_thumbnail, width, height, file_size, asset_id),
            )
        await self.db.commit()

    async def get(self, asset_id: str) -> Optional[Asset]:
        async with self.db.execute(
            "SELECT * FROM assets WHERE id = ?", (asset_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_asset(row)

    async def get_by_hash(self, sha256: str) -> Optional[Asset]:
        async with self.db.execute(
            "SELECT * FROM assets WHERE sha256 = ? LIMIT 1", (sha256,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_asset(row)

    async def update_original_filename(self, asset_id: str, filename: str) -> None:
        await self.db.execute(
            "UPDATE assets SET filename_original = ? WHERE id = ?",
            (filename, asset_id),
        )
        await self.db.commit()

    async def delete(self, asset_id: str) -> None:
        await self.db.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
        await self.db.commit()

    async def list(self, limit: int = 50, offset: int = 0) -> list[Asset]:
        async with self.db.execute(
            "SELECT * FROM assets ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_asset(r) for r in rows]

    def _row_to_asset(self, row: aiosqlite.Row) -> Asset:
        return Asset(
            id=row["id"],
            filename_original=row["filename_original"],
            filename_processed=row["filename_processed"],
            filename_thumbnail=row["filename_thumbnail"],
            source_type=row["source_type"],
            source_id=row["source_id"],
            title=row["title"],
            width=row["width"],
            height=row["height"],
            file_size=row["file_size"],
            mime_type=row["mime_type"],
            sha256=row["sha256"],
            created_at=datetime.fromisoformat(row["created_at"]),
            metadata_json=row["metadata_json"],
        )


class HistoryRepository:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def create(self, asset_id: str, content_id: str, file_id: str) -> int:
        cursor = await self.db.execute(
            """INSERT INTO display_history (asset_id, content_id, file_id)
               VALUES (?, ?, ?)""",
            (asset_id, content_id, file_id),
        )
        await self.db.commit()
        return cursor.lastrowid

    async def update_status(
        self, history_id: int, status: str, error_message: Optional[str] = None
    ) -> None:
        await self.db.execute(
            "UPDATE display_history SET status = ?, error_message = ? WHERE id = ?",
            (status, error_message, history_id),
        )
        await self.db.commit()

    async def get_by_content_id(self, content_id: str) -> Optional[HistoryEntry]:
        async with self.db.execute(
            "SELECT * FROM display_history WHERE content_id = ?", (content_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_entry(row)

    async def get_latest(self) -> Optional[HistoryEntry]:
        async with self.db.execute(
            "SELECT * FROM display_history ORDER BY displayed_at DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_entry(row)

    async def list(self, limit: int = 50) -> list[HistoryEntry]:
        async with self.db.execute(
            "SELECT * FROM display_history ORDER BY displayed_at DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_entry(r) for r in rows]

    def _row_to_entry(self, row: aiosqlite.Row) -> HistoryEntry:
        return HistoryEntry(
            id=row["id"],
            asset_id=row["asset_id"],
            displayed_at=datetime.fromisoformat(row["displayed_at"]),
            content_id=row["content_id"],
            file_id=row["file_id"],
            status=row["status"],
            error_message=row["error_message"],
        )


class PresetRepository:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def create(
        self,
        name: str,
        source_type: str,
        source_config: dict,
        image_config: Optional[dict] = None,
    ) -> str:
        preset_id = str(uuid.uuid4())
        await self.db.execute(
            """INSERT INTO presets (id, name, source_type, source_config_json, image_config_json)
               VALUES (?, ?, ?, ?, ?)""",
            (preset_id, name, source_type, json.dumps(source_config),
             json.dumps(image_config) if image_config else None),
        )
        await self.db.commit()
        return preset_id

    async def get(self, preset_id: str) -> Optional[Preset]:
        async with self.db.execute(
            "SELECT * FROM presets WHERE id = ?", (preset_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_preset(row)

    async def get_by_name(self, name: str) -> Optional[Preset]:
        async with self.db.execute(
            "SELECT * FROM presets WHERE name = ?", (name,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_preset(row)

    async def list(self) -> list[Preset]:
        async with self.db.execute(
            "SELECT * FROM presets ORDER BY name"
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_preset(r) for r in rows]

    async def get_active(self) -> Optional[Preset]:
        async with self.db.execute(
            "SELECT * FROM presets WHERE is_active = 1 LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_preset(row)

    async def activate(self, preset_id: str) -> None:
        await self.db.execute("BEGIN")
        try:
            await self.db.execute("UPDATE presets SET is_active = 0")
            await self.db.execute(
                "UPDATE presets SET is_active = 1, updated_at = datetime('now') WHERE id = ?",
                (preset_id,),
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    async def update(
        self,
        preset_id: str,
        name: Optional[str] = None,
        source_type: Optional[str] = None,
        source_config: Optional[dict] = None,
        image_config: Optional[dict] = None,
    ) -> None:
        fields = []
        values = []
        if name is not None:
            fields.append("name = ?")
            values.append(name)
        if source_type is not None:
            fields.append("source_type = ?")
            values.append(source_type)
        if source_config is not None:
            fields.append("source_config_json = ?")
            values.append(json.dumps(source_config))
        if image_config is not None:
            fields.append("image_config_json = ?")
            values.append(json.dumps(image_config))
        if not fields:
            return
        fields.append("updated_at = datetime('now')")
        values.append(preset_id)
        await self.db.execute(
            f"UPDATE presets SET {', '.join(fields)} WHERE id = ?", values
        )
        await self.db.commit()

    async def delete(self, preset_id: str) -> None:
        await self.db.execute("DELETE FROM presets WHERE id = ?", (preset_id,))
        await self.db.commit()

    def _row_to_preset(self, row: aiosqlite.Row) -> Preset:
        return Preset(
            id=row["id"],
            name=row["name"],
            source_type=row["source_type"],
            source_config=json.loads(row["source_config_json"]),
            image_config=json.loads(row["image_config_json"]) if row["image_config_json"] else None,
            is_active=bool(row["is_active"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


class CollectionRepository:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def create(self, name: str, parent_id: Optional[str] = None) -> str:
        collection_id = str(uuid.uuid4())
        await self.db.execute(
            """INSERT INTO collections (id, name, parent_id)
               VALUES (?, ?, ?)""",
            (collection_id, name, parent_id),
        )
        await self.db.commit()
        return collection_id

    async def get(self, collection_id: str) -> Optional[Collection]:
        async with self.db.execute(
            "SELECT * FROM collections WHERE id = ?", (collection_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_collection(row)

    async def list(self, parent_id: Optional[str] = None) -> list[Collection]:
        if parent_id is not None:
            async with self.db.execute(
                "SELECT * FROM collections WHERE parent_id = ? ORDER BY name",
                (parent_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_collection(r) for r in rows]
        else:
            async with self.db.execute(
                "SELECT * FROM collections ORDER BY name"
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_collection(r) for r in rows]

    async def rename(self, collection_id: str, name: str) -> None:
        await self.db.execute(
            "UPDATE collections SET name = ? WHERE id = ?",
            (name, collection_id),
        )
        await self.db.commit()

    async def delete(self, collection_id: str) -> None:
        await self.db.execute(
            "DELETE FROM collections WHERE id = ?", (collection_id,)
        )
        await self.db.commit()

    async def has_children(self, collection_id: str) -> bool:
        async with self.db.execute(
            "SELECT COUNT(*) FROM collections WHERE parent_id = ?",
            (collection_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] > 0

    async def has_favourites(self, collection_id: str) -> bool:
        async with self.db.execute(
            "SELECT COUNT(*) FROM favourites WHERE collection_id = ?",
            (collection_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] > 0

    async def get_tree(self) -> list[dict]:
        collections = await self.list()
        by_parent: dict[Optional[str], list[Collection]] = {}
        for c in collections:
            by_parent.setdefault(c.parent_id, []).append(c)

        def build(parent_id: Optional[str]) -> list[dict]:
            children = by_parent.get(parent_id, [])
            return [
                {
                    "id": c.id,
                    "name": c.name,
                    "parent_id": c.parent_id,
                    "created_at": c.created_at.isoformat(),
                    "children": build(c.id),
                }
                for c in children
            ]

        return build(None)

    def _row_to_collection(self, row: aiosqlite.Row) -> Collection:
        return Collection(
            id=row["id"],
            name=row["name"],
            parent_id=row["parent_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )


class FavouriteRepository:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def add(
        self,
        asset_id: str,
        collection_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> str:
        favourite_id = str(uuid.uuid4())
        await self.db.execute(
            """INSERT INTO favourites (id, asset_id, collection_id, name)
               VALUES (?, ?, ?, ?)""",
            (favourite_id, asset_id, collection_id, name),
        )
        await self.db.commit()
        return favourite_id

    async def remove(self, favourite_id: str) -> None:
        await self.db.execute(
            "DELETE FROM favourites WHERE id = ?", (favourite_id,)
        )
        await self.db.commit()

    async def list(self, collection_id: Optional[str] = None) -> list[Favourite]:
        if collection_id is not None:
            async with self.db.execute(
                "SELECT * FROM favourites WHERE collection_id = ? ORDER BY added_at DESC",
                (collection_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_favourite(r) for r in rows]
        else:
            async with self.db.execute(
                "SELECT * FROM favourites ORDER BY added_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_favourite(r) for r in rows]

    async def get(self, favourite_id: str) -> Optional[Favourite]:
        async with self.db.execute(
            "SELECT * FROM favourites WHERE id = ?", (favourite_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_favourite(row)

    async def get_by_asset(self, asset_id: str) -> list[Favourite]:
        async with self.db.execute(
            "SELECT * FROM favourites WHERE asset_id = ? ORDER BY added_at DESC",
            (asset_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_favourite(r) for r in rows]

    def _row_to_favourite(self, row: aiosqlite.Row) -> Favourite:
        return Favourite(
            id=row["id"],
            asset_id=row["asset_id"],
            collection_id=row["collection_id"],
            name=row["name"],
            added_at=datetime.fromisoformat(row["added_at"]),
        )


class ScheduleRepository:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def create(
        self, name: str, preset_id: str, cron_expression: str
    ) -> str:
        schedule_id = str(uuid.uuid4())
        await self.db.execute(
            """INSERT INTO schedules (id, name, preset_id, cron_expression)
               VALUES (?, ?, ?, ?)""",
            (schedule_id, name, preset_id, cron_expression),
        )
        await self.db.commit()
        return schedule_id

    async def get(self, schedule_id: str) -> Optional[Schedule]:
        async with self.db.execute(
            "SELECT * FROM schedules WHERE id = ?", (schedule_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_schedule(row)

    async def list(self) -> list[Schedule]:
        async with self.db.execute(
            "SELECT * FROM schedules ORDER BY name"
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_schedule(r) for r in rows]

    async def update(
        self,
        schedule_id: str,
        name: Optional[str] = None,
        preset_id: Optional[str] = None,
        cron_expression: Optional[str] = None,
        is_enabled: Optional[bool] = None,
    ) -> None:
        fields = []
        values = []
        if name is not None:
            fields.append("name = ?")
            values.append(name)
        if preset_id is not None:
            fields.append("preset_id = ?")
            values.append(preset_id)
        if cron_expression is not None:
            fields.append("cron_expression = ?")
            values.append(cron_expression)
        if is_enabled is not None:
            fields.append("is_enabled = ?")
            values.append(1 if is_enabled else 0)
        if not fields:
            return
        values.append(schedule_id)
        await self.db.execute(
            f"UPDATE schedules SET {', '.join(fields)} WHERE id = ?", values
        )
        await self.db.commit()

    async def delete(self, schedule_id: str) -> None:
        await self.db.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        await self.db.commit()

    async def update_last_run(
        self, schedule_id: str, last_run_at: Optional[str], next_run_at: str
    ) -> None:
        await self.db.execute(
            "UPDATE schedules SET last_run_at = ?, next_run_at = ? WHERE id = ?",
            (last_run_at, next_run_at, schedule_id),
        )
        await self.db.commit()

    def _row_to_schedule(self, row: aiosqlite.Row) -> Schedule:
        return Schedule(
            id=row["id"],
            name=row["name"],
            preset_id=row["preset_id"],
            cron_expression=row["cron_expression"],
            is_enabled=bool(row["is_enabled"]),
            last_run_at=datetime.fromisoformat(row["last_run_at"]) if row["last_run_at"] else None,
            next_run_at=datetime.fromisoformat(row["next_run_at"]) if row["next_run_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
        )
