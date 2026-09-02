from __future__ import annotations

import logging

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"
_CONFIGURED = False


def configure_logging(level: str) -> None:
    global _CONFIGURED

    resolved_level = level.upper()
    numeric_level = getattr(logging, resolved_level, logging.INFO)

    root = logging.getLogger()
    root.setLevel(numeric_level)

    if _CONFIGURED:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(fmt=_FORMAT, datefmt=_DATEFMT))
    root.addHandler(handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
