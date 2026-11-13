"""The API operations, in the shape of the SES v2 API (``OPERATIONS``: name -> function(params, ctx)).

The v2 REST routes (``rest.py``) call them directly, the v1 Query API (``query.py``) translates to and from them, and
the console calls them (and the console-only operations at the end) through ``POST /ui/api/<Operation>``. ``ctx``
holds ``region``, ``caller`` (the access key or ``console:<user>``) and ``source_ip``.
"""

from __future__ import annotations

import base64
import binascii
import copy
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import identities, mime, sender, templates
from .config import (
    ACCOUNT,
    CREDENTIALS,
    DELIVERY,
    DIRECT_PORT,
    DKIM_CHECK,
    EVENTS_URL,
    HELO_NAME,
    MAX_24H,
    MAX_MESSAGE,
    MAX_RATE,
    NAME_RE,
    REGION,
    RELAY_HOST,
    RELAY_PORT,
    RELAY_TLS,
    RELAY_USER,
    RETENTION_DAYS,
    RETRY_HOURS,
    SANDBOX,
    SMTP_HOST,
    SMTP_ON,
    SMTP_PORT,
    SMTP_REQUIRE_TLS,
    TLS_CERT,
    VERIFY,
    VERSION,
)
from .errors import ApiError, bad_request, exists, not_found
from .store import db
from .util import addresses, now

Ctx = Dict[str, Any]
Op = Callable[[Dict[str, Any], Ctx], Dict[str, Any]]
OPERATIONS: Dict[str, Op] = {}
# Operations that change nothing (the console may call them more freely).
READS = set()


def op(name: str, read: bool = False) -> Callable[[Op], Op]:
    def wrap(fn: Op) -> Op:
        OPERATIONS[name] = fn
        if read:
            READS.add(name)
        return fn
    return wrap


