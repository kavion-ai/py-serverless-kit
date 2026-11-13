"""The SES v1 API (``POST /`` with ``Action=...&Version=2010-12-01``, answers in XML): boto3's ``ses`` client, the
``aws ses`` CLI commands, and older SDKs and libraries. Each action is translated to an operation of
``operations.py`` and its answer back to the v1 shape."""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Dict, List, Tuple
from urllib.parse import parse_qsl
from xml.sax.saxutils import escape

from . import identities
from . import operations as ops
from .errors import ApiError, bad_request
from .store import db
from .util import addresses, iso

NS = "http://ses.amazonaws.com/doc/2010-12-01/"
Ctx = Dict[str, Any]
ACTIONS: Dict[str, Callable[[Dict[str, Any], Ctx], Any]] = {}


class XmlMap(dict):  # type: ignore[type-arg]
    """A map answered as ``<entry><key/><value/></entry>`` items."""


class Ts(float):
    """A timestamp answered in ISO 8601."""


def action(name: str) -> Callable[[Callable[[Dict[str, Any], Ctx], Any]], Callable[[Dict[str, Any], Ctx], Any]]:
    def wrap(fn: Callable[[Dict[str, Any], Ctx], Any]) -> Callable[[Dict[str, Any], Ctx], Any]:
        ACTIONS[name] = fn
        return fn
    return wrap


# ----------------------------------------------------------------------------- request and answer


def parse(body: bytes, query: str) -> Dict[str, Any]:
    """Form fields (``A.B.member.1.C=v``) as nested dicts and lists."""
    pairs = parse_qsl(query, keep_blank_values=True) + parse_qsl(body.decode("utf-8"), keep_blank_values=True)
    root: Dict[str, Any] = {}
    for key, value in pairs:
        cur = root
        parts = key.split(".")
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                cur[part] = value
            else:
                nxt = cur.get(part)
                if not isinstance(nxt, dict):
                    nxt = cur[part] = {}
                cur = nxt
    return _lists(root)


def _lists(node: Any) -> Any:
    if not isinstance(node, dict):
        return node
    if set(node) == {"member"} and isinstance(node["member"], dict):
        items = node["member"]
        return [_lists(items[k]) for k in sorted(items, key=lambda k: int(k) if k.isdigit() else 0)]
    return {k: _lists(v) for k, v in node.items()}


def _xml(name: str, value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, XmlMap):
        inner = "".join(f"<entry><key>{escape(str(k))}</key>{_xml('value', v)}</entry>" for k, v in value.items())
        return f"<{name}>{inner}</{name}>"
    if isinstance(value, dict):
        return f"<{name}>{''.join(_xml(k, v) for k, v in value.items())}</{name}>"
    if isinstance(value, list):
        return f"<{name}>{''.join(_xml('member', v) for v in value)}</{name}>"
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, Ts):
        text = iso(float(value))
    elif isinstance(value, float) and value.is_integer():
        text = f"{value:.1f}"
    else:
        text = str(value)
    return f"<{name}>{escape(text)}</{name}>"


def answer(name: str, result: Any) -> Tuple[int, bytes]:
    request_id = str(uuid.uuid4())
    inner = "" if result is None else _xml(f"{name}Result", result)
    body = (f'<{name}Response xmlns="{NS}">{inner}<ResponseMetadata><RequestId>{request_id}</RequestId>'
            f"</ResponseMetadata></{name}Response>")
    return 200, body.encode("utf-8")


def error(exc: ApiError) -> Tuple[int, bytes]:
    kind = "Receiver" if exc.status >= 500 else "Sender"
    status = 400 if exc.status in (404, 429) else exc.status
    body = (f'<ErrorResponse xmlns="{NS}"><Error><Type>{kind}</Type><Code>{escape(exc.v1)}</Code>'
            f"<Message>{escape(exc.message)}</Message></Error><RequestId>{uuid.uuid4()}</RequestId></ErrorResponse>")
    return status, body.encode("utf-8")


