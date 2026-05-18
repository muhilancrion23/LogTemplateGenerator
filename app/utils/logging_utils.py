"""
Centralised logging configuration for CLONOS AI.
Call setup_logging() once at app startup.
"""
import logging
import sys


def setup_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    fmt = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt=datefmt,
        stream=sys.stdout,
    )

    # Suppress noisy third-party loggers
    for noisy in (
        "transformers",
        "torch",
        "PIL",
        "urllib3",
        "pymongo",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)