def run(name: str, params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    fn = OPERATIONS.get(name)
    if fn is None:
        raise ApiError("BadRequestException", f"Unknown operation {name}.", 400, "InvalidAction")
    return fn(params, ctx)


# ----------------------------------------------------------------------------- helpers


def _str(params: Dict[str, Any], name: str, required: bool = True) -> str:
    value = params.get(name)
    if value is None or value == "":
        if required:
            raise bad_request(f"{name} is required.")
        return ""
    return str(value)


def _page(items: List[Any], params: Dict[str, Any], default: int = 100, limit: int = 1000) -> Tuple[List[Any], Dict]:
    try:
        size = int(params.get("PageSize") or params.get("MaxItems") or default)
        start = int(base64.b64decode(str(params.get("NextToken") or "MA==")).decode() or 0)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise ApiError("BadRequestException", "The NextToken is not valid.", 400, "InvalidParameterValue") from None
    size = max(1, min(size, limit))
    chunk = items[start:start + size]
    more = {"NextToken": base64.b64encode(str(start + size).encode()).decode()} if start + size < len(items) else {}
    return chunk, more


def _tags_in(tags: Any) -> List[Dict[str, str]]:
    out = []
    for tag in tags or []:
        key, value = str(tag.get("Key") or ""), str(tag.get("Value") or "")
        if not key or len(key) > 128 or len(value) > 256:
            raise bad_request("Tag keys are 1 to 128 characters, values up to 256.")
        out.append({"Key": key, "Value": value})
    return out


def _identity(name: Any) -> Dict[str, Any]:
    key = identities.normalize(name)
    rec = db().identities.get(key)
    if rec is None:
        raise not_found(f"Email identity <{key}> does not exist.", "NotFound")
    return rec


def _template(params: Dict[str, Any]) -> Dict[str, Any]:
    name = str(params.get("TemplateName") or "")
    if not name and params.get("TemplateArn"):
        name = str(params["TemplateArn"]).rsplit("/", 1)[-1]
    rec = db().templates.get(name)
    if rec is None:
        raise not_found(f"Template {name} does not exist.", "TemplateDoesNotExist")
    return rec


def _config_set(name: Any) -> Dict[str, Any]:
    rec = db().configuration_sets.get(str(name or ""))
    if rec is None:
        raise not_found(f"Configuration set <{name}> does not exist.", "ConfigurationSetDoesNotExist")
    return rec


def _resource(arn: Any) -> Dict[str, Any]:
    """The identity, template or configuration set an ARN names."""
    text = str(arn or "")
    parts = text.split(":", 5)
    if len(parts) != 6 or parts[2] != "ses" or "/" not in parts[5]:
        raise bad_request(f"Invalid resource ARN {text!r}.")
    kind, _sl, name = parts[5].partition("/")
    table = {"identity": db().identities, "template": db().templates,
             "configuration-set": db().configuration_sets}.get(kind)
    if table is None or name not in table:
        raise not_found(f"Resource {text} does not exist.")
    return table[name]


def _save() -> None:
    db().save()


# ----------------------------------------------------------------------------- account


def _account(ctx: Ctx) -> Dict[str, Any]:
    store = db()
    return {
        "DedicatedIpAutoWarmupEnabled": False, "EnforcementStatus": "HEALTHY",
        "ProductionAccessEnabled": not SANDBOX, "SendingEnabled": bool(store.account.get("SendingEnabled", True)),
        "SendQuota": {"Max24HourSend": float(MAX_24H), "MaxSendRate": float(MAX_RATE),
                      "SentLast24Hours": float(sender.sent_last_24h())},
        "SuppressionAttributes": {"SuppressedReasons": list(store.account.get("SuppressedReasons") or [])},
        "Details": {"MailType": "TRANSACTIONAL", "WebsiteURL": "", "ContactLanguage": "EN"},
    }


@op("GetAccount", read=True)
def get_account(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    return _account(ctx)


@op("PutAccountSendingAttributes")
def put_account_sending(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    with db().lock:
        db().account["SendingEnabled"] = bool(params.get("SendingEnabled", False))
        _save()
    return {}


def _reasons(value: Any) -> List[str]:
    reasons = [str(r) for r in value or []]
    if any(r not in ("BOUNCE", "COMPLAINT") for r in reasons):
        raise bad_request("SuppressedReasons may only contain BOUNCE and COMPLAINT.")
    return sorted(set(reasons))


@op("PutAccountSuppressionAttributes")
def put_account_suppression(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    with db().lock:
        db().account["SuppressedReasons"] = _reasons(params.get("SuppressedReasons"))
        _save()
    return {}


# ----------------------------------------------------------------------------- identities


def _dkim_out(rec: Dict[str, Any]) -> Dict[str, Any]:
    dk = rec.get("Dkim")
    if dk is None and rec["IdentityType"] == "EMAIL_ADDRESS":
        for d in identities.domains_up(rec["IdentityName"].rpartition("@")[2]):
            dk = (db().identities.get(d) or {}).get("Dkim")
            if dk:
                break
    if not dk:
        return {"SigningEnabled": False, "Status": "NOT_STARTED", "Tokens": []}
    return {"SigningEnabled": bool(dk.get("SigningEnabled")), "Status": dk.get("Status", "PENDING"),
            "Tokens": [dk["Selector"]], "SigningAttributesOrigin": dk.get("Origin", "AWS_SES"),
            "NextSigningKeyLength": dk.get("NextSigningKeyLength", "RSA_2048_BIT"),
            "CurrentSigningKeyLength": dk.get("CurrentSigningKeyLength", "RSA_2048_BIT"),
            "LastKeyGenerationTimestamp": dk.get("LastKeyGenerationTimestamp")}


def _mail_from_out(rec: Dict[str, Any]) -> Dict[str, Any]:
    mf = rec.get("MailFrom") or {}
    return {"MailFromDomain": mf.get("MailFromDomain", ""), "MailFromDomainStatus": mf.get(
        "MailFromDomainStatus", "PENDING" if mf.get("MailFromDomain") else "FAILED"),
            "BehaviorOnMxFailure": mf.get("BehaviorOnMxFailure", "USE_DEFAULT_VALUE")}


def identity_out(rec: Dict[str, Any]) -> Dict[str, Any]:
    status = identities.status_of(rec)
    out = {
        "IdentityType": rec["IdentityType"], "FeedbackForwardingStatus": bool(rec.get("FeedbackForwardingStatus", True)),
        "VerifiedForSendingStatus": status == "SUCCESS", "DkimAttributes": _dkim_out(rec),
        "MailFromAttributes": _mail_from_out(rec), "Policies": dict(rec.get("Policies") or {}),
        "Tags": list(rec.get("Tags") or []), "VerificationStatus": status,
        "VerificationInfo": dict(rec.get("VerificationInfo") or {}),
    }
    if rec.get("ConfigurationSetName"):
        out["ConfigurationSetName"] = rec["ConfigurationSetName"]
    return out


def create_identity(name: str, params: Dict[str, Any], *, idempotent: bool = False) -> Dict[str, Any]:
    store = db()
    key = identities.normalize(name)
    identities.kind_of(key)
    with store.lock:
        if key in store.identities:
            if idempotent:
                return store.identities[key]
            raise exists(f"Email identity <{key}> already exists.")
    if params.get("ConfigurationSetName"):
        _config_set(params["ConfigurationSetName"])
    rec = identities.new(key, params.get("DkimSigningAttributes"))  # may generate a key: outside the lock
    rec["Tags"] = _tags_in(params.get("Tags"))
    if params.get("ConfigurationSetName"):
        rec["ConfigurationSetName"] = str(params["ConfigurationSetName"])
    with store.lock:
        if key in store.identities:
            return store.identities[key]
        store.identities[key] = rec
        _save()
    if rec["IdentityType"] == "DOMAIN":
        identities.check_later(key)
    return rec


@op("CreateEmailIdentity")
def create_email_identity(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = create_identity(_str(params, "EmailIdentity"), params)
    out = identity_out(rec)
    return {"IdentityType": out["IdentityType"], "VerifiedForSendingStatus": out["VerifiedForSendingStatus"],
            "DkimAttributes": out["DkimAttributes"]}


@op("GetEmailIdentity", read=True)
def get_email_identity(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    return identity_out(_identity(_str(params, "EmailIdentity")))


@op("ListEmailIdentities", read=True)
def list_email_identities(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    with db().lock:
        recs = [db().identities[n] for n in sorted(db().identities)]
        items = [{"IdentityType": r["IdentityType"], "IdentityName": r["IdentityName"],
                  "SendingEnabled": identities.status_of(r) == "SUCCESS",
                  "VerificationStatus": identities.status_of(r)} for r in recs]
    chunk, more = _page(items, params)
    return {"EmailIdentities": chunk, **more}


@op("DeleteEmailIdentity")
def delete_email_identity(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _identity(_str(params, "EmailIdentity"))
    with db().lock:
        db().identities.pop(rec["IdentityName"], None)
        _save()
    return {}


@op("PutEmailIdentityDkimAttributes")
def put_identity_dkim(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _identity(_str(params, "EmailIdentity"))
    enabled = bool(params.get("SigningEnabled", False))
    with db().lock:
        if rec.get("Dkim"):
            rec["Dkim"]["SigningEnabled"] = enabled
        elif enabled and rec["IdentityType"] == "EMAIL_ADDRESS":
            raise bad_request("Enable DKIM on the address's domain identity: the domain's key signs its mail.")
        _save()
    return {}


@op("PutEmailIdentityDkimSigningAttributes")
def put_identity_dkim_signing(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _identity(_str(params, "EmailIdentity"))
    if rec["IdentityType"] != "DOMAIN":
        raise bad_request("DKIM signing attributes apply to domain identities.")
    attrs = dict(params.get("SigningAttributes") or {})
    attrs["DomainSigningAttributesOrigin"] = params.get("SigningAttributesOrigin") or attrs.get(
        "DomainSigningAttributesOrigin") or "AWS_SES"
    fresh = {"IdentityName": rec["IdentityName"]}
    identities.set_dkim(fresh, attrs)
    with db().lock:
        rec["Dkim"] = fresh["Dkim"]
        _save()
    identities.check_later(rec["IdentityName"])
    return {"DkimStatus": rec["Dkim"]["Status"], "DkimTokens": [rec["Dkim"]["Selector"]]}


@op("PutEmailIdentityMailFromAttributes")
def put_identity_mail_from(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _identity(_str(params, "EmailIdentity"))
    domain = str(params.get("MailFromDomain") or "").lower().rstrip(".")
    behavior = str(params.get("BehaviorOnMxFailure") or "USE_DEFAULT_VALUE")
    if behavior not in ("USE_DEFAULT_VALUE", "REJECT_MESSAGE"):
        raise bad_request("BehaviorOnMxFailure must be USE_DEFAULT_VALUE or REJECT_MESSAGE.")
    with db().lock:
        if not domain:
            rec.pop("MailFrom", None)
        else:
            parent = rec["IdentityName"].rpartition("@")[2]
            if not domain.endswith("." + parent):
                raise bad_request(f"The MAIL FROM domain must be a subdomain of {parent}.")
            rec["MailFrom"] = {"MailFromDomain": domain, "BehaviorOnMxFailure": behavior,
                               "MailFromDomainStatus": "SUCCESS" if VERIFY in ("auto", "off") else "PENDING"}
        _save()
    return {}


@op("PutEmailIdentityFeedbackAttributes")
def put_identity_feedback(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _identity(_str(params, "EmailIdentity"))
    with db().lock:
        rec["FeedbackForwardingStatus"] = bool(params.get("EmailForwardingEnabled", False))
        _save()
    return {}


@op("PutEmailIdentityConfigurationSetAttributes")
def put_identity_config_set(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _identity(_str(params, "EmailIdentity"))
    name = str(params.get("ConfigurationSetName") or "")
    if name:
        _config_set(name)
    with db().lock:
        if name:
            rec["ConfigurationSetName"] = name
        else:
            rec.pop("ConfigurationSetName", None)
        _save()
    return {}


# ----------------------------------------------------------------------------- templates


def _template_content(params: Dict[str, Any]) -> Dict[str, str]:
    content = params.get("TemplateContent") or {}
    out = {"Subject": str(content.get("Subject") or ""), "Text": str(content.get("Text") or ""),
           "Html": str(content.get("Html") or "")}
    if not out["Subject"] and not out["Text"] and not out["Html"]:
        raise bad_request("A template needs a subject, a text part or an HTML part.")
    templates.check(out["Subject"], out["Text"], out["Html"])
    return out


@op("CreateEmailTemplate")
def create_email_template(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    name = _str(params, "TemplateName")
    if not NAME_RE.match(name):
        raise bad_request("TemplateName may contain only letters, digits, '_' and '-' (up to 64).")
    content = _template_content(params)
    with db().lock:
        if name in db().templates:
            raise exists(f"Template {name} already exists.")
        db().templates[name] = {"TemplateName": name, **content, "CreatedTimestamp": now(),
                                "Tags": _tags_in(params.get("Tags"))}
        _save()
    return {}


def template_out(rec: Dict[str, Any]) -> Dict[str, Any]:
    return {"TemplateName": rec["TemplateName"], "TemplateContent": {
        "Subject": rec.get("Subject", ""), "Text": rec.get("Text", ""), "Html": rec.get("Html", "")},
        "Tags": list(rec.get("Tags") or [])}


@op("GetEmailTemplate", read=True)
def get_email_template(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    return template_out(_template(params))


@op("UpdateEmailTemplate")
def update_email_template(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _template(params)
    content = _template_content(params)
    with db().lock:
        rec.update(content)
        rec["UpdatedTimestamp"] = now()
        _save()
    return {}


@op("DeleteEmailTemplate")
def delete_email_template(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _template(params)
    with db().lock:
        db().templates.pop(rec["TemplateName"], None)
        _save()
    return {}


@op("ListEmailTemplates", read=True)
def list_email_templates(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    with db().lock:
        items = [{"TemplateName": n, "CreatedTimestamp": db().templates[n].get("CreatedTimestamp")}
                 for n in sorted(db().templates)]
    chunk, more = _page(items, params, default=10, limit=100)
    return {"TemplatesMetadata": chunk, **more}


def render(content: Dict[str, Any], data: Dict[str, Any]) -> Tuple[str, Optional[str], Optional[str]]:
    """(subject, text or None, HTML or None) of a template with its data."""
    subject = templates.render(content.get("Subject"), data)
    text = templates.render(content["Text"], data) if content.get("Text") else None
    html = templates.render(content["Html"], data, html=True) if content.get("Html") else None
    if text is None and html is None:
        text = ""
    return subject, text, html


@op("TestRenderEmailTemplate", read=True)
def test_render(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _template(params)
    subject, text, html = render(rec, templates.data_of(params.get("TemplateData")))
    raw = mime.build(source="sender@example.com", to=[], cc=[], reply_to=[], subject=subject, text=text, html=html)
    return {"RenderedTemplate": raw.decode("utf-8", "replace")}


# ----------------------------------------------------------------------------- configuration sets


def _cs_out(rec: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "ConfigurationSetName": rec["Name"],
        "DeliveryOptions": {"TlsPolicy": rec.get("TlsPolicy", "OPTIONAL"),
                            **({"MaxDeliverySeconds": rec["MaxDeliverySeconds"]} if rec.get("MaxDeliverySeconds")
                               else {})},
        "ReputationOptions": {"ReputationMetricsEnabled": bool(rec.get("ReputationMetricsEnabled", False))},
        "SendingOptions": {"SendingEnabled": bool(rec.get("SendingEnabled", True))},
        "Tags": list(rec.get("Tags") or []),
    }
    if rec.get("SuppressedReasons") is not None:
        out["SuppressionOptions"] = {"SuppressedReasons": list(rec["SuppressedReasons"])}
    if rec.get("TrackingOptions"):
        out["TrackingOptions"] = rec["TrackingOptions"]
    return out


def _delivery_options(rec: Dict[str, Any], opts: Dict[str, Any]) -> None:
    policy = str(opts.get("TlsPolicy") or rec.get("TlsPolicy") or "OPTIONAL")
    if policy not in ("REQUIRE", "OPTIONAL"):
        raise bad_request("TlsPolicy must be REQUIRE or OPTIONAL.")
    rec["TlsPolicy"] = policy
    if opts.get("MaxDeliverySeconds") is not None:
        seconds = int(opts["MaxDeliverySeconds"])
        if not 300 <= seconds <= 50400:
            raise bad_request("MaxDeliverySeconds must be between 300 and 50400.")
        rec["MaxDeliverySeconds"] = seconds


@op("CreateConfigurationSet")
def create_configuration_set(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    name = _str(params, "ConfigurationSetName")
    if not NAME_RE.match(name):
        raise bad_request("ConfigurationSetName may contain only letters, digits, '_' and '-' (up to 64).")
    rec: Dict[str, Any] = {"Name": name, "CreatedTimestamp": now(), "SendingEnabled": True, "EventDestinations": {},
                           "Tags": _tags_in(params.get("Tags"))}
    _delivery_options(rec, params.get("DeliveryOptions") or {})
    if params.get("SendingOptions") is not None:
        rec["SendingEnabled"] = bool((params.get("SendingOptions") or {}).get("SendingEnabled", True))
    if params.get("SuppressionOptions") is not None:
        rec["SuppressedReasons"] = _reasons((params.get("SuppressionOptions") or {}).get("SuppressedReasons"))
    if params.get("TrackingOptions"):
        rec["TrackingOptions"] = dict(params["TrackingOptions"])
    if params.get("ReputationOptions"):
        rec["ReputationMetricsEnabled"] = bool(params["ReputationOptions"].get("ReputationMetricsEnabled"))
    with db().lock:
        if name in db().configuration_sets:
            raise exists(f"Configuration set <{name}> already exists.", "ConfigurationSetAlreadyExists")
        db().configuration_sets[name] = rec
        _save()
    return {}


@op("GetConfigurationSet", read=True)
def get_configuration_set(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    return _cs_out(_config_set(params.get("ConfigurationSetName")))


@op("ListConfigurationSets", read=True)
def list_configuration_sets(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    with db().lock:
        names = sorted(db().configuration_sets)
    chunk, more = _page(names, params)
    return {"ConfigurationSets": chunk, **more}


@op("DeleteConfigurationSet")
def delete_configuration_set(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _config_set(params.get("ConfigurationSetName"))
    with db().lock:
        db().configuration_sets.pop(rec["Name"], None)
        _save()
    return {}


@op("PutConfigurationSetSendingOptions")
def put_cs_sending(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _config_set(params.get("ConfigurationSetName"))
    with db().lock:
        rec["SendingEnabled"] = bool(params.get("SendingEnabled", False))
        _save()
    return {}


@op("PutConfigurationSetSuppressionOptions")
def put_cs_suppression(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _config_set(params.get("ConfigurationSetName"))
    with db().lock:
        if params.get("SuppressedReasons") is None:
            rec.pop("SuppressedReasons", None)
        else:
            rec["SuppressedReasons"] = _reasons(params.get("SuppressedReasons"))
        _save()
    return {}


@op("PutConfigurationSetDeliveryOptions")
def put_cs_delivery(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _config_set(params.get("ConfigurationSetName"))
    with db().lock:
        _delivery_options(rec, params)
        _save()
    return {}


@op("PutConfigurationSetReputationOptions")
def put_cs_reputation(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _config_set(params.get("ConfigurationSetName"))
    with db().lock:
        rec["ReputationMetricsEnabled"] = bool(params.get("ReputationMetricsEnabled", False))
        _save()
    return {}


@op("PutConfigurationSetTrackingOptions")
def put_cs_tracking(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _config_set(params.get("ConfigurationSetName"))
    with db().lock:
        rec["TrackingOptions"] = {k: params[k] for k in ("CustomRedirectDomain", "HttpsPolicy") if params.get(k)}
        _save()
    return {}


_EVENT_TYPES = ("SEND", "REJECT", "BOUNCE", "COMPLAINT", "DELIVERY", "OPEN", "CLICK", "RENDERING_FAILURE",
                "DELIVERY_DELAY", "SUBSCRIPTION")


def _event_destination(name: str, definition: Dict[str, Any]) -> Dict[str, Any]:
    types = [str(t) for t in definition.get("MatchingEventTypes") or []]
    if not types or any(t not in _EVENT_TYPES for t in types):
        raise bad_request(f"MatchingEventTypes must list some of {', '.join(_EVENT_TYPES)}.")
    out = {"Name": name, "Enabled": bool(definition.get("Enabled", False)), "MatchingEventTypes": types}
    for key in ("SnsDestination", "EventBridgeDestination", "CloudWatchDestination", "KinesisFirehoseDestination",
                "PinpointDestination"):
        if definition.get(key):
            out[key] = definition[key]
    return out


@op("CreateConfigurationSetEventDestination")
def create_event_destination(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _config_set(params.get("ConfigurationSetName"))
    name = _str(params, "EventDestinationName")
    dest = _event_destination(name, params.get("EventDestination") or {})
    with db().lock:
        dests = rec.setdefault("EventDestinations", {})
        if name in dests:
            raise exists(f"Event destination {name} already exists.")
        dests[name] = dest
        _save()
    return {}


@op("UpdateConfigurationSetEventDestination")
def update_event_destination(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _config_set(params.get("ConfigurationSetName"))
    name = _str(params, "EventDestinationName")
    with db().lock:
        dests = rec.setdefault("EventDestinations", {})
        if name not in dests:
            raise not_found(f"Event destination {name} does not exist.")
        dests[name] = _event_destination(name, params.get("EventDestination") or {})
        _save()
    return {}


@op("GetConfigurationSetEventDestinations", read=True)
def get_event_destinations(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _config_set(params.get("ConfigurationSetName"))
    return {"EventDestinations": [copy.deepcopy(d) for _n, d in sorted((rec.get("EventDestinations") or {}).items())]}


@op("DeleteConfigurationSetEventDestination")
def delete_event_destination(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _config_set(params.get("ConfigurationSetName"))
    name = _str(params, "EventDestinationName")
    with db().lock:
        if name not in (rec.get("EventDestinations") or {}):
            raise not_found(f"Event destination {name} does not exist.")
        rec["EventDestinations"].pop(name)
        _save()
    return {}


# ----------------------------------------------------------------------------- suppression list


def _suppressed_out(rec: Dict[str, Any], full: bool = False) -> Dict[str, Any]:
    out = {"EmailAddress": rec["EmailAddress"], "Reason": rec["Reason"], "LastUpdateTime": rec["LastUpdateTime"]}
    if full:
        out["Attributes"] = {k: rec[k] for k in ("MessageId", "FeedbackId") if rec.get(k)}
    return out


@op("PutSuppressedDestination")
def put_suppressed(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    addr = addresses([_str(params, "EmailAddress")])[0]
    reason = _str(params, "Reason")
    if reason not in ("BOUNCE", "COMPLAINT"):
        raise bad_request("Reason must be BOUNCE or COMPLAINT.")
    with db().lock:
        db().suppressed[addr.lower()] = {"EmailAddress": addr, "Reason": reason, "LastUpdateTime": now()}
        _save()
    return {}


@op("GetSuppressedDestination", read=True)
def get_suppressed(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    addr = _str(params, "EmailAddress").lower()
    rec = db().suppressed.get(addr)
    if rec is None:
        raise not_found(f"Email address {addr} does not exist on your suppression list.")
    return {"SuppressedDestination": _suppressed_out(rec, True)}


@op("DeleteSuppressedDestination")
def delete_suppressed(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    addr = _str(params, "EmailAddress").lower()
    with db().lock:
        if db().suppressed.pop(addr, None) is None:
            raise not_found(f"Email address {addr} does not exist on your suppression list.")
        _save()
    return {}


@op("ListSuppressedDestinations", read=True)
def list_suppressed(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    reasons = params.get("Reasons") or params.get("Reason") or []
    if isinstance(reasons, str):
        reasons = [reasons]
    start, end = _when(params.get("StartDate")), _when(params.get("EndDate"))
    with db().lock:
        items = [_suppressed_out(r) for _k, r in sorted(db().suppressed.items())
                 if (not reasons or r["Reason"] in reasons) and (start is None or r["LastUpdateTime"] >= start)
                 and (end is None or r["LastUpdateTime"] <= end)]
    chunk, more = _page(items, params)
    return {"SuppressedDestinationSummaries": chunk, **more}


def _when(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        from datetime import datetime

        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        except ValueError:
            raise bad_request(f"Invalid date {value!r}.") from None


# ----------------------------------------------------------------------------- tags


@op("TagResource")
def tag_resource(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _resource(params.get("ResourceArn"))
    new_tags = _tags_in(params.get("Tags"))
    with db().lock:
        tags = {t["Key"]: t["Value"] for t in rec.get("Tags") or []}
        tags.update({t["Key"]: t["Value"] for t in new_tags})
        if len(tags) > 50:
            raise bad_request("A resource can have up to 50 tags.")
        rec["Tags"] = [{"Key": k, "Value": v} for k, v in sorted(tags.items())]
        _save()
    return {}


@op("UntagResource")
def untag_resource(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _resource(params.get("ResourceArn"))
    keys = params.get("TagKeys") or []
    if isinstance(keys, str):
        keys = [keys]
    with db().lock:
        rec["Tags"] = [t for t in rec.get("Tags") or [] if t["Key"] not in keys]
        _save()
    return {}


@op("ListTagsForResource", read=True)
def list_tags(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    return {"Tags": list(_resource(params.get("ResourceArn")).get("Tags") or [])}


# ----------------------------------------------------------------------------- sending


def _destination(params: Dict[str, Any]) -> Tuple[List[str], List[str], List[str]]:
    dest = params.get("Destination") or {}
    return (addresses(dest.get("ToAddresses")), addresses(dest.get("CcAddresses")),
            addresses(dest.get("BccAddresses")))


def _template_parts(tpl: Dict[str, Any], data: Dict[str, Any]) -> Tuple[str, Optional[str], Optional[str]]:
    if tpl.get("TemplateContent"):
        content = {k: str(v or "") for k, v in (tpl.get("TemplateContent") or {}).items()}
        templates.check(content.get("Subject"), content.get("Text"), content.get("Html"))
    else:
        content = _template(tpl)
    return render(content, data)


def send_message(*, operation: str, ctx: Ctx, source: str, to: List[str], cc: List[str], bcc: List[str],
                 reply_to: List[str], content: Dict[str, Any], configuration_set: str = "", tags: Any = None,
                 return_path: str = "", envelope: Optional[List[str]] = None) -> str:
    """Send SES v2 ``EmailContent`` (``Simple``, ``Raw`` or ``Template``)."""
    common = {"operation": operation, "caller": ctx.get("caller", ""), "source_ip": ctx.get("source_ip", ""),
              "configuration_set_name": configuration_set, "tags": tags, "return_path": return_path}
    if content.get("Raw"):
        try:
            raw = base64.b64decode(str((content["Raw"] or {}).get("Data") or ""), validate=False)
        except (binascii.Error, ValueError):
            raise bad_request("Raw.Data must be base64.") from None
        if not raw.strip():
            raise bad_request("The raw message is empty.")
        header_from, h_to, h_cc, h_bcc = mime.raw_recipients(raw)
        dest = envelope if envelope is not None else (to + cc + bcc or None)
        if dest is None:
            dest = addresses(h_to) + addresses(h_cc) + addresses(h_bcc)
        return sender.accept(source=source or header_from, to=[], cc=[], bcc=[], envelope=dest,
                             build=sender.raw_build(raw), **common)
    if content.get("Template"):
        tpl = content["Template"] or {}
        subject, text, html = _template_parts(tpl, templates.data_of(tpl.get("TemplateData")))
        message = {"Subject": {"Data": subject}, "Body": {
            **({"Text": {"Data": text}} if text is not None else {}),
            **({"Html": {"Data": html}} if html is not None else {})},
            "Headers": tpl.get("Headers"), "Attachments": tpl.get("Attachments")}
    elif content.get("Simple"):
        message = content["Simple"] or {}
        if not (message.get("Subject") or {}).get("Data") and (message.get("Subject") is None):
            raise bad_request("Message.Subject is required.")
    else:
        raise bad_request("Content needs Simple, Raw or Template.")

    def build(message_id: str, date: float) -> bytes:
        return mime.simple(source, to, cc, reply_to, message, message_id, date)

    return sender.accept(source=source, to=to, cc=cc, bcc=bcc, envelope=envelope, build=build, **common)


@op("SendEmail")
def send_email(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    to, cc, bcc = _destination(params)
    content = params.get("Content") or {}
    source = str(params.get("FromEmailAddress") or "")
    if not source and not content.get("Raw"):
        raise bad_request("FromEmailAddress is required.")
    message_id = send_message(
        operation="SendEmail", ctx=ctx, source=source, to=to, cc=cc, bcc=bcc,
        reply_to=addresses(params.get("ReplyToAddresses")), content=content,
        configuration_set=str(params.get("ConfigurationSetName") or ""), tags=params.get("EmailTags"),
        return_path=str(params.get("FeedbackForwardingEmailAddress") or ""),
        envelope=(to + cc + bcc) if content.get("Raw") and (to or cc or bcc) else None)
    return {"MessageId": message_id}


_BULK_STATUS = {"MessageRejected": "MESSAGE_REJECTED", "MailFromDomainNotVerifiedException":
                "MAIL_FROM_DOMAIN_NOT_VERIFIED", "TooManyRequestsException": "ACCOUNT_THROTTLED",
                "LimitExceededException": "ACCOUNT_DAILY_QUOTA_EXCEEDED", "SendingPausedException":
                "ACCOUNT_SENDING_PAUSED", "BadRequestException": "INVALID_PARAMETER"}


def bulk_status(exc: ApiError) -> str:
    if exc.v1 == "ConfigurationSetDoesNotExist":
        return "CONFIGURATION_SET_NOT_FOUND"
    if exc.v1 == "TemplateDoesNotExist":
        return "TEMPLATE_NOT_FOUND"
    if exc.v1 == "ConfigurationSetSendingPausedException":
        return "CONFIGURATION_SET_SENDING_PAUSED"
    return _BULK_STATUS.get(exc.code, "FAILED")


@op("SendBulkEmail")
def send_bulk_email(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    source = _str(params, "FromEmailAddress")
    default = (params.get("DefaultContent") or {}).get("Template") or {}
    entries = params.get("BulkEmailEntries") or []
    if not entries or len(entries) > 50:
        raise bad_request("BulkEmailEntries must have 1 to 50 entries.")
    if not default.get("TemplateContent"):
        _template(default)  # a missing template fails the whole call, as on SES
    sender.check_sender(source)
    sender.configuration_set(str(params.get("ConfigurationSetName") or ""))
    base = templates.data_of(default.get("TemplateData") or "{}")
    results = []
    for entry in entries:
        try:
            to, cc, bcc = _destination(entry)
            replacement = ((entry.get("ReplacementEmailContent") or {}).get("ReplacementTemplate") or {}).get(
                "ReplacementTemplateData")
            data = {**base, **templates.data_of(replacement)} if replacement else base
            tpl = {**default, "TemplateData": data}
            if entry.get("ReplacementHeaders"):
                tpl["Headers"] = entry["ReplacementHeaders"]
            tags = entry.get("ReplacementTags") or params.get("DefaultEmailTags")
            message_id = send_message(
                operation="SendBulkEmail", ctx=ctx, source=source, to=to, cc=cc, bcc=bcc,
                reply_to=addresses(params.get("ReplyToAddresses")), content={"Template": tpl},
                configuration_set=str(params.get("ConfigurationSetName") or ""), tags=tags,
                return_path=str(params.get("FeedbackForwardingEmailAddress") or ""))
            results.append({"Status": "SUCCESS", "MessageId": message_id})
        except ApiError as exc:
            results.append({"Status": bulk_status(exc), "Error": exc.message})
    return {"BulkEmailEntryResults": results}


# ----------------------------------------------------------------------------- console only


def _summary(rec: Dict[str, Any]) -> Dict[str, Any]:
    return {k: rec.get(k) for k in ("MessageId", "Timestamp", "Source", "From", "Destinations", "Subject", "Status",
                                    "Operation", "ConfigurationSetName", "Size", "DkimDomain", "Caller")}


@op("ListMessages", read=True)
def list_messages(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    status = str(params.get("Status") or "")
    text = str(params.get("Query") or "").lower()
    with db().lock:
        recs = sorted(db().messages.values(), key=lambda r: r["Timestamp"], reverse=True)
        items = [_summary(r) for r in recs
                 if (not status or r.get("Status") == status)
                 and (not text or text in " ".join([r["MessageId"], r.get("Source") or "", r.get("Subject") or "",
                                                    " ".join(r.get("Destinations") or [])]).lower())]
    chunk, more = _page(items, params, default=50)
    return {"Messages": chunk, "Total": len(items), **more}


def _message(params: Dict[str, Any]) -> Dict[str, Any]:
    rec = db().messages.get(str(params.get("MessageId") or ""))
    if rec is None:
        raise not_found("Message not found (it may be older than the retention period).")
    return rec


@op("GetMessage", read=True)
def get_message(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    with db().lock:
        rec = copy.deepcopy(_message(params))
    try:
        raw = db().raw(rec["MessageId"])
    except OSError:
        raw = b""
    out = {**rec, "Content": mime.read(raw) if raw else {}}
    if params.get("IncludeRaw"):
        out["Raw"] = raw[:5 * 1024 * 1024].decode("utf-8", "replace")
    return out


@op("DeleteMessage")
def delete_message(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _message(params)
    db().delete_message(rec["MessageId"])
    return {}


@op("RetryMessage")
def retry_message(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _message(params)
    with db().lock:
        for st in rec["Recipients"].values():
            if st["Status"] in ("QUEUED", "DELAYED"):
                st["NextAttempt"] = now()
        db().save_message(rec)
    if sender._wake:  # noqa: SLF001 - the worker's wake-up
        sender._wake()  # noqa: SLF001
    return {}


@op("CheckEmailIdentity")
def check_email_identity(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _identity(_str(params, "EmailIdentity"))
    if rec["IdentityType"] == "DOMAIN":
        identities.check(rec["IdentityName"])
    return identity_out(rec)


@op("SetEmailIdentityVerified")
def set_identity_verified(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    rec = _identity(_str(params, "EmailIdentity"))
    return identity_out(identities.set_verified(rec["IdentityName"], bool(params.get("Verified", True))))


@op("GetEmailIdentityDnsRecords", read=True)
def identity_dns(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    return {"Records": identities.dns_records(_identity(_str(params, "EmailIdentity")))}


@op("GetServerInfo", read=True)
def server_info(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    return {
        "Version": VERSION, "Implementation": "Python", "Region": REGION, "AccountId": ACCOUNT,
        "Delivery": DELIVERY, "Relay": {"Host": RELAY_HOST, "Port": RELAY_PORT, "Tls": RELAY_TLS,
                                        "User": RELAY_USER} if DELIVERY == "relay" else None,
        "DirectPort": DIRECT_PORT, "HeloName": HELO_NAME, "Verify": VERIFY, "Sandbox": SANDBOX,
        "DkimCheck": DKIM_CHECK, "EventsWebhook": bool(EVENTS_URL), "RetentionDays": RETENTION_DAYS,
        "RetryHours": RETRY_HOURS, "MaxMessageBytes": MAX_MESSAGE,
        "Smtp": {"Enabled": SMTP_ON, "Port": SMTP_PORT, "Host": SMTP_HOST, "StartTls": bool(TLS_CERT),
                 "RequireTls": SMTP_REQUIRE_TLS},
    }


@op("GetStatistics", read=True)
def statistics(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    """Per day (UTC) for ``Days`` days (default 14): recipients sent, delivered, bounced, complaints, delayed."""
    days = max(1, min(int(params.get("Days") or 14), 90))
    today = int(time.time()) // 86400
    buckets = {d: {"Date": d * 86400, "Sent": 0, "Delivered": 0, "Bounced": 0, "Complaints": 0, "Rejected": 0,
                   "Delayed": 0} for d in range(today - days + 1, today + 1)}
    status: Dict[str, int] = {}
    with db().lock:
        for rec in db().messages.values():
            status[rec.get("Status") or ""] = status.get(rec.get("Status") or "", 0) + 1
            for ev in rec.get("Events") or []:
                day = int(ev["Timestamp"]) // 86400
                if day not in buckets:
                    continue
                field = {"Send": "Sent", "Delivery": "Delivered", "Bounce": "Bounced", "Complaint": "Complaints",
                         "Reject": "Rejected", "DeliveryDelay": "Delayed"}.get(ev["Type"])
                if field:
                    buckets[day][field] += len(ev.get("Recipients") or [])
        counts = {"Identities": len(db().identities), "Templates": len(db().templates),
                  "ConfigurationSets": len(db().configuration_sets), "Suppressed": len(db().suppressed),
                  "Messages": len(db().messages)}
    return {"Days": [buckets[d] for d in sorted(buckets)], "MessagesByStatus": status, "Counts": counts,
            "Account": _account(ctx)}


@op("GetSmtpCredentials", read=True)
def smtp_credentials(params: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    from .sigv4 import smtp_password

    user = str(ctx.get("user") or "")
    key = user if user in CREDENTIALS else next(iter(sorted(CREDENTIALS)), "")
    if not key:
        return {"Username": "", "Password": "", "Note": "SES_AUTH=off: the SMTP endpoint takes any login."}
    return {"Username": key, "Password": smtp_password(CREDENTIALS[key], ctx.get("region") or REGION),
            "Region": ctx.get("region") or REGION}