def handle(body: bytes, query: str, ctx: Ctx) -> Tuple[int, bytes]:
    try:
        params = parse(body, query)
    except UnicodeDecodeError:
        return error(bad_request("The request body is not UTF-8 form data."))
    name = str(params.get("Action") or "")
    fn = ACTIONS.get(name)
    if fn is None:
        return error(ApiError("BadRequestException", f"The action {name or '(none)'} is not valid for this web "
                              "service.", 400, "InvalidAction"))
    try:
        return answer(name, fn(params, ctx))
    except ApiError as exc:
        return error(exc)


# ----------------------------------------------------------------------------- helpers

_STATUS = {"SUCCESS": "Success", "PENDING": "Pending", "FAILED": "Failed", "TEMPORARY_FAILURE": "TemporaryFailure",
           "NOT_STARTED": "NotStarted"}


def _dest(d: Any) -> Dict[str, List[str]]:
    d = d if isinstance(d, dict) else {}
    return {k: d.get(k) or [] for k in ("ToAddresses", "CcAddresses", "BccAddresses")}


def _send(params: Dict[str, Any], ctx: Ctx, operation: str, content: Dict[str, Any]) -> str:
    dest = _dest(params.get("Destination"))
    return ops.send_message(
        operation=operation, ctx=ctx, source=str(params.get("Source") or ""),
        to=addresses(dest["ToAddresses"]), cc=addresses(dest["CcAddresses"]), bcc=addresses(dest["BccAddresses"]),
        reply_to=addresses(params.get("ReplyToAddresses")), content=content,
        configuration_set=str(params.get("ConfigurationSetName") or ""), tags=params.get("Tags"),
        return_path=str(params.get("ReturnPath") or ""))


def _required(params: Dict[str, Any], *names: str) -> None:
    for name in names:
        if params.get(name) in (None, ""):
            raise ApiError("BadRequestException", f"{name} is required.", 400, "MissingParameter")


# ----------------------------------------------------------------------------- sending


@action("SendEmail")
def send_email(params: Dict[str, Any], ctx: Ctx) -> Any:
    _required(params, "Source", "Message")
    message = params["Message"] if isinstance(params["Message"], dict) else {}
    if not message.get("Body"):
        raise ApiError("BadRequestException", "Message.Body is required.", 400, "MissingParameter")
    message.setdefault("Subject", {"Data": ""})
    return {"MessageId": _send(params, ctx, "SendEmail", {"Simple": message})}


@action("SendRawEmail")
def send_raw_email(params: Dict[str, Any], ctx: Ctx) -> Any:
    raw = params.get("RawMessage") if isinstance(params.get("RawMessage"), dict) else {}
    if not raw.get("Data"):
        raise ApiError("BadRequestException", "RawMessage.Data is required.", 400, "MissingParameter")
    dests = params.get("Destinations")
    message_id = ops.send_message(
        operation="SendRawEmail", ctx=ctx, source=str(params.get("Source") or ""), to=[], cc=[], bcc=[], reply_to=[],
        content={"Raw": {"Data": raw["Data"]}}, configuration_set=str(params.get("ConfigurationSetName") or ""),
        tags=params.get("Tags"), envelope=addresses(dests) if dests else None)
    return {"MessageId": message_id}


@action("SendTemplatedEmail")
def send_templated_email(params: Dict[str, Any], ctx: Ctx) -> Any:
    _required(params, "Source", "Template", "TemplateData")
    tpl = {"TemplateName": params["Template"], "TemplateData": params["TemplateData"]}
    return {"MessageId": _send(params, ctx, "SendTemplatedEmail", {"Template": tpl})}


