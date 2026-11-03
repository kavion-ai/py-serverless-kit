"""Per-provider translation between native payloads and the portable model.

Each module exposes at least ``to_event(native, native_context)`` and a
provider-specific entrypoint used by the generated shim in the bundle.
"""

ADAPTERS = (
    "aws",
    "azure",
    "gcp",
    "alibaba",
    "oracle",
    "ibm",
    "digitalocean",
    "tencent",
    "huawei",
    "cloudflare",
)
