#include "operations.hpp"

#include <algorithm>
#include <cmath>
#include <ctime>
#include <functional>
#include <map>
#include <set>
#include <stdexcept>

#include "config.hpp"
#include "errors.hpp"
#include "identities.hpp"
#include "mime.hpp"
#include "sender.hpp"
#include "delivery.hpp"
#include "settings.hpp"
#include "sigv4.hpp"
#include "store.hpp"
#include "templates.hpp"
#include "util.hpp"

namespace ses {

namespace {

using Op = std::function<Json(Json&, const Ctx&)>;
std::map<std::string, Op> build_ops();
std::map<std::string, Op>& ops() {
  static std::map<std::string, Op> table = build_ops();  // thread-safe initialization
  return table;
}

Store& S() { return db(); }
void save() { S().save(); }

std::string str_or(const Json& v, const std::string& def = "") { return truthy(v) ? py_str(v) : def; }

std::string req_str(const Json& params, const std::string& name, bool required = true) {
  const Json& v = params.get(name);
  if (v.is_null() || (v.is_str() && v.s().empty())) {
    if (required) throw bad_request(name + " is required.");
    return "";
  }
  return py_str(v);
}

// int(value) as Python does it; false for a value int() refuses
bool py_int(const Json& v, long long& out) {
  if (v.is_int()) {
    out = v.i();
    return !v.big();
  }
  if (v.is_float()) {
    if (!std::isfinite(v.d())) return false;
    out = static_cast<long long>(v.d());
    return true;
  }
  if (v.is_bool()) {
    out = v.b() ? 1 : 0;
    return true;
  }
  if (v.is_str()) return parse_py_int(v.s(), out);
  return false;
}

Json tags_in(const Json& tags) {
  Json out = Json::array();
  if (!tags.is_arr()) return out;
  for (const Json& tag : tags.arr()) {
    std::string key = str_or(tag.get("Key")), value = str_or(tag.get("Value"));
    if (key.empty() || utf8_len(key) > 128 || utf8_len(value) > 256)
      throw bad_request("Tag keys are 1 to 128 characters, values up to 256.");
    Json t = Json::object();
    t["Key"] = key;
    t["Value"] = value;
    out.push(t);
  }
  return out;
}

Json& identity(const Json& name) {
  std::string key = normalize_identity(name);
  auto it = S().identities.find(key);
  if (it == S().identities.end()) throw not_found("Email identity <" + key + "> does not exist.", "NotFound");
  return it->second;
}

Json& template_rec(const Json& params) {
  std::string name = str_or(params.get("TemplateName"));
  if (name.empty() && truthy(params.get("TemplateArn"))) {
    std::string arn_ = py_str(params.get("TemplateArn"));
    name = arn_.substr(arn_.rfind('/') == std::string::npos ? 0 : arn_.rfind('/') + 1);
  }
  auto it = S().templates.find(name);
  if (it == S().templates.end()) throw not_found("Template " + name + " does not exist.", "TemplateDoesNotExist");
  return it->second;
}

Json& config_set(const Json& name) {
  std::string n = str_or(name);
  auto it = S().configuration_sets.find(n);
  if (it == S().configuration_sets.end())
    throw not_found("Configuration set <" + py_str(name) + "> does not exist.", "ConfigurationSetDoesNotExist");
  return it->second;
}

Json& resource(const Json& arn_value) {
  std::string text = str_or(arn_value);
  std::vector<std::string> parts;
  {
    size_t start = 0;
    for (int k = 0; k < 5; ++k) {
      size_t at = text.find(':', start);
      if (at == std::string::npos) break;
      parts.push_back(text.substr(start, at - start));
      start = at + 1;
    }
    parts.push_back(text.substr(start));
  }
  if (parts.size() != 6 || parts[2] != "ses" || parts[5].find('/') == std::string::npos)
    throw bad_request("Invalid resource ARN " + py_repr_str(text) + ".");
  std::string kind = parts[5].substr(0, parts[5].find('/'));
  std::string name = parts[5].substr(parts[5].find('/') + 1);
  std::map<std::string, Json>* table = nullptr;
  if (kind == "identity") table = &S().identities;
  else if (kind == "template") table = &S().templates;
  else if (kind == "configuration-set") table = &S().configuration_sets;
  if (!table || !table->count(name)) throw not_found("Resource " + text + " does not exist.");
  return (*table)[name];
}

Json obj() { return Json::object(); }

// ----------------------------------------------------------------------------- account

Json reasons_of(const Json& value) {
  std::set<std::string> out;
  if (value.is_arr()) {
    for (auto& r : value.arr()) {
      std::string s = py_str(r);
      if (s != "BOUNCE" && s != "COMPLAINT") throw bad_request("SuppressedReasons may only contain BOUNCE and COMPLAINT.");
      out.insert(s);
    }
  } else if (truthy(value)) {
    for (auto& r : py_str(value)) {
      std::string s(1, r);
      if (s != "BOUNCE" && s != "COMPLAINT") throw bad_request("SuppressedReasons may only contain BOUNCE and COMPLAINT.");
    }
  }
  return Json(std::vector<std::string>(out.begin(), out.end()));
}

// ----------------------------------------------------------------------------- identities

Json mail_from_out(const Json& rec) {
  const Json& mf = rec.get("MailFrom");
  Json out = obj();
  out["MailFromDomain"] = mf.has("MailFromDomain") ? mf.get("MailFromDomain") : Json("");
  out["MailFromDomainStatus"] = mf.has("MailFromDomainStatus")
                                    ? mf.get("MailFromDomainStatus")
                                    : Json(truthy(mf.get("MailFromDomain")) ? "PENDING" : "FAILED");
  out["BehaviorOnMxFailure"] = mf.has("BehaviorOnMxFailure") ? mf.get("BehaviorOnMxFailure") : Json("USE_DEFAULT_VALUE");
  return out;
}

Json identity_out(const Json& rec) {
  std::string status = status_of(rec);
  Json out = obj();
  out["IdentityType"] = rec.get("IdentityType");
  out["FeedbackForwardingStatus"] = rec.has("FeedbackForwardingStatus") ? truthy(rec.get("FeedbackForwardingStatus")) : true;
  out["VerifiedForSendingStatus"] = status == "SUCCESS";
  out["DkimAttributes"] = dkim_out(rec);
  out["MailFromAttributes"] = mail_from_out(rec);
  out["Policies"] = rec.get("Policies").is_obj() ? rec.get("Policies") : obj();
  out["Tags"] = rec.get("Tags").is_arr() ? rec.get("Tags") : Json::array();
  out["VerificationStatus"] = status;
  out["VerificationInfo"] = rec.get("VerificationInfo").is_obj() ? rec.get("VerificationInfo") : obj();
  if (truthy(rec.get("ConfigurationSetName"))) out["ConfigurationSetName"] = rec.get("ConfigurationSetName");
  return out;
}

// ----------------------------------------------------------------------------- templates

Json template_content(const Json& params) {
  const Json& content = params.get("TemplateContent");
  Json out = obj();
  out["Subject"] = str_or(content.get("Subject"));
  out["Text"] = str_or(content.get("Text"));
  out["Html"] = str_or(content.get("Html"));
  if (out.get("Subject").s().empty() && out.get("Text").s().empty() && out.get("Html").s().empty())
    throw bad_request("A template needs a subject, a text part or an HTML part.");
  check_templates(out.get("Subject").s(), out.get("Text").s(), out.get("Html").s());
  return out;
}

Json template_out(const Json& rec) {
  Json out = obj();
  out["TemplateName"] = rec.get("TemplateName");
  Json content = obj();
  content["Subject"] = rec.has("Subject") ? rec.get("Subject") : Json("");
  content["Text"] = rec.has("Text") ? rec.get("Text") : Json("");
  content["Html"] = rec.has("Html") ? rec.get("Html") : Json("");
  out["TemplateContent"] = content;
  out["Tags"] = rec.get("Tags").is_arr() ? rec.get("Tags") : Json::array();
  return out;
}

struct Rendered {
  std::string subject;
  bool has_text = false, has_html = false;
  std::string text, html;
};

Rendered render(const Json& content, const Json& data) {
  Rendered r;
  r.subject = render_template(str_or(content.get("Subject")), data);
  if (truthy(content.get("Text"))) {
    r.has_text = true;
    r.text = render_template(py_str(content.get("Text")), data);
  }
  if (truthy(content.get("Html"))) {
    r.has_html = true;
    r.html = render_template(py_str(content.get("Html")), data, true);
  }
  if (!r.has_text && !r.has_html) r.has_text = true;
  return r;
}

// ----------------------------------------------------------------------------- configuration sets

Json cs_out(const Json& rec) {
  Json out = obj();
  out["ConfigurationSetName"] = rec.get("Name");
  Json delivery = obj();
  delivery["TlsPolicy"] = rec.has("TlsPolicy") ? rec.get("TlsPolicy") : Json("OPTIONAL");
  if (truthy(rec.get("MaxDeliverySeconds"))) delivery["MaxDeliverySeconds"] = rec.get("MaxDeliverySeconds");
  out["DeliveryOptions"] = delivery;
  Json rep = obj();
  rep["ReputationMetricsEnabled"] = truthy(rec.get("ReputationMetricsEnabled"));
  out["ReputationOptions"] = rep;
  Json sending = obj();
  sending["SendingEnabled"] = rec.has("SendingEnabled") ? truthy(rec.get("SendingEnabled")) : true;
  out["SendingOptions"] = sending;
  out["Tags"] = rec.get("Tags").is_arr() ? rec.get("Tags") : Json::array();
  if (!rec.get("SuppressedReasons").is_null()) {
    Json supp = obj();
    supp["SuppressedReasons"] = rec.get("SuppressedReasons");
    out["SuppressionOptions"] = supp;
  }
  if (truthy(rec.get("TrackingOptions"))) out["TrackingOptions"] = rec.get("TrackingOptions");
  return out;
}

void delivery_options(Json& rec, const Json& opts) {
  std::string policy = str_or(opts.get("TlsPolicy"), str_or(rec.get("TlsPolicy"), "OPTIONAL"));
  if (policy != "REQUIRE" && policy != "OPTIONAL") throw bad_request("TlsPolicy must be REQUIRE or OPTIONAL.");
  rec["TlsPolicy"] = policy;
  if (!opts.get("MaxDeliverySeconds").is_null()) {
    long long seconds;
    if (!py_int(opts.get("MaxDeliverySeconds"), seconds)) throw std::runtime_error("invalid MaxDeliverySeconds");
    if (seconds < 300 || seconds > 50400) throw bad_request("MaxDeliverySeconds must be between 300 and 50400.");
    rec["MaxDeliverySeconds"] = seconds;
  }
}

const char* const EVENT_TYPES[] = {"SEND",  "REJECT", "BOUNCE",            "COMPLAINT",      "DELIVERY",
                                   "OPEN",  "CLICK",  "RENDERING_FAILURE", "DELIVERY_DELAY", "SUBSCRIPTION"};

Json event_destination(const std::string& name, const Json& def) {
  std::vector<std::string> types;
  if (def.get("MatchingEventTypes").is_arr())
    for (auto& t : def.get("MatchingEventTypes").arr()) types.push_back(py_str(t));
  bool ok = !types.empty();
  for (auto& t : types)
    if (std::find_if(std::begin(EVENT_TYPES), std::end(EVENT_TYPES), [&](const char* e) { return t == e; }) ==
        std::end(EVENT_TYPES))
      ok = false;
  if (!ok)
    throw bad_request("MatchingEventTypes must list some of " +
                      join(std::vector<std::string>(std::begin(EVENT_TYPES), std::end(EVENT_TYPES)), ", ") + ".");
  Json out = obj();
  out["Name"] = name;
  out["Enabled"] = truthy(def.get("Enabled"));
  out["MatchingEventTypes"] = Json(types);
  for (const char* key : {"SnsDestination", "EventBridgeDestination", "CloudWatchDestination",
                          "KinesisFirehoseDestination", "PinpointDestination"})
    if (truthy(def.get(key))) out[key] = def.get(key);
  return out;
}

// ----------------------------------------------------------------------------- suppression

Json suppressed_out(const Json& rec, bool full) {
  Json out = obj();
  out["EmailAddress"] = rec.get("EmailAddress");
  out["Reason"] = rec.get("Reason");
  out["LastUpdateTime"] = rec.get("LastUpdateTime");
  if (full) {
    Json attrs = obj();
    for (const char* k : {"MessageId", "FeedbackId"})
      if (truthy(rec.get(k))) attrs[k] = rec.get(k);
    out["Attributes"] = attrs;
  }
  return out;
}

bool parse_iso(const std::string& text, double& out) {
  std::string s = replace_all(strip(text), "Z", "+00:00");
  int Y, M, D, h = 0, m = 0;
  double sec = 0;
  if (s.size() < 10 || std::sscanf(s.c_str(), "%4d-%2d-%2d", &Y, &M, &D) != 3 || s[4] != '-' || s[7] != '-') return false;
  size_t pos = 10;
  int offset = 0;
  if (pos < s.size()) {
    if (s[pos] != 'T' && s[pos] != ' ') return false;
    ++pos;
    if (std::sscanf(s.c_str() + pos, "%2d:%2d", &h, &m) != 2) return false;
    pos += 5;
    if (pos < s.size() && s[pos] == ':') {
      char* end = nullptr;
      sec = std::strtod(s.c_str() + pos + 1, &end);
      pos = static_cast<size_t>(end - s.c_str());
    }
    if (pos < s.size()) {
      char sign = s[pos];
      int oh = 0, om = 0;
      if ((sign != '+' && sign != '-') || std::sscanf(s.c_str() + pos + 1, "%2d:%2d", &oh, &om) != 2) return false;
      offset = (oh * 3600 + om * 60) * (sign == '-' ? -1 : 1);
    }
  }
  struct tm tm = {};
  tm.tm_year = Y - 1900;
  tm.tm_mon = M - 1;
  tm.tm_mday = D;
  tm.tm_hour = h;
  tm.tm_min = m;
  out = static_cast<double>(timegm(&tm)) + sec - offset;
  return true;
}

bool when(const Json& value, double& out) {
  if (value.is_null() || (value.is_str() && value.s().empty())) return false;
  if (value.is_number() || value.is_bool()) {
    out = value.num();
    return true;
  }
  std::string s = py_str(value);
  if (parse_py_float(s, out)) return true;
  if (parse_iso(s, out)) return true;
  throw bad_request("Invalid date " + py_repr_str(s) + ".");
}

// ----------------------------------------------------------------------------- sending

void destination(const Json& params, std::vector<std::string>& to, std::vector<std::string>& cc,
                 std::vector<std::string>& bcc) {
  const Json& dest = params.get("Destination");
  to = addresses(dest.get("ToAddresses"));
  cc = addresses(dest.get("CcAddresses"));
  bcc = addresses(dest.get("BccAddresses"));
}

Rendered template_parts(const Json& tpl, const Json& data) {
  if (truthy(tpl.get("TemplateContent"))) {
    Json content = obj();
    if (tpl.get("TemplateContent").is_obj())
      for (auto& kv : tpl.get("TemplateContent").items()) content[kv.first] = str_or(kv.second);
    check_templates(str_or(content.get("Subject")), str_or(content.get("Text")), str_or(content.get("Html")));
    return render(content, data);
  }
  return render(template_rec(tpl), data);
}

std::string bulk_status(const ApiError& e) {
  if (e.v1 == "ConfigurationSetDoesNotExist") return "CONFIGURATION_SET_NOT_FOUND";
  if (e.v1 == "TemplateDoesNotExist") return "TEMPLATE_NOT_FOUND";
  if (e.v1 == "ConfigurationSetSendingPausedException") return "CONFIGURATION_SET_SENDING_PAUSED";
  static const std::map<std::string, std::string> m = {
      {"MessageRejected", "MESSAGE_REJECTED"},
      {"MailFromDomainNotVerifiedException", "MAIL_FROM_DOMAIN_NOT_VERIFIED"},
      {"TooManyRequestsException", "ACCOUNT_THROTTLED"},
      {"LimitExceededException", "ACCOUNT_DAILY_QUOTA_EXCEEDED"},
      {"SendingPausedException", "ACCOUNT_SENDING_PAUSED"},
      {"BadRequestException", "INVALID_PARAMETER"}};
  auto it = m.find(e.code);
  return it == m.end() ? "FAILED" : it->second;
}

Json message_summary(const Json& rec) {
  Json out = obj();
  for (const char* k : {"MessageId", "Timestamp", "Source", "From", "Destinations", "Subject", "Status", "Operation",
                        "ConfigurationSetName", "Size", "DkimDomain", "Caller"})
    out[k] = rec.get(k);
  return out;
}

Json& message(const Json& params) {
  auto it = S().messages.find(str_or(params.get("MessageId")));
  if (it == S().messages.end()) throw not_found("Message not found (it may be older than the retention period).");
  return it->second;
}

#define OP(name) static Json op_##name(Json& params, const Ctx& ctx)
#define UNUSED (void)params, (void)ctx

// ----------------------------------------------------------------------------- account ops

OP(GetAccount) {
  UNUSED;
  return account_out(ctx);
}

OP(PutAccountSendingAttributes) {
  UNUSED;
  S().account["SendingEnabled"] = truthy(params.get("SendingEnabled"));
  save();
  return obj();
}

OP(PutAccountSuppressionAttributes) {
  UNUSED;
  S().account["SuppressedReasons"] = reasons_of(params.get("SuppressedReasons"));
  save();
  return obj();
}

// ----------------------------------------------------------------------------- identity ops

OP(CreateEmailIdentity) {
  UNUSED;
  Json rec = create_identity(req_str(params, "EmailIdentity"), params, false);
  Json full = identity_out(rec);
  Json out = obj();
  out["IdentityType"] = full.get("IdentityType");
  out["VerifiedForSendingStatus"] = full.get("VerifiedForSendingStatus");
  out["DkimAttributes"] = full.get("DkimAttributes");
  return out;
}

OP(GetEmailIdentity) {
  UNUSED;
  return identity_out(identity(req_str(params, "EmailIdentity")));
}

OP(ListEmailIdentities) {
  UNUSED;
  std::vector<Json> items;
  for (auto& kv : S().identities) {
    std::string status = status_of(kv.second);
    Json item = obj();
    item["IdentityType"] = kv.second.get("IdentityType");
    item["IdentityName"] = kv.second.get("IdentityName");
    item["SendingEnabled"] = status == "SUCCESS";
    item["VerificationStatus"] = status;
    items.push_back(item);
  }
  auto pg = page(items, params);
  Json out = obj();
  out["EmailIdentities"] = Json::array();
  for (auto& i : pg.first) out["EmailIdentities"].push(i);
  if (!pg.second.empty()) out["NextToken"] = pg.second;
  return out;
}

OP(DeleteEmailIdentity) {
  UNUSED;
  Json& rec = identity(req_str(params, "EmailIdentity"));
  S().identities.erase(py_str(rec.get("IdentityName")));
  save();
  return obj();
}

OP(PutEmailIdentityDkimAttributes) {
  UNUSED;
  Json& rec = identity(req_str(params, "EmailIdentity"));
  bool enabled = truthy(params.get("SigningEnabled"));
  if (truthy(rec.get("Dkim"))) {
    rec["Dkim"]["SigningEnabled"] = enabled;
  } else if (enabled && py_str(rec.get("IdentityType")) == "EMAIL_ADDRESS") {
    throw bad_request("Enable DKIM on the address's domain identity: the domain's key signs its mail.");
  }
  save();
  return obj();
}

OP(PutEmailIdentityDkimSigningAttributes) {
  UNUSED;
  Json& rec = identity(req_str(params, "EmailIdentity"));
  if (py_str(rec.get("IdentityType")) != "DOMAIN") throw bad_request("DKIM signing attributes apply to domain identities.");
  Json attrs = params.get("SigningAttributes").is_obj() ? params.get("SigningAttributes") : obj();
  attrs["DomainSigningAttributesOrigin"] =
      truthy(params.get("SigningAttributesOrigin"))
          ? params.get("SigningAttributesOrigin")
          : (truthy(attrs.get("DomainSigningAttributesOrigin")) ? attrs.get("DomainSigningAttributesOrigin")
                                                                : Json("AWS_SES"));
  Json fresh = obj();
  fresh["IdentityName"] = rec.get("IdentityName");
  set_dkim(fresh, attrs);
  rec["Dkim"] = fresh.get("Dkim");
  save();
  check_later(py_str(rec.get("IdentityName")));
  Json out = obj();
  out["DkimStatus"] = rec.get("Dkim").get("Status");
  out["DkimTokens"] = Json(std::vector<std::string>{py_str(rec.get("Dkim").get("Selector"))});
  return out;
}

OP(PutEmailIdentityMailFromAttributes) {
  UNUSED;
  Json& rec = identity(req_str(params, "EmailIdentity"));
  std::string domain = rstrip(lower(str_or(params.get("MailFromDomain"))), ".");
  std::string behavior = str_or(params.get("BehaviorOnMxFailure"), "USE_DEFAULT_VALUE");
  if (behavior != "USE_DEFAULT_VALUE" && behavior != "REJECT_MESSAGE")
    throw bad_request("BehaviorOnMxFailure must be USE_DEFAULT_VALUE or REJECT_MESSAGE.");
  if (domain.empty()) {
    rec.erase("MailFrom");
  } else {
    std::string name = py_str(rec.get("IdentityName"));
    std::string parent = name.substr(name.rfind('@') == std::string::npos ? 0 : name.rfind('@') + 1);
    if (!ends_with(domain, "." + parent)) throw bad_request("The MAIL FROM domain must be a subdomain of " + parent + ".");
    Json mf = obj();
    mf["MailFromDomain"] = domain;
    mf["BehaviorOnMxFailure"] = behavior;
    mf["MailFromDomainStatus"] = (cfg.verify == "auto" || cfg.verify == "off") ? "SUCCESS" : "PENDING";
    rec["MailFrom"] = mf;
  }
  save();
  return obj();
}

OP(PutEmailIdentityFeedbackAttributes) {
  UNUSED;
  Json& rec = identity(req_str(params, "EmailIdentity"));
  rec["FeedbackForwardingStatus"] = truthy(params.get("EmailForwardingEnabled"));
  save();
  return obj();
}

OP(PutEmailIdentityConfigurationSetAttributes) {
  UNUSED;
  Json& rec = identity(req_str(params, "EmailIdentity"));
  std::string name = str_or(params.get("ConfigurationSetName"));
  if (!name.empty()) config_set(name);
  if (!name.empty()) rec["ConfigurationSetName"] = name;
  else rec.erase("ConfigurationSetName");
  save();
  return obj();
}

// ----------------------------------------------------------------------------- template ops

OP(CreateEmailTemplate) {
  UNUSED;
  std::string name = req_str(params, "TemplateName");
  if (!name_re(name)) throw bad_request("TemplateName may contain only letters, digits, '_' and '-' (up to 64).");
  Json content = template_content(params);
  if (S().templates.count(name)) throw exists("Template " + name + " already exists.");
  Json rec = obj();
  rec["TemplateName"] = name;
  for (auto& kv : content.items()) rec[kv.first] = kv.second;
  rec["CreatedTimestamp"] = now();
  rec["Tags"] = tags_in(params.get("Tags"));
  S().templates[name] = rec;
  save();
  return obj();
}

OP(GetEmailTemplate) {
  UNUSED;
  return template_out(template_rec(params));
}

OP(UpdateEmailTemplate) {
  UNUSED;
  Json& rec = template_rec(params);
  Json content = template_content(params);
  for (auto& kv : content.items()) rec[kv.first] = kv.second;
  rec["UpdatedTimestamp"] = now();
  save();
  return obj();
}

OP(DeleteEmailTemplate) {
  UNUSED;
  Json& rec = template_rec(params);
  S().templates.erase(py_str(rec.get("TemplateName")));
  save();
  return obj();
}

OP(ListEmailTemplates) {
  UNUSED;
  std::vector<Json> items;
  for (auto& kv : S().templates) {
    Json item = obj();
    item["TemplateName"] = kv.first;
    item["CreatedTimestamp"] = kv.second.get("CreatedTimestamp");
    items.push_back(item);
  }
  auto pg = page(items, params, 10, 100);
  Json out = obj();
  out["TemplatesMetadata"] = Json::array();
  for (auto& i : pg.first) out["TemplatesMetadata"].push(i);
  if (!pg.second.empty()) out["NextToken"] = pg.second;
  return out;
}

OP(TestRenderEmailTemplate) {
  UNUSED;
  Json& rec = template_rec(params);
  Rendered r = render(rec, template_data_of(params.get("TemplateData")));
  BuildArgs a;
  a.source = "sender@example.com";
  a.subject = r.subject;
  a.has_text = r.has_text;
  a.text = r.text;
  a.has_html = r.has_html;
  a.html = r.html;
  Json out = obj();
  out["RenderedTemplate"] = sanitize_utf8(mime_build(a));
  return out;
}

// ----------------------------------------------------------------------------- configuration set ops

OP(CreateConfigurationSet) {
  UNUSED;
  std::string name = req_str(params, "ConfigurationSetName");
  if (!name_re(name))
    throw bad_request("ConfigurationSetName may contain only letters, digits, '_' and '-' (up to 64).");
  Json rec = obj();
  rec["Name"] = name;
  rec["CreatedTimestamp"] = now();
  rec["SendingEnabled"] = true;
  rec["EventDestinations"] = obj();
  rec["Tags"] = tags_in(params.get("Tags"));
  delivery_options(rec, params.get("DeliveryOptions").is_obj() ? params.get("DeliveryOptions") : obj());
  if (!params.get("SendingOptions").is_null()) {
    const Json& so = params.get("SendingOptions");
    rec["SendingEnabled"] = so.has("SendingEnabled") ? truthy(so.get("SendingEnabled")) : true;
  }
  if (!params.get("SuppressionOptions").is_null())
    rec["SuppressedReasons"] = reasons_of(params.get("SuppressionOptions").get("SuppressedReasons"));
  if (truthy(params.get("TrackingOptions"))) rec["TrackingOptions"] = params.get("TrackingOptions");
  if (truthy(params.get("ReputationOptions")))
    rec["ReputationMetricsEnabled"] = truthy(params.get("ReputationOptions").get("ReputationMetricsEnabled"));
  if (S().configuration_sets.count(name))
    throw exists("Configuration set <" + name + "> already exists.", "ConfigurationSetAlreadyExists");
  S().configuration_sets[name] = rec;
  save();
  return obj();
}

OP(GetConfigurationSet) {
  UNUSED;
  return cs_out(config_set(params.get("ConfigurationSetName")));
}

OP(ListConfigurationSets) {
  UNUSED;
  std::vector<Json> names;
  for (auto& kv : S().configuration_sets) names.push_back(Json(kv.first));
  auto pg = page(names, params);
  Json out = obj();
  out["ConfigurationSets"] = Json::array();
  for (auto& n : pg.first) out["ConfigurationSets"].push(n);
  if (!pg.second.empty()) out["NextToken"] = pg.second;
  return out;
}

OP(DeleteConfigurationSet) {
  UNUSED;
  Json& rec = config_set(params.get("ConfigurationSetName"));
  S().configuration_sets.erase(py_str(rec.get("Name")));
  save();
  return obj();
}

OP(PutConfigurationSetSendingOptions) {
  UNUSED;
  Json& rec = config_set(params.get("ConfigurationSetName"));
  rec["SendingEnabled"] = truthy(params.get("SendingEnabled"));
  save();
  return obj();
}

OP(PutConfigurationSetSuppressionOptions) {
  UNUSED;
  Json& rec = config_set(params.get("ConfigurationSetName"));
  if (params.get("SuppressedReasons").is_null()) rec.erase("SuppressedReasons");
  else rec["SuppressedReasons"] = reasons_of(params.get("SuppressedReasons"));
  save();
  return obj();
}

OP(PutConfigurationSetDeliveryOptions) {
  UNUSED;
  Json& rec = config_set(params.get("ConfigurationSetName"));
  delivery_options(rec, params);
  save();
  return obj();
}

OP(PutConfigurationSetReputationOptions) {
  UNUSED;
  Json& rec = config_set(params.get("ConfigurationSetName"));
  rec["ReputationMetricsEnabled"] = truthy(params.get("ReputationMetricsEnabled"));
  save();
  return obj();
}

OP(PutConfigurationSetTrackingOptions) {
  UNUSED;
  Json& rec = config_set(params.get("ConfigurationSetName"));
  Json t = obj();
  for (const char* k : {"CustomRedirectDomain", "HttpsPolicy"})
    if (truthy(params.get(k))) t[k] = params.get(k);
  rec["TrackingOptions"] = t;
  save();
  return obj();
}

OP(CreateConfigurationSetEventDestination) {
  UNUSED;
  Json& rec = config_set(params.get("ConfigurationSetName"));
  std::string name = req_str(params, "EventDestinationName");
  Json dest = event_destination(name, params.get("EventDestination").is_obj() ? params.get("EventDestination") : obj());
  Json& dests = rec["EventDestinations"];
  if (!dests.is_obj()) dests = obj();
  if (dests.has(name)) throw exists("Event destination " + name + " already exists.");
  dests[name] = dest;
  save();
  return obj();
}

OP(UpdateConfigurationSetEventDestination) {
  UNUSED;
  Json& rec = config_set(params.get("ConfigurationSetName"));
  std::string name = req_str(params, "EventDestinationName");
  Json& dests = rec["EventDestinations"];
  if (!dests.is_obj()) dests = obj();
  if (!dests.has(name)) throw not_found("Event destination " + name + " does not exist.");
  dests[name] = event_destination(name, params.get("EventDestination").is_obj() ? params.get("EventDestination") : obj());
  save();
  return obj();
}

OP(GetConfigurationSetEventDestinations) {
  UNUSED;
  Json& rec = config_set(params.get("ConfigurationSetName"));
  std::vector<std::pair<std::string, Json>> items;
  if (rec.get("EventDestinations").is_obj())
    for (auto& kv : rec.get("EventDestinations").items()) items.emplace_back(kv.first, kv.second);
  std::sort(items.begin(), items.end(),
            [](const std::pair<std::string, Json>& a, const std::pair<std::string, Json>& b) { return a.first < b.first; });
  Json out = obj();
  out["EventDestinations"] = Json::array();
  for (auto& kv : items) out["EventDestinations"].push(kv.second);
  return out;
}

OP(DeleteConfigurationSetEventDestination) {
  UNUSED;
  Json& rec = config_set(params.get("ConfigurationSetName"));
  std::string name = req_str(params, "EventDestinationName");
  if (!rec.get("EventDestinations").has(name)) throw not_found("Event destination " + name + " does not exist.");
  rec["EventDestinations"].erase(name);
  save();
  return obj();
}

// ----------------------------------------------------------------------------- suppression ops

OP(PutSuppressedDestination) {
  UNUSED;
  Json list = Json::array();
  list.push(req_str(params, "EmailAddress"));
  std::string addr = addresses(list).at(0);
  std::string reason = req_str(params, "Reason");
  if (reason != "BOUNCE" && reason != "COMPLAINT") throw bad_request("Reason must be BOUNCE or COMPLAINT.");
  Json rec = obj();
  rec["EmailAddress"] = addr;
  rec["Reason"] = reason;
  rec["LastUpdateTime"] = now();
  S().suppressed[lower(addr)] = rec;
  save();
  return obj();
}

OP(GetSuppressedDestination) {
  UNUSED;
  std::string addr = lower(req_str(params, "EmailAddress"));
  auto it = S().suppressed.find(addr);
  if (it == S().suppressed.end()) throw not_found("Email address " + addr + " does not exist on your suppression list.");
  Json out = obj();
  out["SuppressedDestination"] = suppressed_out(it->second, true);
  return out;
}

OP(DeleteSuppressedDestination) {
  UNUSED;
  std::string addr = lower(req_str(params, "EmailAddress"));
  if (!S().suppressed.erase(addr)) throw not_found("Email address " + addr + " does not exist on your suppression list.");
  save();
  return obj();
}

OP(ListSuppressedDestinations) {
  UNUSED;
  Json reasons = truthy(params.get("Reasons")) ? params.get("Reasons")
                                               : (truthy(params.get("Reason")) ? params.get("Reason") : Json::array());
  if (reasons.is_str()) {
    Json l = Json::array();
    l.push(reasons);
    reasons = l;
  }
  double start = 0, end = 0;
  bool has_start = when(params.get("StartDate"), start), has_end = when(params.get("EndDate"), end);
  std::vector<Json> items;
  for (auto& kv : S().suppressed) {
    const Json& r = kv.second;
    bool reason_ok = !truthy(reasons);
    if (reasons.is_arr())
      for (auto& x : reasons.arr())
        if (x == r.get("Reason")) reason_ok = true;
    double t = r.get("LastUpdateTime").num();
    if (reason_ok && (!has_start || t >= start) && (!has_end || t <= end)) items.push_back(suppressed_out(r, false));
  }
  auto pg = page(items, params);
  Json out = obj();
  out["SuppressedDestinationSummaries"] = Json::array();
  for (auto& i : pg.first) out["SuppressedDestinationSummaries"].push(i);
  if (!pg.second.empty()) out["NextToken"] = pg.second;
  return out;
}

// ----------------------------------------------------------------------------- tag ops

OP(TagResource) {
  UNUSED;
  Json& rec = resource(params.get("ResourceArn"));
  Json new_tags = tags_in(params.get("Tags"));
  std::map<std::string, Json> tags;
  if (rec.get("Tags").is_arr())
    for (auto& t : rec.get("Tags").arr()) tags[py_str(t.get("Key"))] = t.get("Value");
  for (auto& t : new_tags.arr()) tags[py_str(t.get("Key"))] = t.get("Value");
  if (tags.size() > 50) throw bad_request("A resource can have up to 50 tags.");
  Json list = Json::array();
  for (auto& kv : tags) {
    Json t = obj();
    t["Key"] = kv.first;
    t["Value"] = kv.second;
    list.push(t);
  }
  rec["Tags"] = list;
  save();
  return obj();
}

OP(UntagResource) {
  UNUSED;
  Json& rec = resource(params.get("ResourceArn"));
  Json keys = truthy(params.get("TagKeys")) ? params.get("TagKeys") : Json::array();
  if (keys.is_str()) {
    Json l = Json::array();
    l.push(keys);
    keys = l;
  }
  Json kept = Json::array();
  if (rec.get("Tags").is_arr())
    for (auto& t : rec.get("Tags").arr()) {
      bool drop = false;
      if (keys.is_arr())
        for (auto& k : keys.arr())
          if (k == t.get("Key")) drop = true;
      if (!drop) kept.push(t);
    }
  rec["Tags"] = kept;
  save();
  return obj();
}

OP(ListTagsForResource) {
  UNUSED;
  Json out = obj();
  const Json& tags = resource(params.get("ResourceArn")).get("Tags");
  out["Tags"] = tags.is_arr() ? tags : Json::array();
  return out;
}

// ----------------------------------------------------------------------------- send ops

OP(SendEmail) {
  std::vector<std::string> to, cc, bcc;
  destination(params, to, cc, bcc);
  Json content = truthy(params.get("Content")) ? params.get("Content") : obj();
  std::string source = str_or(params.get("FromEmailAddress"));
  bool raw = truthy(content.get("Raw"));
  if (source.empty() && !raw) throw bad_request("FromEmailAddress is required.");
  SendArgs a;
  a.operation = "SendEmail";
  a.ctx = ctx;
  a.source = source;
  a.to = to;
  a.cc = cc;
  a.bcc = bcc;
  a.reply_to = addresses(params.get("ReplyToAddresses"));
  a.content = content;
  a.configuration_set = str_or(params.get("ConfigurationSetName"));
  a.tags = params.get("EmailTags");
  a.return_path = str_or(params.get("FeedbackForwardingEmailAddress"));
  if (raw && (!to.empty() || !cc.empty() || !bcc.empty())) {
    a.has_envelope = true;
    a.envelope = to;
    a.envelope.insert(a.envelope.end(), cc.begin(), cc.end());
    a.envelope.insert(a.envelope.end(), bcc.begin(), bcc.end());
  }
  Json out = obj();
  out["MessageId"] = send_message(a);
  return out;
}

OP(SendBulkEmail) {
  std::string source = req_str(params, "FromEmailAddress");
  Json def = params.get("DefaultContent").get("Template");
  if (!def.is_obj()) def = obj();
  const Json& entries = params.get("BulkEmailEntries");
  if (!entries.is_arr() || entries.arr().empty() || entries.arr().size() > 50)
    throw bad_request("BulkEmailEntries must have 1 to 50 entries.");
  if (!truthy(def.get("TemplateContent"))) template_rec(def);
  check_sender(source);
  configuration_set(str_or(params.get("ConfigurationSetName")));
  Json base = template_data_of(truthy(def.get("TemplateData")) ? def.get("TemplateData") : Json("{}"));
  Json results = Json::array();
  for (const Json& entry : entries.arr()) {
    Json result = obj();
    try {
      std::vector<std::string> to, cc, bcc;
      destination(entry, to, cc, bcc);
      const Json& replacement = entry.get("ReplacementEmailContent").get("ReplacementTemplate").get("ReplacementTemplateData");
      Json data = base;
      if (truthy(replacement)) {
        Json extra = template_data_of(replacement);
        for (auto& kv : extra.items()) data[kv.first] = kv.second;
      }
      Json tpl = def;
      tpl["TemplateData"] = data;
      if (truthy(entry.get("ReplacementHeaders"))) tpl["Headers"] = entry.get("ReplacementHeaders");
      Json content = obj();
      content["Template"] = tpl;
      SendArgs a;
      a.operation = "SendBulkEmail";
      a.ctx = ctx;
      a.source = source;
      a.to = to;
      a.cc = cc;
      a.bcc = bcc;
      a.reply_to = addresses(params.get("ReplyToAddresses"));
      a.content = content;
      a.configuration_set = str_or(params.get("ConfigurationSetName"));
      a.tags = truthy(entry.get("ReplacementTags")) ? entry.get("ReplacementTags") : params.get("DefaultEmailTags");
      a.return_path = str_or(params.get("FeedbackForwardingEmailAddress"));
      std::string id = send_message(a);
      result["Status"] = "SUCCESS";
      result["MessageId"] = id;
    } catch (const ApiError& e) {
      result["Status"] = bulk_status(e);
      result["Error"] = e.message;
    }
    results.push(result);
  }
  Json out = obj();
  out["BulkEmailEntryResults"] = results;
  return out;
}

// ----------------------------------------------------------------------------- console ops

OP(ListMessages) {
  UNUSED;
  std::string status = str_or(params.get("Status"));
  std::string text = lower(str_or(params.get("Query")));
  std::vector<const Json*> recs;
  for (auto& kv : S().messages) recs.push_back(&kv.second);
  std::stable_sort(recs.begin(), recs.end(), [](const Json* a, const Json* b) {
    return a->get("Timestamp").num() > b->get("Timestamp").num();
  });
  std::vector<Json> items;
  for (const Json* r : recs) {
    if (!status.empty() && str_or(r->get("Status")) != status) continue;
    if (!text.empty()) {
      std::vector<std::string> dests;
      if (r->get("Destinations").is_arr())
        for (auto& d : r->get("Destinations").arr()) dests.push_back(py_str(d));
      std::string hay = lower(join({py_str(r->get("MessageId")), str_or(r->get("Source")), str_or(r->get("Subject")),
                                    join(dests, " ")},
                                   " "));
      if (hay.find(text) == std::string::npos) continue;
    }
    items.push_back(message_summary(*r));
  }
  auto pg = page(items, params, 50);
  Json out = obj();
  out["Messages"] = Json::array();
  for (auto& i : pg.first) out["Messages"].push(i);
  out["Total"] = static_cast<long long>(items.size());
  if (!pg.second.empty()) out["NextToken"] = pg.second;
  return out;
}

OP(GetMessage) {
  UNUSED;
  Json rec = message(params);
  std::string raw;
  try {
    raw = S().raw(py_str(rec.get("MessageId")));
  } catch (const std::exception&) {
    raw.clear();
  }
  Json out = rec;
  out["Content"] = raw.empty() ? obj() : mime_read(raw);
  if (truthy(params.get("IncludeRaw")))
    out["Raw"] = sanitize_utf8(raw.substr(0, std::min<size_t>(raw.size(), 5 * 1024 * 1024)));
  return out;
}

OP(DeleteMessage) {
  UNUSED;
  Json& rec = message(params);
  S().delete_message(py_str(rec.get("MessageId")));
  return obj();
}

OP(RetryMessage) {
  UNUSED;
  Json& rec = message(params);
  for (auto& kv : rec["Recipients"].items()) {
    std::string s = str_or(kv.second.get("Status"));
    if (s == "QUEUED" || s == "DELAYED") kv.second["NextAttempt"] = now();
  }
  S().save_message(py_str(rec.get("MessageId")));
  wake_worker();
  return obj();
}

OP(SetEmailIdentityVerified) {
  UNUSED;
  Json& rec = identity(req_str(params, "EmailIdentity"));
  bool value = params.has("Verified") ? truthy(params.get("Verified")) : true;
  return identity_out(set_verified(py_str(rec.get("IdentityName")), value));
}

OP(GetEmailIdentityDnsRecords) {
  UNUSED;
  Json out = obj();
  out["Records"] = dns_records(identity(req_str(params, "EmailIdentity")));
  return out;
}

// After a mode change, try waiting recipients again now instead of at their next retry time.
void retry_waiting() {
  for (auto& kv : S().messages) {
    Json& rec = kv.second;
    std::string status = str_or(rec.get("Status"));
    if (status != "QUEUED" && status != "DELAYED") continue;
    bool changed = false;
    for (auto& r : rec["Recipients"].items()) {
      std::string st = str_or(r.second.get("Status"));
      if (st == "QUEUED" || st == "DELAYED") {
        r.second["NextAttempt"] = now();
        changed = true;
      }
    }
    if (changed) S().save_message(kv.first);
  }
  wake_worker();
}

OP(GetDeliverySettings) {
  UNUSED;
  Json out = delivery_public(delivery_effective());
  out["DirectPort"] = cfg.direct_port;
  out["Environment"] = delivery_public(delivery_environment());
  return out;
}

OP(PutDeliverySettings) {
  Json values = delivery_check(params);
  delivery_save(values);
  retry_waiting();
  Json none = obj();
  return op_GetDeliverySettings(none, ctx);
}

OP(ResetDeliverySettings) {
  UNUSED;
  delivery_save(obj());
  retry_waiting();
  Json none = obj();
  return op_GetDeliverySettings(none, ctx);
}

// Runs without the store lock: it may wait on the network for a while.
Json test_delivery_settings(Json& params, const Ctx&) {
  Json conf = delivery_effective();
  if (truthy(params.get("Mode"))) {
    Json checked = delivery_check(params);
    for (auto& kv : checked.items()) conf[kv.first] = kv.second;
  }
  std::string domain = lower(strip(str_or(params.get("TestDomain"), "gmail.com")));
  if (!is_domain(domain)) throw bad_request("TestDomain must be a domain name.");
  return test_connection(conf, domain);
}

OP(GetServerInfo) {
  UNUSED;
  Json out = obj();
  out["Version"] = VERSION;
  out["Implementation"] = "C++";
  out["Region"] = cfg.region;
  out["AccountId"] = cfg.account;
  Json conf = delivery_effective();
  out["Delivery"] = conf.get("Mode");
  out["DeliverySource"] = conf.get("Source");
  if (py_str(conf.get("Mode")) == "relay") {
    Json relay = obj();
    relay["Host"] = conf.get("RelayHost");
    relay["Port"] = conf.get("RelayPort");
    relay["Tls"] = conf.get("RelayTls");
    relay["User"] = conf.get("RelayUser");
    out["Relay"] = relay;
  } else {
    out["Relay"] = Json();
  }
  out["DirectPort"] = cfg.direct_port;
  out["HeloName"] = conf.get("HeloName");
  out["Verify"] = cfg.verify;
  out["Sandbox"] = cfg.sandbox;
  out["DkimCheck"] = cfg.dkim_check;
  out["EventsWebhook"] = !cfg.events_url.empty();
  out["RetentionDays"] = cfg.retention_days;
  out["RetryHours"] = cfg.retry_hours;
  out["MaxMessageBytes"] = cfg.max_message;
  Json smtp = obj();
  smtp["Enabled"] = cfg.smtp_on;
  smtp["Port"] = cfg.smtp_port;
  smtp["Host"] = cfg.smtp_host;
  smtp["StartTls"] = !cfg.tls_cert.empty();
  smtp["RequireTls"] = cfg.smtp_require_tls;
  out["Smtp"] = smtp;
  return out;
}

OP(GetStatistics) {
  long long days_param = 14;
  if (truthy(params.get("Days")) && !py_int(params.get("Days"), days_param)) throw std::runtime_error("invalid Days");
  long long days = std::max(1LL, std::min(days_param, 90LL));
  long long today = static_cast<long long>(time_now()) / 86400;
  std::map<long long, Json> buckets;
  for (long long d = today - days + 1; d <= today; ++d) {
    Json b = obj();
    b["Date"] = d * 86400;
    for (const char* k : {"Sent", "Delivered", "Bounced", "Complaints", "Rejected", "Delayed"}) b[k] = 0;
    buckets[d] = b;
  }
  static const std::map<std::string, std::string> field = {{"Send", "Sent"},          {"Delivery", "Delivered"},
                                                           {"Bounce", "Bounced"},      {"Complaint", "Complaints"},
                                                           {"Reject", "Rejected"},     {"DeliveryDelay", "Delayed"}};
  Json status = obj();
  for (auto& kv : S().messages) {
    const Json& rec = kv.second;
    std::string st = str_or(rec.get("Status"));
    status[st] = static_cast<long long>(status.get(st).num()) + 1;
    if (!rec.get("Events").is_arr()) continue;
    for (auto& ev : rec.get("Events").arr()) {
      long long day = static_cast<long long>(ev.get("Timestamp").num()) / 86400;
      auto b = buckets.find(day);
      if (b == buckets.end()) continue;
      auto f = field.find(py_str(ev.get("Type")));
      if (f == field.end()) continue;
      b->second[f->second] = static_cast<long long>(b->second.get(f->second).num()) +
                             static_cast<long long>(ev.get("Recipients").size());
    }
  }
  Json counts = obj();
  counts["Identities"] = static_cast<long long>(S().identities.size());
  counts["Templates"] = static_cast<long long>(S().templates.size());
  counts["ConfigurationSets"] = static_cast<long long>(S().configuration_sets.size());
  counts["Suppressed"] = static_cast<long long>(S().suppressed.size());
  counts["Messages"] = static_cast<long long>(S().messages.size());
  Json out = obj();
  out["Days"] = Json::array();
  for (auto& kv : buckets) out["Days"].push(kv.second);
  out["MessagesByStatus"] = status;
  out["Counts"] = counts;
  out["Account"] = account_out(ctx);
  return out;
}

OP(GetSmtpCredentials) {
  UNUSED;
  std::string key = cfg.credentials.count(ctx.user) ? ctx.user
                                                     : (cfg.credentials.empty() ? "" : cfg.credentials.begin()->first);
  Json out = obj();
  if (key.empty()) {
    out["Username"] = "";
    out["Password"] = "";
    out["Note"] = "SES_AUTH=off: the SMTP endpoint takes any login.";
    return out;
  }
  std::string region = ctx.region.empty() ? cfg.region : ctx.region;
  out["Username"] = key;
  out["Password"] = smtp_password(cfg.credentials[key], region);
  out["Region"] = region;
  return out;
}

std::map<std::string, Op> build_ops() {
  std::map<std::string, Op> t;
#define REG(name) t[#name] = op_##name
  REG(GetAccount);
  REG(PutAccountSendingAttributes);
  REG(PutAccountSuppressionAttributes);
  REG(CreateEmailIdentity);
  REG(GetEmailIdentity);
  REG(ListEmailIdentities);
  REG(DeleteEmailIdentity);
  REG(PutEmailIdentityDkimAttributes);
  REG(PutEmailIdentityDkimSigningAttributes);
  REG(PutEmailIdentityMailFromAttributes);
  REG(PutEmailIdentityFeedbackAttributes);
  REG(PutEmailIdentityConfigurationSetAttributes);
  REG(CreateEmailTemplate);
  REG(GetEmailTemplate);
  REG(UpdateEmailTemplate);
  REG(DeleteEmailTemplate);
  REG(ListEmailTemplates);
  REG(TestRenderEmailTemplate);
  REG(CreateConfigurationSet);
  REG(GetConfigurationSet);
  REG(ListConfigurationSets);
  REG(DeleteConfigurationSet);
  REG(PutConfigurationSetSendingOptions);
  REG(PutConfigurationSetSuppressionOptions);
  REG(PutConfigurationSetDeliveryOptions);
  REG(PutConfigurationSetReputationOptions);
  REG(PutConfigurationSetTrackingOptions);
  REG(CreateConfigurationSetEventDestination);
  REG(UpdateConfigurationSetEventDestination);
  REG(GetConfigurationSetEventDestinations);
  REG(DeleteConfigurationSetEventDestination);
  REG(PutSuppressedDestination);
  REG(GetSuppressedDestination);
  REG(DeleteSuppressedDestination);
  REG(ListSuppressedDestinations);
  REG(TagResource);
  REG(UntagResource);
  REG(ListTagsForResource);
  REG(SendEmail);
  REG(SendBulkEmail);
  REG(ListMessages);
  REG(GetMessage);
  REG(DeleteMessage);
  REG(RetryMessage);
  REG(SetEmailIdentityVerified);
  REG(GetEmailIdentityDnsRecords);
  REG(GetServerInfo);
  REG(GetStatistics);
  REG(GetSmtpCredentials);
  REG(GetDeliverySettings);
  REG(PutDeliverySettings);
  REG(ResetDeliverySettings);
#undef REG
  return t;
}

Json check_email_identity(Json& params, const Ctx&) {
  std::string name, kind;
  {
    std::lock_guard<std::recursive_mutex> guard(S().lock);
    Json& rec = identity(req_str(params, "EmailIdentity"));
    name = py_str(rec.get("IdentityName"));
    kind = py_str(rec.get("IdentityType"));
  }
  if (kind == "DOMAIN") check_identity(name);
  std::lock_guard<std::recursive_mutex> guard(S().lock);
  auto it = S().identities.find(name);
  if (it == S().identities.end()) throw not_found("Email identity <" + name + "> does not exist.", "NotFound");
  return identity_out(it->second);
}

}  // namespace

// ----------------------------------------------------------------------------- shared helpers

std::pair<std::vector<Json>, std::string> page(const std::vector<Json>& items, const Json& params, int def, int limit) {
  long long size = def, start = 0;
  bool ok = true;
  const Json& ps = truthy(params.get("PageSize")) ? params.get("PageSize") : params.get("MaxItems");
  if (truthy(ps)) ok = py_int(ps, size);
  std::string decoded;
  if (ok) {
    try {
      decoded = sanitize_utf8(b64decode(str_or(params.get("NextToken"), "MA==")));
    } catch (const std::exception&) {
      ok = false;
    }
  }
  if (ok && !decoded.empty()) ok = parse_py_int(decoded, start);
  if (!ok) throw ApiError("BadRequestException", "The NextToken is not valid.", 400, "InvalidParameterValue");
  size = std::max(1LL, std::min(size, static_cast<long long>(limit)));
  long long n = static_cast<long long>(items.size());
  if (start < 0) start = std::max(0LL, n + start);
  std::vector<Json> chunk;
  for (long long i = start; i < std::min(n, start + size); ++i) chunk.push_back(items[static_cast<size_t>(i)]);
  std::string more = start + size < n ? b64encode(std::to_string(start + size)) : "";
  return {chunk, more};
}

Json account_out(const Ctx&) {
  Json out = Json::object();
  out["DedicatedIpAutoWarmupEnabled"] = false;
  out["EnforcementStatus"] = "HEALTHY";
  out["ProductionAccessEnabled"] = !cfg.sandbox;
  out["SendingEnabled"] = S().account.has("SendingEnabled") ? truthy(S().account.get("SendingEnabled")) : true;
  Json quota = Json::object();
  quota["Max24HourSend"] = cfg.max_24h;
  quota["MaxSendRate"] = cfg.max_rate;
  quota["SentLast24Hours"] = static_cast<double>(sent_last_24h());
  out["SendQuota"] = quota;
  Json supp = Json::object();
  supp["SuppressedReasons"] = truthy(S().account.get("SuppressedReasons")) ? S().account.get("SuppressedReasons") : Json::array();
  out["SuppressionAttributes"] = supp;
  Json details = Json::object();
  details["MailType"] = "TRANSACTIONAL";
  details["WebsiteURL"] = "";
  details["ContactLanguage"] = "EN";
  out["Details"] = details;
  return out;
}

Json dkim_out(const Json& rec) {
  const Json* dk = rec.find("Dkim");
  if ((!dk || dk->is_null()) && py_str(rec.get("IdentityType")) == "EMAIL_ADDRESS") {
    std::string name = py_str(rec.get("IdentityName"));
    for (auto& d : domains_up(name.substr(name.rfind('@') + 1))) {
      auto it = S().identities.find(d);
      if (it != S().identities.end() && truthy(it->second.get("Dkim"))) {
        dk = it->second.find("Dkim");
        break;
      }
    }
  }
  Json out = Json::object();
  if (!dk || !truthy(*dk)) {
    out["SigningEnabled"] = false;
    out["Status"] = "NOT_STARTED";
    out["Tokens"] = Json::array();
    return out;
  }
  out["SigningEnabled"] = truthy(dk->get("SigningEnabled"));
  out["Status"] = dk->has("Status") ? dk->get("Status") : Json("PENDING");
  out["Tokens"] = Json(std::vector<std::string>{py_str(dk->get("Selector"))});
  out["SigningAttributesOrigin"] = dk->has("Origin") ? dk->get("Origin") : Json("AWS_SES");
  out["NextSigningKeyLength"] = dk->has("NextSigningKeyLength") ? dk->get("NextSigningKeyLength") : Json("RSA_2048_BIT");
  out["CurrentSigningKeyLength"] =
      dk->has("CurrentSigningKeyLength") ? dk->get("CurrentSigningKeyLength") : Json("RSA_2048_BIT");
  out["LastKeyGenerationTimestamp"] = dk->get("LastKeyGenerationTimestamp");
  return out;
}

Json create_identity(const std::string& name, const Json& params, bool idempotent) {
  Store& store = S();
  std::string key = normalize_identity(Json(name));
  identity_kind(key);
  auto it = store.identities.find(key);
  if (it != store.identities.end()) {
    if (idempotent) return it->second;
    throw exists("Email identity <" + key + "> already exists.");
  }
  if (truthy(params.get("ConfigurationSetName"))) config_set(params.get("ConfigurationSetName"));
  Json rec = new_identity(key, params.get("DkimSigningAttributes"));
  rec["Tags"] = tags_in(params.get("Tags"));
  if (truthy(params.get("ConfigurationSetName"))) rec["ConfigurationSetName"] = py_str(params.get("ConfigurationSetName"));
  store.identities[key] = rec;
  save();
  if (py_str(rec.get("IdentityType")) == "DOMAIN") check_later(key);
  return rec;
}

std::string send_message(const SendArgs& a) {
  AcceptArgs acc;
  acc.operation = a.operation;
  acc.caller = a.ctx.caller;
  acc.source_ip = a.ctx.source_ip;
  acc.configuration_set_name = a.configuration_set;
  acc.tags = a.tags;
  acc.return_path = a.return_path;
  const Json& content = a.content;
  if (truthy(content.get("Raw"))) {
    std::string raw;
    try {
      raw = b64decode(str_or(content.get("Raw").get("Data")));
    } catch (const std::exception&) {
      throw bad_request("Raw.Data must be base64.");
    }
    if (strip(raw, " \t\r\n\f\v").empty()) throw bad_request("The raw message is empty.");
    RawRecipients rr = raw_recipients(raw);
    std::vector<std::string> dest;
    if (a.has_envelope) {
      dest = a.envelope;
    } else {
      dest = a.to;
      dest.insert(dest.end(), a.cc.begin(), a.cc.end());
      dest.insert(dest.end(), a.bcc.begin(), a.bcc.end());
      if (dest.empty()) {
        for (auto* list : {&rr.to, &rr.cc, &rr.bcc}) {
          Json l = Json::array();
          for (auto& x : *list) l.push(x);
          for (auto& x : addresses(l)) dest.push_back(x);
        }
      }
    }
    acc.source = a.source.empty() ? rr.from : a.source;
    acc.has_envelope = true;
    acc.envelope = dest;
    acc.build = [raw](const std::string& mid, double ts) { return prepare_raw(raw, mid, ts); };
    return accept(acc);
  }
  Json message;
  if (truthy(content.get("Template"))) {
    const Json& tpl = content.get("Template");
    Rendered r = template_parts(tpl, template_data_of(tpl.get("TemplateData")));
    message = Json::object();
    Json subject = Json::object();
    subject["Data"] = r.subject;
    message["Subject"] = subject;
    Json body = Json::object();
    if (r.has_text) {
      Json t = Json::object();
      t["Data"] = r.text;
      body["Text"] = t;
    }
    if (r.has_html) {
      Json h = Json::object();
      h["Data"] = r.html;
      body["Html"] = h;
    }
    message["Body"] = body;
    message["Headers"] = tpl.get("Headers");
    message["Attachments"] = tpl.get("Attachments");
  } else if (truthy(content.get("Simple"))) {
    message = content.get("Simple");
    if (message.get("Subject").is_null()) throw bad_request("Message.Subject is required.");
  } else {
    throw bad_request("Content needs Simple, Raw or Template.");
  }
  std::string source = a.source;
  std::vector<std::string> to = a.to, cc = a.cc, reply_to = a.reply_to;
  acc.source = source;
  acc.to = a.to;
  acc.cc = a.cc;
  acc.bcc = a.bcc;
  acc.has_envelope = a.has_envelope;
  acc.envelope = a.envelope;
  acc.build = [source, to, cc, reply_to, message](const std::string& mid, double ts) {
    return mime_simple(source, to, cc, reply_to, message, mid, ts);
  };
  return accept(acc);
}

Json run_unlocked(const std::string& name, Json& params, const Ctx& ctx) {
  if (name == "CheckEmailIdentity") return check_email_identity(params, ctx);
  if (name == "TestDeliverySettings") return test_delivery_settings(params, ctx);
  auto it = ops().find(name);
  if (it == ops().end()) throw ApiError("BadRequestException", "Unknown operation " + name + ".", 400, "InvalidAction");
  return it->second(params, ctx);
}

Json run(const std::string& name, Json params, const Ctx& ctx) {
  if (name == "CheckEmailIdentity" || name == "TestDeliverySettings") return run_unlocked(name, params, ctx);
  std::lock_guard<std::recursive_mutex> guard(db().lock);
  return run_unlocked(name, params, ctx);
}

}  // namespace ses
