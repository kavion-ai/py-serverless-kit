"""The smallest useful py-serverless-kit function.

The same function runs unchanged on AWS Lambda, Azure Functions, Google Cloud
Functions and the other supported clouds - only ``pskit.yml`` decides where.
"""

from py_serverless_kit import Context, Event


def hello(event: Event, ctx: Context):
    # Query string parameters are a plain dict on every provider.
    name = event.http.query.get("name", "world")
    ctx.logger.info("greeting", extra={"name": name})
    # Returning a dict produces a 200 JSON response.
    return {"message": f"Hello, {name}!", "provider": event.provider, "stage": ctx.stage}