_BULK_V1 = {"SUCCESS": "Success", "MESSAGE_REJECTED": "MessageRejected", "MAIL_FROM_DOMAIN_NOT_VERIFIED":
            "MailFromDomainNotVerified", "CONFIGURATION_SET_NOT_FOUND": "ConfigurationSetDoesNotExist",
            "TEMPLATE_NOT_FOUND": "TemplateDoesNotExist", "ACCOUNT_THROTTLED": "AccountThrottled",
            "ACCOUNT_DAILY_QUOTA_EXCEEDED": "AccountDailyQuotaExceeded", "ACCOUNT_SENDING_PAUSED":
            "AccountSendingPaused", "CONFIGURATION_SET_SENDING_PAUSED": "ConfigurationSetSendingPaused",
            "INVALID_PARAMETER": "InvalidParameterValue", "FAILED": "Failed"}


@action("SendBulkTemplatedEmail")
def send_bulk(params: Dict[str, Any], ctx: Ctx) -> Any:
    _required(params, "Source", "Template", "DefaultTemplateData", "Destinations")
    entries = []
    for d in params.get("Destinations") or []:
        entry: Dict[str, Any] = {"Destination": _dest(d.get("Destination"))}
        if d.get("ReplacementTemplateData"):
            entry["ReplacementEmailContent"] = {"ReplacementTemplate": {
                "ReplacementTemplateData": d["ReplacementTemplateData"]}}
        if d.get("ReplacementTags"):
            entry["ReplacementTags"] = d["ReplacementTags"]
        entries.append(entry)
    out = ops.send_bulk_email({
        "FromEmailAddress": params["Source"], "ReplyToAddresses": params.get("ReplyToAddresses"),
        "ConfigurationSetName": params.get("ConfigurationSetName"), "DefaultEmailTags": params.get("DefaultTags"),
        "DefaultContent": {"Template": {"TemplateName": params["Template"],
                                        "TemplateData": params["DefaultTemplateData"]}},
        "BulkEmailEntries": entries}, ctx)
    status = []
    for r in out["BulkEmailEntryResults"]:
        item = {"Status": _BULK_V1.get(r["Status"], "Failed")}
        if r.get("Error"):
            item["Error"] = r["Error"]
        if r.get("MessageId"):
            item["MessageId"] = r["MessageId"]
        status.append(item)
    return {"Status": status}


# ----------------------------------------------------------------------------- identities


@action("VerifyEmailIdentity")
def verify_email_identity(params: Dict[str, Any], ctx: Ctx) -> Any:
    _required(params, "EmailAddress")
    ops.create_identity(str(params["EmailAddress"]), {}, idempotent=True)
    return {}


@action("VerifyEmailAddress")
def verify_email_address(params: Dict[str, Any], ctx: Ctx) -> Any:
    verify_email_identity(params, ctx)
    return None


@action("VerifyDomainIdentity")
def verify_domain_identity(params: Dict[str, Any], ctx: Ctx) -> Any:
    _required(params, "Domain")
    if "@" in str(params["Domain"]):
        raise ApiError("BadRequestException", "Invalid domain name.", 400, "InvalidParameterValue")
    rec = ops.create_identity(str(params["Domain"]), {}, idempotent=True)
    return {"VerificationToken": rec.get("VerificationToken") or ""}


@action("VerifyDomainDkim")
def verify_domain_dkim(params: Dict[str, Any], ctx: Ctx) -> Any:
    rec = verify_domain_identity(params, ctx)
    del rec
    ident = db().identities[identities.normalize(params["Domain"])]
    return {"DkimTokens": [ident["Dkim"]["Selector"]] if ident.get("Dkim") else []}


@action("ListIdentities")
def list_identities(params: Dict[str, Any], ctx: Ctx) -> Any:
    kind = {"EmailAddress": "EMAIL_ADDRESS", "Domain": "DOMAIN"}.get(str(params.get("IdentityType") or ""))
    with db().lock:
        names = [n for n in sorted(db().identities) if not kind or db().identities[n]["IdentityType"] == kind]
    chunk, more = ops._page(names, params, default=1000)  # noqa: SLF001 - shared paging
    return {"Identities": chunk, **more}


