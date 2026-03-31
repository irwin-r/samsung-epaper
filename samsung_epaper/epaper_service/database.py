"""SQLite database with aiosqlite — schema, migrations, repositories."""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from .models import Asset, HistoryEntry, Preset

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

CREATE INDEX IF NOT EXISTS idx_assets_source ON assets(source_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_displayed ON display_history(displayed_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_content_id ON display_history(content_id);
CREATE INDEX IF NOT EXISTS idx_presets_active ON presets(is_active);
"""


async def init_db(db_path: str) -> aiosqlite.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
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
    ) -> str:
        asset_id = str(uuid.uuid4())
        await self.db.execute(
            """INSERT INTO assets (id, filename_original, source_type, source_id, title, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (asset_id, filename_original, source_type, source_id, title, metadata_json),
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
    ) -> None:
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
