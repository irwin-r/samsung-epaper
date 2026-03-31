"""Pydantic models for API request/response and domain objects."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Asset(BaseModel):
    id: str
    filename_original: str
    filename_processed: Optional[str] = None
    filename_thumbnail: Optional[str] = None
    source_type: str
    source_id: Optional[str] = None
    title: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    file_size: Optional[int] = None
    mime_type: str = "image/png"
    sha256: Optional[str] = None
    created_at: datetime
    metadata_json: Optional[str] = None


class DisplayStatus(BaseModel):
    power: Optional[str] = None
    battery_percent: Optional[int] = None
    charging_state: Optional[str] = None
    model_name: Optional[str] = None
    serial_number: Optional[str] = None
    reachable: bool = False


class ServiceStatus(BaseModel):
    service: str = "running"
    version: str = "1.0.0"
    display: DisplayStatus = Field(default_factory=DisplayStatus)
    last_update: Optional[datetime] = None
    last_update_status: Optional[str] = None
    is_updating: bool = False
    active_preset_id: Optional[str] = None
    active_preset_name: Optional[str] = None
    current_asset_id: Optional[str] = None


class Preset(BaseModel):
    id: str
    name: str
    source_type: str
    source_config: dict
    image_config: Optional[dict] = None
    is_active: bool = False
    created_at: datetime
    updated_at: datetime


class PresetCreate(BaseModel):
    name: str
    source_type: str
    source_config: dict
    image_config: Optional[dict] = None


class PresetUpdate(BaseModel):
    name: Optional[str] = None
    source_type: Optional[str] = None
    source_config: Optional[dict] = None
    image_config: Optional[dict] = None


class UpdateRequest(BaseModel):
    preset_id: Optional[str] = None
    force: bool = False


class UpdateResponse(BaseModel):
    status: str
    message: str
    asset_id: Optional[str] = None
    started_at: datetime


class DisplayAssetRequest(BaseModel):
    asset_id: str


class HistoryEntry(BaseModel):
    id: int
    asset_id: str
    displayed_at: datetime
    content_id: str
    file_id: str
    status: str
    error_message: Optional[str] = None


class ImageInfo(BaseModel):
    width: int
    height: int
    file_size: int


class Collection(BaseModel):
    id: str
    name: str
    parent_id: Optional[str] = None
    created_at: datetime


class CollectionCreate(BaseModel):
    name: str
    parent_id: Optional[str] = None


class Favourite(BaseModel):
    id: str
    asset_id: str
    collection_id: Optional[str] = None
    name: Optional[str] = None
    added_at: datetime


class FavouriteCreate(BaseModel):
    asset_id: str
    collection_id: Optional[str] = None
    name: Optional[str] = None


class Schedule(BaseModel):
    id: str
    name: str
    preset_id: str
    cron_expression: str
    is_enabled: bool = True
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    created_at: datetime


class ScheduleCreate(BaseModel):
    name: str
    preset_id: str
    cron_expression: str


class ScheduleUpdate(BaseModel):
    name: Optional[str] = None
    preset_id: Optional[str] = None
    cron_expression: Optional[str] = None
    is_enabled: Optional[bool] = None