@action("ListVerifiedEmailAddresses")
def list_verified(params: Dict[str, Any], ctx: Ctx) -> Any:
    with db().lock:
        names = [n for n, r in sorted(db().identities.items())
                 if r["IdentityType"] == "EMAIL_ADDRESS" and identities.status_of(r) == "SUCCESS"]
    return {"VerifiedEmailAddresses": names}


def _identity_names(params: Dict[str, Any]) -> List[str]:
    names = params.get("Identities") or []
    if not isinstance(names, list) or len(names) > 100:
        raise ApiError("BadRequestException", "Identities must list up to 100 identities.", 400,
                       "InvalidParameterValue")
    return [identities.normalize(n) for n in names]


@action("GetIdentityVerificationAttributes")
def verification_attributes(params: Dict[str, Any], ctx: Ctx) -> Any:
    out = XmlMap()
    with db().lock:
        for name in _identity_names(params):
            rec = db().identities.get(name)
            if rec is None:
                continue
            item = {"VerificationStatus": _STATUS.get(identities.status_of(rec), "Pending")}
            if rec.get("VerificationToken"):
                item["VerificationToken"] = rec["VerificationToken"]
            out[name] = item
    return {"VerificationAttributes": out}


@action("GetIdentityDkimAttributes")
def dkim_attributes(params: Dict[str, Any], ctx: Ctx) -> Any:
    out = XmlMap()
    with db().lock:
        for name in _identity_names(params):
            rec = db().identities.get(name)
            if rec is None:
                continue
            dk = ops._dkim_out(rec)  # noqa: SLF001
            item: Dict[str, Any] = {"DkimEnabled": dk["SigningEnabled"],
                                    "DkimVerificationStatus": _STATUS.get(dk["Status"], "NotStarted")}
            if rec.get("Dkim"):
                item["DkimTokens"] = dk["Tokens"]
            out[name] = item
    return {"DkimAttributes": out}


@action("GetIdentityMailFromDomainAttributes")
def mail_from_attributes(params: Dict[str, Any], ctx: Ctx) -> Any:
    out = XmlMap()
    with db().lock:
        for name in _identity_names(params):
            rec = db().identities.get(name)
            if rec is None or not rec.get("MailFrom"):
                continue
            mf = rec["MailFrom"]
            out[name] = {"MailFromDomain": mf["MailFromDomain"],
                         "MailFromDomainStatus": _STATUS.get(mf.get("MailFromDomainStatus", "PENDING"), "Pending"),
                         "BehaviorOnMXFailure": "RejectMessage" if mf.get("BehaviorOnMxFailure") == "REJECT_MESSAGE"
                         else "UseDefaultValue"}
    return {"MailFromDomainAttributes": out}


@action("SetIdentityMailFromDomain")
def set_mail_from(params: Dict[str, Any], ctx: Ctx) -> Any:
    _required(params, "Identity")
    behavior = "REJECT_MESSAGE" if params.get("BehaviorOnMXFailure") == "RejectMessage" else "USE_DEFAULT_VALUE"
    ops.put_identity_mail_from({"EmailIdentity": params["Identity"], "MailFromDomain": params.get("MailFromDomain"),
                                "BehaviorOnMxFailure": behavior}, ctx)
    return {}


@action("SetIdentityDkimEnabled")
def set_dkim_enabled(params: Dict[str, Any], ctx: Ctx) -> Any:
    _required(params, "Identity", "DkimEnabled")
    ops.put_identity_dkim({"EmailIdentity": params["Identity"],
                           "SigningEnabled": str(params["DkimEnabled"]).lower() == "true"}, ctx)
    return {}


@action("SetIdentityFeedbackForwardingEnabled")
def set_feedback(params: Dict[str, Any], ctx: Ctx) -> Any:
    _required(params, "Identity", "ForwardingEnabled")
    ops.put_identity_feedback({"EmailIdentity": params["Identity"],
                               "EmailForwardingEnabled": str(params["ForwardingEnabled"]).lower() == "true"}, ctx)
    return {}


