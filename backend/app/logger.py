import logging
import os
import sys
from datetime import date
from pathlib import Path


def _build_logger(name: str, filename: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(fmt)
    logger.addHandler(stdout_handler)

    log_dir = os.getenv("LOG_DIR")
    if log_dir:
        path = Path(log_dir) / f"{filename}_{date.today().isoformat()}.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    return logger


backend_logger = _build_logger("backend", "backend")
api_logger = _build_logger("api", "api")
