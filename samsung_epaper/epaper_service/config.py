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

    # Art generation
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    image_provider: str = Field(default="openai", alias="IMAGE_PROVIDER")
    image_provider_fallbacks: str = Field(default="", alias="IMAGE_PROVIDER_FALLBACKS")
    epaper_auth_token: str = Field(default="", alias="EPAPER_AUTH_TOKEN")
    font_dir: str = Field(default="", alias="FONT_DIR")
    art_assets_dir: str = Field(default="", alias="ART_ASSETS_DIR")

    model_config = {"populate_by_name": True}
