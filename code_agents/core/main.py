import sys
sys.dont_write_bytecode = True

from .env_loader import load_all_env
load_all_env()

import logging
import os
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
import uvicorn

logger = logging.getLogger("code_agents.core.main")

from .config import settings
from .logging_config import setup_logging


def main():
    setup_logging()

    log_level = os.getenv("LOG_LEVEL", "info").lower()
    logger.info("Starting code-agents server on %s:%d (log_level=%s)", settings.host, settings.port, log_level)
    uvicorn.run(
        "code_agents.core.app:app",
        host=settings.host,
        port=settings.port,
        log_level=log_level,
        log_config=None,
    )


if __name__ == "__main__":
    main()
