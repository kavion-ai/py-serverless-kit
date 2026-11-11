"""Service-level operations: ListBuckets."""

from __future__ import annotations

from ..config import REGION
from ..errors import denied
from ..listing import token_decode, token_encode
from ..request import Request, Response, xml_response
from ..store import get_store
from ..util import iso, owner_xml, x


def list_buckets(req: Request) -> Response:
    if req.who is None:
        raise denied()
    prefix = req.q.get("prefix", "")
    region = req.q.get("bucket-region", "")
    limit = int(req.q.get("max-buckets") or 10000)
    after = token_decode(req.q["continuation-token"]) if req.q.get("continuation-token") else ""
    with get_store().lock:
        names = [
            n
            for n in sorted(get_store().buckets)
            if n.startswith(prefix)
            and n > after
            and (not region or get_store().buckets[n].meta.get("region") == region)
        ]
        page, more = names[:limit], len(names) > limit
        items = "".join(
            f"<Bucket>{x('Name', n)}{x('CreationDate', iso(get_store().buckets[n].meta['created']))}"
            f"{x('BucketRegion', get_store().buckets[n].meta.get('region') or REGION)}</Bucket>"
            for n in page
        )
    inner = owner_xml() + f"<Buckets>{items}</Buckets>"
    if more:
        inner += x("ContinuationToken", token_encode(page[-1]))
    if prefix:
        inner += x("Prefix", prefix)
    return xml_response("ListAllMyBucketsResult", inner)