@action("DeleteIdentity")
def delete_identity(params: Dict[str, Any], ctx: Ctx) -> Any:
    _required(params, "Identity")
    with db().lock:
        if db().identities.pop(identities.normalize(params["Identity"]), None) is not None:
            db().save()
    return {}


@action("DeleteVerifiedEmailAddress")
def delete_verified(params: Dict[str, Any], ctx: Ctx) -> Any:
    _required(params, "EmailAddress")
    delete_identity({"Identity": params["EmailAddress"]}, ctx)
    return None


# ----------------------------------------------------------------------------- account


@action("GetSendQuota")
def get_send_quota(params: Dict[str, Any], ctx: Ctx) -> Any:
    return dict(ops._account(ctx)["SendQuota"])  # noqa: SLF001


@action("GetSendStatistics")
def get_send_statistics(params: Dict[str, Any], ctx: Ctx) -> Any:
    since = time.time() - 14 * 86400
    buckets: Dict[int, Dict[str, Any]] = {}
    for rec in db().recent(since - 86400):
        for ev in rec.get("Events") or []:
            if ev["Timestamp"] < since:
                continue
            slot = int(ev["Timestamp"]) // 900 * 900
            b = buckets.setdefault(slot, {"Timestamp": Ts(slot), "DeliveryAttempts": 0, "Bounces": 0,
                                          "Complaints": 0, "Rejects": 0})
            field = {"Send": "DeliveryAttempts", "Bounce": "Bounces", "Complaint": "Complaints",
                     "Reject": "Rejects"}.get(ev["Type"])
            if field:
                b[field] += len(ev.get("Recipients") or [])
    return {"SendDataPoints": [buckets[k] for k in sorted(buckets)]}


@action("GetAccountSendingEnabled")
def get_sending_enabled(params: Dict[str, Any], ctx: Ctx) -> Any:
    return {"Enabled": bool(db().account.get("SendingEnabled", True))}


@action("UpdateAccountSendingEnabled")
def update_sending_enabled(params: Dict[str, Any], ctx: Ctx) -> Any:
    ops.put_account_sending({"SendingEnabled": str(params.get("Enabled", "false")).lower() == "true"}, ctx)
    return None


# ----------------------------------------------------------------------------- templates


def _v1_template(params: Dict[str, Any]) -> Dict[str, Any]:
    tpl = params.get("Template") if isinstance(params.get("Template"), dict) else {}
    if not tpl.get("TemplateName"):
        raise ApiError("BadRequestException", "Template.TemplateName is required.", 400, "MissingParameter")
    return {"TemplateName": tpl["TemplateName"], "TemplateContent": {
        "Subject": tpl.get("SubjectPart") or "", "Text": tpl.get("TextPart") or "", "Html": tpl.get("HtmlPart") or ""}}


@action("CreateTemplate")
def create_template(params: Dict[str, Any], ctx: Ctx) -> Any:
    ops.create_email_template(_v1_template(params), ctx)
    return {}


@action("UpdateTemplate")
def update_template(params: Dict[str, Any], ctx: Ctx) -> Any:
    ops.update_email_template(_v1_template(params), ctx)
    return {}


@action("GetTemplate")
def get_template(params: Dict[str, Any], ctx: Ctx) -> Any:
    _required(params, "TemplateName")
    out = ops.get_email_template({"TemplateName": params["TemplateName"]}, ctx)
    content = out["TemplateContent"]
    tpl = {"TemplateName": out["TemplateName"], "SubjectPart": content["Subject"]}
    if content["Text"]:
        tpl["TextPart"] = content["Text"]
    if content["Html"]:
        tpl["HtmlPart"] = content["Html"]
    return {"Template": tpl}


