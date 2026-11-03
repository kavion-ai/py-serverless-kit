from py_serverless_kit import Context, Event

from .settings import get_settings


def config(event: Event, ctx: Context):
    """GET /config - shows which settings the current stage resolved to."""
    s = get_settings()
    return {
        "stage": s.stage,
        "table": s.table_name,
        "log_level": s.log_level,
        "new_checkout": s.feature_new_checkout,
        "api_base_url": s.api_base_url,
        "payment_api_key_configured": s.payment_api_key_set,
        "memory_mb": ctx.memory_mb,
    }
