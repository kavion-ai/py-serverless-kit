import os

from py_serverless_kit import Context, Event


def health(event: Event, ctx: Context):
    """GET /health - used by the pipeline's post-deploy smoke test."""
    return {
        "status": "ok",
        "stage": ctx.stage,
        "version": os.environ.get("APP_VERSION", "unknown"),  # git SHA injected by CI
    }
