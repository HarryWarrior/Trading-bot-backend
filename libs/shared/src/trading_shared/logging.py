"""Logging configuration shared by all services."""

import logging

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: str) -> None:
    """Configure root logging once per process."""
    logging.basicConfig(level=level.upper(), format=LOG_FORMAT, force=True)
