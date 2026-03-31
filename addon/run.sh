#!/usr/bin/with-contenv bashio

export DISPLAY_IP="$(bashio::config 'display_ip')"
export DISPLAY_PORT="$(bashio::config 'display_port')"
export DISPLAY_ID="$(bashio::config 'display_id')"
export DISPLAY_PIN="$(bashio::config 'display_pin')"
export PUBLIC_BASE_URL="$(bashio::config 'public_base_url')"
export VIEWPORT_WIDTH="$(bashio::config 'viewport_width')"
export VIEWPORT_HEIGHT="$(bashio::config 'viewport_height')"
export NEWSPAPER_URL="$(bashio::config 'newspaper_url')"
export NEWSPAPER_PATTERN="$(bashio::config 'newspaper_pattern')"
export DB_PATH="/data/epaper.db"
export ASSETS_DIR="/data/assets"

exec python -m epaper_service.main