@action("DeleteTemplate")
def delete_template(params: Dict[str, Any], ctx: Ctx) -> Any:
    _required(params, "TemplateName")
    with db().lock:
        if db().templates.pop(str(params["TemplateName"]), None) is not None:
            db().save()
    return {}


@action("ListTemplates")
def list_templates(params: Dict[str, Any], ctx: Ctx) -> Any:
    out = ops.list_email_templates({"NextToken": params.get("NextToken"), "PageSize": params.get("MaxItems") or 10},
                                   ctx)
    meta = [{"Name": m["TemplateName"], "CreatedTimestamp": Ts(m["CreatedTimestamp"] or 0)}
            for m in out["TemplatesMetadata"]]
    return {"TemplatesMetadata": meta, **({"NextToken": out["NextToken"]} if out.get("NextToken") else {})}


@action("TestRenderTemplate")
def test_render_template(params: Dict[str, Any], ctx: Ctx) -> Any:
    _required(params, "TemplateName", "TemplateData")
    return ops.test_render({"TemplateName": params["TemplateName"], "TemplateData": params["TemplateData"]}, ctx)


# ----------------------------------------------------------------------------- configuration sets


@action("CreateConfigurationSet")
def create_configuration_set(params: Dict[str, Any], ctx: Ctx) -> Any:
    cs = params.get("ConfigurationSet") if isinstance(params.get("ConfigurationSet"), dict) else {}
    if not cs.get("Name"):
        raise ApiError("BadRequestException", "ConfigurationSet.Name is required.", 400, "MissingParameter")
    try:
        ops.create_configuration_set({"ConfigurationSetName": cs["Name"]}, ctx)
    except ApiError as exc:
        if exc.code == "BadRequestException":
            raise ApiError(exc.code, exc.message, 400, "InvalidConfigurationSet") from None
        raise
    return {}


@action("DeleteConfigurationSet")
def delete_configuration_set(params: Dict[str, Any], ctx: Ctx) -> Any:
    ops.delete_configuration_set({"ConfigurationSetName": params.get("ConfigurationSetName")}, ctx)
    return {}


@action("ListConfigurationSets")
def list_configuration_sets(params: Dict[str, Any], ctx: Ctx) -> Any:
    out = ops.list_configuration_sets({"NextToken": params.get("NextToken"), "PageSize": params.get("MaxItems")}, ctx)
    return {"ConfigurationSets": [{"Name": n} for n in out["ConfigurationSets"]],
            **({"NextToken": out["NextToken"]} if out.get("NextToken") else {})}


@action("DescribeConfigurationSet")
def describe_configuration_set(params: Dict[str, Any], ctx: Ctx) -> Any:
    out = ops.get_configuration_set({"ConfigurationSetName": params.get("ConfigurationSetName")}, ctx)
    dests = ops.get_event_destinations({"ConfigurationSetName": params.get("ConfigurationSetName")}, ctx)
    camel = {"SEND": "send", "REJECT": "reject", "BOUNCE": "bounce", "COMPLAINT": "complaint", "DELIVERY": "delivery",
             "OPEN": "open", "CLICK": "click", "RENDERING_FAILURE": "renderingFailure",
             "DELIVERY_DELAY": "deliveryDelay", "SUBSCRIPTION": "subscription"}
    return {
        "ConfigurationSet": {"Name": out["ConfigurationSetName"]},
        "EventDestinations": [{"Name": d["Name"], "Enabled": d["Enabled"],
                               "MatchingEventTypes": [camel.get(t, t) for t in d["MatchingEventTypes"]]}
                              for d in dests["EventDestinations"]],
        "DeliveryOptions": {"TlsPolicy": "Require" if out["DeliveryOptions"]["TlsPolicy"] == "REQUIRE" else "Optional"},
        "ReputationOptions": {"SendingEnabled": out["SendingOptions"]["SendingEnabled"],
                              "ReputationMetricsEnabled": out["ReputationOptions"]["ReputationMetricsEnabled"]},
    }
