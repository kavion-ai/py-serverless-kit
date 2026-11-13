"""The SES v2 REST API (``/v2/email/...``, JSON): boto3's ``sesv2`` client, ``@aws-sdk/client-sesv2``, nodemailer's
SES transport, the ``aws sesv2`` CLI. Each route calls an operation of ``operations.py``; path and query parameters
are merged into its parameters. Errors: the status of the error, ``x-amzn-ErrorType`` and ``{"message": ...}``."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, unquote

from .errors import ApiError
from .operations import run

_SEG = r"([^/]+)"
# (method, path pattern, operation, names of the path parameters)
ROUTES: List[Tuple[str, re.Pattern[str], str, Tuple[str, ...]]] = []


def _route(method: str, path: str, operation: str, *names: str) -> None:
    pattern = re.compile("^" + re.sub(r"\{[^}]+\}", _SEG, path) + "/?$")
    ROUTES.append((method, pattern, operation, names))


_route("POST", "/v2/email/outbound-emails", "SendEmail")
_route("POST", "/v2/email/outbound-bulk-emails", "SendBulkEmail")
_route("GET", "/v2/email/account", "GetAccount")
_route("PUT", "/v2/email/account/sending", "PutAccountSendingAttributes")
_route("PUT", "/v2/email/account/suppression", "PutAccountSuppressionAttributes")
_route("POST", "/v2/email/identities", "CreateEmailIdentity")
_route("GET", "/v2/email/identities", "ListEmailIdentities")
_route("POST", "/v2/email/list-identities", "ListEmailIdentities")
_route("GET", "/v2/email/identities/{EmailIdentity}", "GetEmailIdentity", "EmailIdentity")
_route("DELETE", "/v2/email/identities/{EmailIdentity}", "DeleteEmailIdentity", "EmailIdentity")
_route("PUT", "/v2/email/identities/{EmailIdentity}/dkim", "PutEmailIdentityDkimAttributes", "EmailIdentity")
_route("PUT", "/v2/email/identities/{EmailIdentity}/dkim/signing", "PutEmailIdentityDkimSigningAttributes",
       "EmailIdentity")
_route("PUT", "/v1/email/identities/{EmailIdentity}/dkim/signing", "PutEmailIdentityDkimSigningAttributes",
       "EmailIdentity")
_route("PUT", "/v2/email/identities/{EmailIdentity}/mail-from", "PutEmailIdentityMailFromAttributes", "EmailIdentity")
_route("PUT", "/v2/email/identities/{EmailIdentity}/feedback", "PutEmailIdentityFeedbackAttributes", "EmailIdentity")
_route("PUT", "/v2/email/identities/{EmailIdentity}/configuration-set", "PutEmailIdentityConfigurationSetAttributes",
       "EmailIdentity")
_route("POST", "/v2/email/templates", "CreateEmailTemplate")
_route("GET", "/v2/email/templates", "ListEmailTemplates")
_route("GET", "/v2/email/templates/{TemplateName}", "GetEmailTemplate", "TemplateName")
_route("PUT", "/v2/email/templates/{TemplateName}", "UpdateEmailTemplate", "TemplateName")
_route("DELETE", "/v2/email/templates/{TemplateName}", "DeleteEmailTemplate", "TemplateName")
_route("POST", "/v2/email/templates/{TemplateName}/render", "TestRenderEmailTemplate", "TemplateName")
_route("POST", "/v2/email/configuration-sets", "CreateConfigurationSet")
_route("GET", "/v2/email/configuration-sets", "ListConfigurationSets")
_route("POST", "/v2/email/list-configuration-sets", "ListConfigurationSets")
_route("GET", "/v2/email/configuration-sets/{ConfigurationSetName}", "GetConfigurationSet", "ConfigurationSetName")
_route("DELETE", "/v2/email/configuration-sets/{ConfigurationSetName}", "DeleteConfigurationSet",
       "ConfigurationSetName")
_route("PUT", "/v2/email/configuration-sets/{ConfigurationSetName}/sending", "PutConfigurationSetSendingOptions",
       "ConfigurationSetName")
_route("PUT", "/v2/email/configuration-sets/{ConfigurationSetName}/suppression-options",
       "PutConfigurationSetSuppressionOptions", "ConfigurationSetName")
_route("PUT", "/v2/email/configuration-sets/{ConfigurationSetName}/delivery-options",
       "PutConfigurationSetDeliveryOptions", "ConfigurationSetName")
_route("PUT", "/v2/email/configuration-sets/{ConfigurationSetName}/reputation-options",
       "PutConfigurationSetReputationOptions", "ConfigurationSetName")
_route("PUT", "/v2/email/configuration-sets/{ConfigurationSetName}/tracking-options",
       "PutConfigurationSetTrackingOptions", "ConfigurationSetName")
_route("POST", "/v2/email/configuration-sets/{ConfigurationSetName}/event-destinations",
       "CreateConfigurationSetEventDestination", "ConfigurationSetName")
_route("GET", "/v2/email/configuration-sets/{ConfigurationSetName}/event-destinations",
       "GetConfigurationSetEventDestinations", "ConfigurationSetName")
_route("PUT", "/v2/email/configuration-sets/{ConfigurationSetName}/event-destinations/{EventDestinationName}",
       "UpdateConfigurationSetEventDestination", "ConfigurationSetName", "EventDestinationName")
_route("DELETE", "/v2/email/configuration-sets/{ConfigurationSetName}/event-destinations/{EventDestinationName}",
       "DeleteConfigurationSetEventDestination", "ConfigurationSetName", "EventDestinationName")
_route("PUT", "/v2/email/suppression/addresses", "PutSuppressedDestination")
_route("GET", "/v2/email/suppression/addresses", "ListSuppressedDestinations")
_route("GET", "/v2/email/suppression/addresses/{EmailAddress}", "GetSuppressedDestination", "EmailAddress")
_route("DELETE", "/v2/email/suppression/addresses/{EmailAddress}", "DeleteSuppressedDestination", "EmailAddress")
_route("POST", "/v2/email/tags", "TagResource")
_route("GET", "/v2/email/tags", "ListTagsForResource")
_route("DELETE", "/v2/email/tags", "UntagResource")

# Query parameters that may repeat (lists).
_LISTS = {"Reason": "Reasons", "TagKeys": "TagKeys"}


def match(method: str, path: str) -> Optional[Tuple[str, Dict[str, str]]]:
    """(operation, path parameters) of a request, or None when no route matches. 405 is answered as 404, as AWS."""
    for verb, pattern, operation, names in ROUTES:
        if verb != method:
            continue
        m = pattern.match(path)
        if m:
            return operation, {n: unquote(v) for n, v in zip(names, m.groups())}
    return None


def is_rest(path: str) -> bool:
    return path.startswith("/v2/email/") or path.startswith("/v1/email/")


def handle(method: str, path: str, query: str, body: bytes, ctx: Dict[str, Any]) -> Tuple[int, Any]:
    found = match(method, path)
    if found is None:
        raise ApiError("NotFoundException", f"No SES v2 operation answers {method} {path}.", 404)
    operation, path_params = found
    params: Dict[str, Any] = {}
    for key, value in parse_qsl(query, keep_blank_values=True):
        if key in _LISTS:
            params.setdefault(_LISTS[key], []).append(value)
        else:
            params[key] = value
    if body.strip():
        try:
            data = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError("BadRequestException", "The request body is not valid JSON.") from None
        if not isinstance(data, dict):
            raise ApiError("BadRequestException", "The request body must be a JSON object.")
        params.update(data)
    params.update(path_params)
    return 200, run(operation, params, ctx)
