import logging
import sys

from app.core.config import settings


def configure_logging() -> None:
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # Silence noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
