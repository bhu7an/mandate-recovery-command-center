"""Shared configuration for the mandate-health project.

Secrets are intentionally loaded from environment variables or an ignored
``db_config.local.json`` file.  Nothing sensitive should be committed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
LOCAL_CONFIG_FILE = PROJECT_DIR / "db_config.local.json"


def load_db_config() -> dict[str, object]:
    """Return MySQL settings without hard-coding credentials."""

    config: dict[str, object] = {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "mandate_health"),
    }

    if LOCAL_CONFIG_FILE.exists():
        with LOCAL_CONFIG_FILE.open("r", encoding="utf-8") as file:
            local_config = json.load(file)
        allowed_keys = {"host", "port", "user", "password", "database"}
        config.update(
            {
                key: value
                for key, value in local_config.items()
                if key in allowed_keys
            }
        )

    return config


DB_CONFIG = load_db_config()
