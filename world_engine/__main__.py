from __future__ import annotations

import uvicorn

from . import config
from .api import create_app


def main() -> None:
    uvicorn.run(create_app(), host=config.HOST, port=config.PORT, log_level="info")


if __name__ == "__main__":
    main()
