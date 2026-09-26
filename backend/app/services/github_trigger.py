"""
Trigger the GitHub Actions book-processing worker immediately when a book
is queued, instead of waiting for the next scheduled run (which can be
several minutes away).
"""

import logging
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

WORKFLOW_FILE = "process-books.yml"


async def trigger_worker() -> bool:
    token = (settings.github_token or "").strip()
    repo = (settings.github_repo or "").strip()
    if not token or not repo:
        logger.info("GitHub trigger not configured; relying on the schedule")
        return False
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW_FILE}/dispatches",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                json={"ref": "master"},
            )
            if r.status_code in (204, 200):
                logger.info("Triggered processing workflow")
                return True
            logger.warning(f"Workflow trigger failed: {r.status_code} {r.text[:150]}")
            return False
    except Exception as e:
        logger.warning(f"Workflow trigger error: {e}")
        return False
