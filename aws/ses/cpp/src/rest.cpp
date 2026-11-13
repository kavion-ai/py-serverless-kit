#include "rest.hpp"

#include <vector>

#include "errors.hpp"
#include "util.hpp"

namespace ses {

namespace {

struct Route {
  const char* method;
  const char* path;
  const char* operation;
};

const Route ROUTES[] = {
    {"POST", "/v2/email/outbound-emails", "SendEmail"},
    {"POST", "/v2/email/outbound-bulk-emails", "SendBulkEmail"},
    {"GET", "/v2/email/account", "GetAccount"},
    {"PUT", "/v2/email/account/sending", "PutAccountSendingAttributes"},
    {"PUT", "/v2/email/account/suppression", "PutAccountSuppressionAttributes"},
    {"POST", "/v2/email/identities", "CreateEmailIdentity"},
    {"GET", "/v2/email/identities", "ListEmailIdentities"},
    {"POST", "/v2/email/list-identities", "ListEmailIdentities"},
    {"GET", "/v2/email/identities/{EmailIdentity}", "GetEmailIdentity"},
    {"DELETE", "/v2/email/identities/{EmailIdentity}", "DeleteEmailIdentity"},
    {"PUT", "/v2/email/identities/{EmailIdentity}/dkim", "PutEmailIdentityDkimAttributes"},
    {"PUT", "/v2/email/identities/{EmailIdentity}/dkim/signing", "PutEmailIdentityDkimSigningAttributes"},
    {"PUT", "/v1/email/identities/{EmailIdentity}/dkim/signing", "PutEmailIdentityDkimSigningAttributes"},
    {"PUT", "/v2/email/identities/{EmailIdentity}/mail-from", "PutEmailIdentityMailFromAttributes"},
    {"PUT", "/v2/email/identities/{EmailIdentity}/feedback", "PutEmailIdentityFeedbackAttributes"},
    {"PUT", "/v2/email/identities/{EmailIdentity}/configuration-set", "PutEmailIdentityConfigurationSetAttributes"},
    {"POST", "/v2/email/templates", "CreateEmailTemplate"},
    {"GET", "/v2/email/templates", "ListEmailTemplates"},
    {"GET", "/v2/email/templates/{TemplateName}", "GetEmailTemplate"},
    {"PUT", "/v2/email/templates/{TemplateName}", "UpdateEmailTemplate"},
    {"DELETE", "/v2/email/templates/{TemplateName}", "DeleteEmailTemplate"},
    {"POST", "/v2/email/templates/{TemplateName}/render", "TestRenderEmailTemplate"},
    {"POST", "/v2/email/configuration-sets", "CreateConfigurationSet"},
    {"GET", "/v2/email/configuration-sets", "ListConfigurationSets"},
    {"POST", "/v2/email/list-configuration-sets", "ListConfigurationSets"},
    {"GET", "/v2/email/configuration-sets/{ConfigurationSetName}", "GetConfigurationSet"},
    {"DELETE", "/v2/email/configuration-sets/{ConfigurationSetName}", "DeleteConfigurationSet"},
    {"PUT", "/v2/email/configuration-sets/{ConfigurationSetName}/sending", "PutConfigurationSetSendingOptions"},
    {"PUT", "/v2/email/configuration-sets/{ConfigurationSetName}/suppression-options",
     "PutConfigurationSetSuppressionOptions"},
    {"PUT", "/v2/email/configuration-sets/{ConfigurationSetName}/delivery-options",
     "PutConfigurationSetDeliveryOptions"},
    {"PUT", "/v2/email/configuration-sets/{ConfigurationSetName}/reputation-options",
     "PutConfigurationSetReputationOptions"},
    {"PUT", "/v2/email/configuration-sets/{ConfigurationSetName}/tracking-options",
     "PutConfigurationSetTrackingOptions"},
    {"POST", "/v2/email/configuration-sets/{ConfigurationSetName}/event-destinations",
     "CreateConfigurationSetEventDestination"},
    {"GET", "/v2/email/configuration-sets/{ConfigurationSetName}/event-destinations",
     "GetConfigurationSetEventDestinations"},
    {"PUT", "/v2/email/configuration-sets/{ConfigurationSetName}/event-destinations/{EventDestinationName}",
     "UpdateConfigurationSetEventDestination"},
    {"DELETE", "/v2/email/configuration-sets/{ConfigurationSetName}/event-destinations/{EventDestinationName}",
     "DeleteConfigurationSetEventDestination"},
    {"PUT", "/v2/email/suppression/addresses", "PutSuppressedDestination"},
    {"GET", "/v2/email/suppression/addresses", "ListSuppressedDestinations"},
    {"GET", "/v2/email/suppression/addresses/{EmailAddress}", "GetSuppressedDestination"},
    {"DELETE", "/v2/email/suppression/addresses/{EmailAddress}", "DeleteSuppressedDestination"},
    {"POST", "/v2/email/tags", "TagResource"},
    {"GET", "/v2/email/tags", "ListTagsForResource"},
    {"DELETE", "/v2/email/tags", "UntagResource"},
};

bool match(const std::string& method, const std::string& path_in, std::string& operation, Json& path_params) {
  std::string path = path_in;
  if (path.size() > 1 && path.back() == '/') path.pop_back();
  std::vector<std::string> segs = split(path, '/');
  for (const Route& r : ROUTES) {
    if (method != r.method) continue;
    std::vector<std::string> pat = split(r.path, '/');
    if (pat.size() != segs.size()) continue;
    bool ok = true;
    Json params = Json::object();
    for (size_t i = 0; i < pat.size() && ok; ++i) {
      if (!pat[i].empty() && pat[i][0] == '{') {
        if (segs[i].empty()) ok = false;
        else params[pat[i].substr(1, pat[i].size() - 2)] = unquote(segs[i]);
      } else if (pat[i] != segs[i]) {
        ok = false;
      }
    }
    if (ok) {
      operation = r.operation;
      path_params = params;
      return true;
    }
  }
  return false;
}

}  // namespace

bool is_rest(const std::string& path) { return starts_with(path, "/v2/email/") || starts_with(path, "/v1/email/"); }

Json rest_handle(const std::string& method, const std::string& path, const std::string& query, const std::string& body,
                 const Ctx& ctx) {
  std::string operation;
  Json path_params;
  if (!match(method, path, operation, path_params))
    throw ApiError("NotFoundException", "No SES v2 operation answers " + method + " " + path + ".", 404);
  Json params = Json::object();
  for (auto& kv : parse_qsl(query)) {
    std::string list = kv.first == "Reason" ? "Reasons" : (kv.first == "TagKeys" ? "TagKeys" : "");
    if (!list.empty()) {
      Json& l = params[list];
      if (!l.is_arr()) l = Json::array();
      l.push(kv.second);
    } else {
      params[kv.first] = kv.second;
    }
  }
  if (!strip(body, " \t\r\n\f\v").empty()) {
    Json data;
    if (!valid_utf8(body)) throw bad_request("The request body is not valid JSON.");
    try {
      data = parse_json(body);
    } catch (const JsonError&) {
      throw bad_request("The request body is not valid JSON.");
    }
    if (!data.is_obj()) throw bad_request("The request body must be a JSON object.");
    for (auto& kv : data.items()) params[kv.first] = kv.second;
  }
  for (auto& kv : path_params.items()) params[kv.first] = kv.second;
  return run(operation, params, ctx);
}

}  // namespace ses
