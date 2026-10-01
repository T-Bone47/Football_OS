import asyncio

from app.worker.runner import main

raise SystemExit(asyncio.run(main()))
