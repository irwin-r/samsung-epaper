"""Application configuration from environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings


class AppConfig(BaseSettings):
    # Display
    display_ip: str = Field(alias="DISPLAY_IP")
    display_port: int = Field(default=1515, alias="DISPLAY_PORT")
    display_id: int = Field(default=0, alias="DISPLAY_ID")
    display_pin: str = Field(default="", alias="DISPLAY_PIN")

    # Server
    server_port: int = Field(default=8000, alias="SERVER_PORT")
    public_base_url: str = Field(default="", alias="PUBLIC_BASE_URL")

    # Display viewport
    viewport_width: int = Field(default=1440, alias="VIEWPORT_WIDTH")
    viewport_height: int = Field(default=2560, alias="VIEWPORT_HEIGHT")

    # Storage
    db_path: str = Field(default="/data/epaper.db", alias="DB_PATH")
    assets_dir: str = Field(default="/data/assets", alias="ASSETS_DIR")

    # Default newspaper source
    newspaper_url: str = Field(
        default="https://www.frontpages.com/the-sydney-morning-herald/",
        alias="NEWSPAPER_URL",
    )
    newspaper_pattern: str = Field(
        default="the-sydney-morning-herald",
        alias="NEWSPAPER_PATTERN",
    )

    model_config = {"populate_by_name": True}
