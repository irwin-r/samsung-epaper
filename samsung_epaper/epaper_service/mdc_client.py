"""Thin async wrapper around python-samsung-mdc for ePaper displays."""

import logging

from samsung_mdc import MDC
from samsung_mdc.exceptions import MDCTimeoutError, MDCReadTimeoutError, MDCError

from .config import AppConfig
from .models import DisplayStatus

logger = logging.getLogger(__name__)


class MDCClient:
    def __init__(self, config: AppConfig):
        self._target = f"{config.display_ip}:{config.display_port}"
        self._display_id = config.display_id
        self._pin = config.display_pin or None

    def _connection_kwargs(self) -> dict:
        kwargs = {}
        if self._pin:
            kwargs["pin"] = self._pin
        return kwargs

    async def ping(self) -> bool:
        try:
            async with MDC(self._target, **self._connection_kwargs()) as mdc:
                await mdc.serial_number(self._display_id)
            return True
        except Exception:
            return False

    async def get_status(self) -> DisplayStatus:
        status = DisplayStatus()
        try:
            async with MDC(self._target, **self._connection_kwargs()) as mdc:
                status.reachable = True
                try:
                    result = await mdc.model_name(self._display_id)
                    status.model_name = result[0] if result else None
                except Exception as e:
                    logger.debug(f"Could not get model name: {e}")

                try:
                    result = await mdc.serial_number(self._display_id)
                    status.serial_number = result[0] if result else None
                except Exception as e:
                    logger.debug(f"Could not get serial number: {e}")

                try:
                    result = await mdc.power(self._display_id)
                    status.power = "on" if result[0] == 1 else "off"
                except Exception as e:
                    logger.debug(f"Could not get power state: {e}")

                try:
                    result = await mdc.battery(self._display_id)
                    if len(result) >= 2:
                        status.battery_percent = result[0]
                        status.charging_state = str(result[1])
                except Exception as e:
                    logger.debug(f"Could not get battery: {e}")

        except (MDCTimeoutError, MDCReadTimeoutError):
            logger.warning("Display connection timed out")
            status.reachable = False
        except MDCError as e:
            logger.warning(f"MDC error: {e}")
            status.reachable = False
        except Exception as e:
            logger.warning(f"Unexpected error connecting to display: {e}")
            status.reachable = False

        return status

    async def send_content(self, content_url: str) -> bool:
        logger.info(f"Sending content download: {content_url}")
        try:
            async with MDC(self._target, **self._connection_kwargs()) as mdc:
                result = await mdc.set_content_download(
                    self._display_id, data=[content_url]
                )
                logger.info(f"Content download command sent: {result}")
                return True
        except (MDCTimeoutError, MDCReadTimeoutError):
            # Display often doesn't ACK but still processes the command
            logger.info("MDC timeout on set_content_download (display may still process)")
            return True
        except MDCError as e:
            logger.error(f"MDC error sending content: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending content: {e}")
            return False

    async def set_power(self, on: bool) -> bool:
        try:
            async with MDC(self._target, **self._connection_kwargs()) as mdc:
                await mdc.power(self._display_id, 1 if on else 0)
                return True
        except Exception as e:
            logger.error(f"Error setting power: {e}")
            return False
