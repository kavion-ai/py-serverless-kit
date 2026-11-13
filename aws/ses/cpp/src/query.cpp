#include "query.hpp"

#include <algorithm>
#include <cmath>
#include <functional>
#include <map>
#include <mutex>

#include "identities.hpp"
#include "store.hpp"
#include "util.hpp"

namespace ses {

namespace {

const char* const NS = "http://ses.amazonaws.com/doc/2010-12-01/";
const char* const MAP_MARK = "\x01map";  // an object answered as <entry><key/><value/></entry> items
const char* const TS_MARK = "\x01ts";    // a timestamp answered in ISO 8601

using Action = std::function<Json(Json&, const Ctx&)>;

Json xml_map() {
  Json m = Json::object();
  m[MAP_MARK] = true;
  return m;
}

Json ts(double value) {
  Json t = Json::object();
  t[TS_MARK] = value;
  return t;
}

std::string escape(const std::string& s) {
  std::string out;
  for (char c : s) {
    if (c == '&') out += "&amp;";
    else if (c == '<') out += "&lt;";
    else if (c == '>') out += "&gt;";
    else out += c;
  }
  return out;
}

std::string xml(const std::string& name, const Json& value) {
  if (value.is_null()) return "";
  if (value.is_obj() && value.has(TS_MARK)) return "<" + name + ">" + escape(iso(value.get(TS_MARK).num())) + "</" + name + ">";
  if (value.is_obj() && value.has(MAP_MARK)) {
    std::string inner;
    for (auto& kv : value.items()) {
      if (kv.first == MAP_MARK) continue;
      inner += "<entry><key>" + escape(kv.first) + "</key>" + xml("value", kv.second) + "</entry>";
    }
    return "<" + name + ">" + inner + "</" + name + ">";
  }
  if (value.is_obj()) {
    std::string inner;
    for (auto& kv : value.items()) inner += xml(kv.first, kv.second);
    return "<" + name + ">" + inner + "</" + name + ">";
  }
  if (value.is_arr()) {
    std::string inner;
    for (auto& v : value.arr()) inner += xml("member", v);
    return "<" + name + ">" + inner + "</" + name + ">";
  }
  std::string text;
  if (value.is_bool()) {
    text = value.b() ? "true" : "false";
  } else if (value.is_float() && std::isfinite(value.d()) && value.d() == std::floor(value.d())) {
    char buf[64];
    std::snprintf(buf, sizeof buf, "%.1f", value.d());
    text = buf;
  } else {
    text = py_str(value);
  }
  return "<" + name + ">" + escape(text) + "</" + name + ">";
}

std::pair<int, std::string> answer(const std::string& name, const Json& result) {
  std::string inner = result.is_null() ? "" : xml(name + "Result", result);
  return {200, "<" + name + "Response xmlns=\"" + NS + "\">" + inner + "<ResponseMetadata><RequestId>" + uuid4() +
                   "</RequestId></ResponseMetadata></" + name + "Response>"};
}

Json lists(const Json& node) {
  if (!node.is_obj()) return node;
  if (node.size() == 1 && node.has("member") && node.get("member").is_obj()) {
    std::vector<std::pair<long long, const Json*>> items;
    for (auto& kv : node.get("member").items()) {
      long long k = 0;
      bool digits = !kv.first.empty() && std::all_of(kv.first.begin(), kv.first.end(), [](char c) {
        return std::isdigit(static_cast<unsigned char>(c));
      });
      if (digits) parse_py_int(kv.first, k);
      items.emplace_back(k, &kv.second);
    }
    std::stable_sort(items.begin(), items.end(),
                     [](const std::pair<long long, const Json*>& a, const std::pair<long long, const Json*>& b) {
                       return a.first < b.first;
                     });
    Json out = Json::array();
    for (auto& it : items) out.push(lists(*it.second));
    return out;
  }
  Json out = Json::object();
  for (auto& kv : node.items()) out[kv.first] = lists(kv.second);
  return out;
}

Json parse_form(const std::string& body, const std::string& query) {
  auto pairs = parse_qsl(query);
  auto more = parse_qsl(body);
  pairs.insert(pairs.end(), more.begin(), more.end());
  Json root = Json::object();
  for (auto& kv : pairs) {
    Json* cur = &root;
    std::vector<std::string> parts = split(kv.first, '.');
    for (size_t i = 0; i < parts.size(); ++i) {
      if (i + 1 == parts.size()) {
        (*cur)[parts[i]] = kv.second;
      } else {
        Json& nxt = (*cur)[parts[i]];
        if (!nxt.is_obj()) nxt = Json::object();
        cur = &nxt;
      }
    }
  }
  return lists(root);
}

std::string str_or(const Json& v, const std::string& def = "") { return truthy(v) ? py_str(v) : def; }

void required(const Json& params, std::initializer_list<const char*> names) {
  for (const char* n : names) {
    const Json& v = params.get(n);
    if (v.is_null() || (v.is_str() && v.s().empty()))
      throw ApiError("BadRequestException", std::string(n) + " is required.", 400, "MissingParameter");
  }
}

Json dest_of(const Json& d) {
  Json out = Json::object();
  for (const char* k : {"ToAddresses", "CcAddresses", "BccAddresses"})
    out[k] = d.is_obj() && truthy(d.get(k)) ? d.get(k) : Json::array();
  return out;
}

std::string send(const Json& params, const Ctx& ctx, const std::string& operation, const Json& content) {
  Json dest = dest_of(params.get("Destination"));
  SendArgs a;
  a.operation = operation;
  a.ctx = ctx;
  a.source = str_or(params.get("Source"));
  a.to = addresses(dest.get("ToAddresses"));
  a.cc = addresses(dest.get("CcAddresses"));
  a.bcc = addresses(dest.get("BccAddresses"));
  a.reply_to = addresses(params.get("ReplyToAddresses"));
  a.content = content;
  a.configuration_set = str_or(params.get("ConfigurationSetName"));
  a.tags = params.get("Tags");
  a.return_path = str_or(params.get("ReturnPath"));
  return send_message(a);
}

std::string v1_status(const std::string& s, const std::string& def) {
  static const std::map<std::string, std::string> m = {{"SUCCESS", "Success"},
                                                       {"PENDING", "Pending"},
                                                       {"FAILED", "Failed"},
                                                       {"TEMPORARY_FAILURE", "TemporaryFailure"},
                                                       {"NOT_STARTED", "NotStarted"}};
  auto it = m.find(s);
  return it == m.end() ? def : it->second;
}

Json obj() { return Json::object(); }

Json message_id_result(const std::string& id) {
  Json out = obj();
  out["MessageId"] = id;
  return out;
}

std::vector<std::string> identity_names(const Json& params) {
  const Json& names = params.get("Identities");
  std::vector<std::string> out;
  if (!truthy(names)) return out;
  if (!names.is_arr() || names.arr().size() > 100)
    throw ApiError("BadRequestException", "Identities must list up to 100 identities.", 400, "InvalidParameterValue");
  for (auto& n : names.arr()) out.push_back(normalize_identity(n));
  return out;
}

Json op(const std::string& name, Json params, const Ctx& ctx) { return run_unlocked(name, params, ctx); }

Json delete_identity(const Json& identity) {
  Store& store = db();
  if (store.identities.erase(normalize_identity(identity))) store.save();
  return obj();
}

std::map<std::string, Action> build_actions();
std::map<std::string, Action>& actions() {
  static std::map<std::string, Action> table = build_actions();  // thread-safe initialization
  return table;
}

std::map<std::string, Action> build_actions() {
  std::map<std::string, Action> table;
  auto& t = table;

  t["SendEmail"] = [](Json& p, const Ctx& ctx) {
    required(p, {"Source", "Message"});
    Json message = p.get("Message").is_obj() ? p.get("Message") : obj();
    if (!truthy(message.get("Body")))
      throw ApiError("BadRequestException", "Message.Body is required.", 400, "MissingParameter");
    if (!message.has("Subject")) {
      Json s = obj();
      s["Data"] = "";
      message["Subject"] = s;
    }
    Json content = obj();
    content["Simple"] = message;
    return message_id_result(send(p, ctx, "SendEmail", content));
  };

  t["SendRawEmail"] = [](Json& p, const Ctx& ctx) {
    Json raw = p.get("RawMessage").is_obj() ? p.get("RawMessage") : obj();
    if (!truthy(raw.get("Data")))
      throw ApiError("BadRequestException", "RawMessage.Data is required.", 400, "MissingParameter");
    SendArgs a;
    a.operation = "SendRawEmail";
    a.ctx = ctx;
    a.source = str_or(p.get("Source"));
    Json content = obj();
    Json r = obj();
    r["Data"] = raw.get("Data");
    content["Raw"] = r;
    a.content = content;
    a.configuration_set = str_or(p.get("ConfigurationSetName"));
    a.tags = p.get("Tags");
    if (truthy(p.get("Destinations"))) {
      a.has_envelope = true;
      a.envelope = addresses(p.get("Destinations"));
    }
    return message_id_result(send_message(a));
  };

  t["SendTemplatedEmail"] = [](Json& p, const Ctx& ctx) {
    required(p, {"Source", "Template", "TemplateData"});
    Json tpl = obj();
    tpl["TemplateName"] = p.get("Template");
    tpl["TemplateData"] = p.get("TemplateData");
    Json content = obj();
    content["Template"] = tpl;
    return message_id_result(send(p, ctx, "SendTemplatedEmail", content));
  };

  t["SendBulkTemplatedEmail"] = [](Json& p, const Ctx& ctx) {
    required(p, {"Source", "Template", "DefaultTemplateData", "Destinations"});
    Json entries = Json::array();
    if (p.get("Destinations").is_arr())
      for (auto& d : p.get("Destinations").arr()) {
        Json entry = obj();
        entry["Destination"] = dest_of(d.get("Destination"));
        if (truthy(d.get("ReplacementTemplateData"))) {
          Json rt = obj();
          rt["ReplacementTemplateData"] = d.get("ReplacementTemplateData");
          Json rc = obj();
          rc["ReplacementTemplate"] = rt;
          entry["ReplacementEmailContent"] = rc;
        }
        if (truthy(d.get("ReplacementTags"))) entry["ReplacementTags"] = d.get("ReplacementTags");
        entries.push(entry);
      }
    Json req = obj();
    req["FromEmailAddress"] = p.get("Source");
    req["ReplyToAddresses"] = p.get("ReplyToAddresses");
    req["ConfigurationSetName"] = p.get("ConfigurationSetName");
    req["DefaultEmailTags"] = p.get("DefaultTags");
    Json tpl = obj();
    tpl["TemplateName"] = p.get("Template");
    tpl["TemplateData"] = p.get("DefaultTemplateData");
    Json dc = obj();
    dc["Template"] = tpl;
    req["DefaultContent"] = dc;
    req["BulkEmailEntries"] = entries;
    Json out = op("SendBulkEmail", req, ctx);
    static const std::map<std::string, std::string> v1 = {
        {"SUCCESS", "Success"},
        {"MESSAGE_REJECTED", "MessageRejected"},
        {"MAIL_FROM_DOMAIN_NOT_VERIFIED", "MailFromDomainNotVerified"},
        {"CONFIGURATION_SET_NOT_FOUND", "ConfigurationSetDoesNotExist"},
        {"TEMPLATE_NOT_FOUND", "TemplateDoesNotExist"},
        {"ACCOUNT_THROTTLED", "AccountThrottled"},
        {"ACCOUNT_DAILY_QUOTA_EXCEEDED", "AccountDailyQuotaExceeded"},
        {"ACCOUNT_SENDING_PAUSED", "AccountSendingPaused"},
        {"CONFIGURATION_SET_SENDING_PAUSED", "ConfigurationSetSendingPaused"},
        {"INVALID_PARAMETER", "InvalidParameterValue"},
        {"FAILED", "Failed"}};
    Json status = Json::array();
    for (auto& r : out.get("BulkEmailEntryResults").arr()) {
      Json item = obj();
      auto it = v1.find(py_str(r.get("Status")));
      item["Status"] = it == v1.end() ? "Failed" : it->second;
      if (truthy(r.get("Error"))) item["Error"] = r.get("Error");
      if (truthy(r.get("MessageId"))) item["MessageId"] = r.get("MessageId");
      status.push(item);
    }
    Json result = obj();
    result["Status"] = status;
    return result;
  };

  t["VerifyEmailIdentity"] = [](Json& p, const Ctx&) {
    required(p, {"EmailAddress"});
    create_identity(py_str(p.get("EmailAddress")), obj(), true);
    return obj();
  };
  t["VerifyEmailAddress"] = [](Json& p, const Ctx& ctx) {
    actions()["VerifyEmailIdentity"](p, ctx);
    return Json();
  };
  t["VerifyDomainIdentity"] = [](Json& p, const Ctx&) {
    required(p, {"Domain"});
    if (py_str(p.get("Domain")).find('@') != std::string::npos)
      throw ApiError("BadRequestException", "Invalid domain name.", 400, "InvalidParameterValue");
    Json rec = create_identity(py_str(p.get("Domain")), obj(), true);
    Json out = obj();
    out["VerificationToken"] = str_or(rec.get("VerificationToken"));
    return out;
  };
  t["VerifyDomainDkim"] = [](Json& p, const Ctx& ctx) {
    actions()["VerifyDomainIdentity"](p, ctx);
    const Json& ident = db().identities.at(normalize_identity(p.get("Domain")));
    Json out = obj();
    out["DkimTokens"] = truthy(ident.get("Dkim")) ? Json(std::vector<std::string>{py_str(ident.get("Dkim").get("Selector"))})
                                                  : Json::array();
    return out;
  };
  t["ListIdentities"] = [](Json& p, const Ctx&) {
    std::string type = str_or(p.get("IdentityType"));
    std::string kind = type == "EmailAddress" ? "EMAIL_ADDRESS" : (type == "Domain" ? "DOMAIN" : "");
    std::vector<Json> names;
    for (auto& kv : db().identities)
      if (kind.empty() || py_str(kv.second.get("IdentityType")) == kind) names.push_back(Json(kv.first));
    auto pg = page(names, p, 1000);
    Json out = obj();
    out["Identities"] = Json::array();
    for (auto& n : pg.first) out["Identities"].push(n);
    if (!pg.second.empty()) out["NextToken"] = pg.second;
    return out;
  };
  t["ListVerifiedEmailAddresses"] = [](Json&, const Ctx&) {
    Json names = Json::array();
    for (auto& kv : db().identities)
      if (py_str(kv.second.get("IdentityType")) == "EMAIL_ADDRESS" && status_of(kv.second) == "SUCCESS")
        names.push(kv.first);
    Json out = obj();
    out["VerifiedEmailAddresses"] = names;
    return out;
  };
  t["GetIdentityVerificationAttributes"] = [](Json& p, const Ctx&) {
    Json out = xml_map();
    for (auto& name : identity_names(p)) {
      auto it = db().identities.find(name);
      if (it == db().identities.end()) continue;
      Json item = obj();
      item["VerificationStatus"] = v1_status(status_of(it->second), "Pending");
      if (truthy(it->second.get("VerificationToken"))) item["VerificationToken"] = it->second.get("VerificationToken");
      out[name] = item;
    }
    Json result = obj();
    result["VerificationAttributes"] = out;
    return result;
  };
  t["GetIdentityDkimAttributes"] = [](Json& p, const Ctx&) {
    Json out = xml_map();
    for (auto& name : identity_names(p)) {
      auto it = db().identities.find(name);
      if (it == db().identities.end()) continue;
      Json dk = dkim_out(it->second);
      Json item = obj();
      item["DkimEnabled"] = dk.get("SigningEnabled");
      item["DkimVerificationStatus"] = v1_status(py_str(dk.get("Status")), "NotStarted");
      if (truthy(it->second.get("Dkim"))) item["DkimTokens"] = dk.get("Tokens");
      out[name] = item;
    }
    Json result = obj();
    result["DkimAttributes"] = out;
    return result;
  };
  t["GetIdentityMailFromDomainAttributes"] = [](Json& p, const Ctx&) {
    Json out = xml_map();
    for (auto& name : identity_names(p)) {
      auto it = db().identities.find(name);
      if (it == db().identities.end() || !truthy(it->second.get("MailFrom"))) continue;
      const Json& mf = it->second.get("MailFrom");
      Json item = obj();
      item["MailFromDomain"] = mf.get("MailFromDomain");
      item["MailFromDomainStatus"] = v1_status(str_or(mf.get("MailFromDomainStatus"), "PENDING"), "Pending");
      item["BehaviorOnMXFailure"] =
          py_str(mf.get("BehaviorOnMxFailure")) == "REJECT_MESSAGE" ? "RejectMessage" : "UseDefaultValue";
      out[name] = item;
    }
    Json result = obj();
    result["MailFromDomainAttributes"] = out;
    return result;
  };
  t["SetIdentityMailFromDomain"] = [](Json& p, const Ctx& ctx) {
    required(p, {"Identity"});
    Json req = obj();
    req["EmailIdentity"] = p.get("Identity");
    req["MailFromDomain"] = p.get("MailFromDomain");
    req["BehaviorOnMxFailure"] = str_or(p.get("BehaviorOnMXFailure")) == "RejectMessage" ? "REJECT_MESSAGE" : "USE_DEFAULT_VALUE";
    op("PutEmailIdentityMailFromAttributes", req, ctx);
    return obj();
  };
  t["SetIdentityDkimEnabled"] = [](Json& p, const Ctx& ctx) {
    required(p, {"Identity", "DkimEnabled"});
    Json req = obj();
    req["EmailIdentity"] = p.get("Identity");
    req["SigningEnabled"] = lower(py_str(p.get("DkimEnabled"))) == "true";
    op("PutEmailIdentityDkimAttributes", req, ctx);
    return obj();
  };
  t["SetIdentityFeedbackForwardingEnabled"] = [](Json& p, const Ctx& ctx) {
    required(p, {"Identity", "ForwardingEnabled"});
    Json req = obj();
    req["EmailIdentity"] = p.get("Identity");
    req["EmailForwardingEnabled"] = lower(py_str(p.get("ForwardingEnabled"))) == "true";
    op("PutEmailIdentityFeedbackAttributes", req, ctx);
    return obj();
  };
  t["DeleteIdentity"] = [](Json& p, const Ctx&) {
    required(p, {"Identity"});
    return delete_identity(p.get("Identity"));
  };
  t["DeleteVerifiedEmailAddress"] = [](Json& p, const Ctx&) {
    required(p, {"EmailAddress"});
    delete_identity(p.get("EmailAddress"));
    return Json();
  };

  t["GetSendQuota"] = [](Json&, const Ctx& ctx) { return account_out(ctx).get("SendQuota"); };
  t["GetSendStatistics"] = [](Json&, const Ctx&) {
    double since = time_now() - 14 * 86400;
    std::map<long long, Json> buckets;
    for (const Json* rec : db().recent(since - 86400)) {
      if (!rec->get("Events").is_arr()) continue;
      for (auto& ev : rec->get("Events").arr()) {
        double t = ev.get("Timestamp").num();
        if (t < since) continue;
        long long slot = static_cast<long long>(t) / 900 * 900;
        auto it = buckets.find(slot);
        if (it == buckets.end()) {
          Json b = obj();
          b["Timestamp"] = ts(static_cast<double>(slot));
          b["DeliveryAttempts"] = 0;
          b["Bounces"] = 0;
          b["Complaints"] = 0;
          b["Rejects"] = 0;
          it = buckets.emplace(slot, b).first;
        }
        std::string type = py_str(ev.get("Type"));
        std::string field = type == "Send" ? "DeliveryAttempts"
                            : type == "Bounce" ? "Bounces"
                            : type == "Complaint" ? "Complaints"
                            : type == "Reject" ? "Rejects" : "";
        if (!field.empty())
          it->second[field] = static_cast<long long>(it->second.get(field).num()) +
                              static_cast<long long>(ev.get("Recipients").size());
      }
    }
    Json points = Json::array();
    for (auto& kv : buckets) points.push(kv.second);
    Json out = obj();
    out["SendDataPoints"] = points;
    return out;
  };
  t["GetAccountSendingEnabled"] = [](Json&, const Ctx&) {
    Json out = obj();
    out["Enabled"] = db().account.has("SendingEnabled") ? truthy(db().account.get("SendingEnabled")) : true;
    return out;
  };
  t["UpdateAccountSendingEnabled"] = [](Json& p, const Ctx& ctx) {
    Json req = obj();
    req["SendingEnabled"] = lower(p.has("Enabled") ? py_str(p.get("Enabled")) : "false") == "true";
    op("PutAccountSendingAttributes", req, ctx);
    return Json();
  };

  auto v1_template = [](const Json& p) {
    Json tpl = p.get("Template").is_obj() ? p.get("Template") : obj();
    if (!truthy(tpl.get("TemplateName")))
      throw ApiError("BadRequestException", "Template.TemplateName is required.", 400, "MissingParameter");
    Json out = obj();
    out["TemplateName"] = tpl.get("TemplateName");
    Json content = obj();
    content["Subject"] = truthy(tpl.get("SubjectPart")) ? tpl.get("SubjectPart") : Json("");
    content["Text"] = truthy(tpl.get("TextPart")) ? tpl.get("TextPart") : Json("");
    content["Html"] = truthy(tpl.get("HtmlPart")) ? tpl.get("HtmlPart") : Json("");
    out["TemplateContent"] = content;
    return out;
  };
  t["CreateTemplate"] = [v1_template](Json& p, const Ctx& ctx) {
    op("CreateEmailTemplate", v1_template(p), ctx);
    return obj();
  };
  t["UpdateTemplate"] = [v1_template](Json& p, const Ctx& ctx) {
    op("UpdateEmailTemplate", v1_template(p), ctx);
    return obj();
  };
  t["GetTemplate"] = [](Json& p, const Ctx& ctx) {
    required(p, {"TemplateName"});
    Json req = obj();
    req["TemplateName"] = p.get("TemplateName");
    Json out = op("GetEmailTemplate", req, ctx);
    const Json& content = out.get("TemplateContent");
    Json tpl = obj();
    tpl["TemplateName"] = out.get("TemplateName");
    tpl["SubjectPart"] = content.get("Subject");
    if (truthy(content.get("Text"))) tpl["TextPart"] = content.get("Text");
    if (truthy(content.get("Html"))) tpl["HtmlPart"] = content.get("Html");
    Json result = obj();
    result["Template"] = tpl;
    return result;
  };
  t["DeleteTemplate"] = [](Json& p, const Ctx&) {
    required(p, {"TemplateName"});
    if (db().templates.erase(py_str(p.get("TemplateName")))) db().save();
    return obj();
  };
  t["ListTemplates"] = [](Json& p, const Ctx& ctx) {
    Json req = obj();
    req["NextToken"] = p.get("NextToken");
    req["PageSize"] = truthy(p.get("MaxItems")) ? p.get("MaxItems") : Json(10);
    Json out = op("ListEmailTemplates", req, ctx);
    Json meta = Json::array();
    for (auto& m : out.get("TemplatesMetadata").arr()) {
      Json item = obj();
      item["Name"] = m.get("TemplateName");
      item["CreatedTimestamp"] = ts(truthy(m.get("CreatedTimestamp")) ? m.get("CreatedTimestamp").num() : 0);
      meta.push(item);
    }
    Json result = obj();
    result["TemplatesMetadata"] = meta;
    if (truthy(out.get("NextToken"))) result["NextToken"] = out.get("NextToken");
    return result;
  };
  t["TestRenderTemplate"] = [](Json& p, const Ctx& ctx) {
    required(p, {"TemplateName", "TemplateData"});
    Json req = obj();
    req["TemplateName"] = p.get("TemplateName");
    req["TemplateData"] = p.get("TemplateData");
    return op("TestRenderEmailTemplate", req, ctx);
  };

  t["CreateConfigurationSet"] = [](Json& p, const Ctx& ctx) {
    Json cs = p.get("ConfigurationSet").is_obj() ? p.get("ConfigurationSet") : obj();
    if (!truthy(cs.get("Name")))
      throw ApiError("BadRequestException", "ConfigurationSet.Name is required.", 400, "MissingParameter");
    Json req = obj();
    req["ConfigurationSetName"] = cs.get("Name");
    try {
      op("CreateConfigurationSet", req, ctx);
    } catch (const ApiError& e) {
      if (e.code == "BadRequestException") throw ApiError(e.code, e.message, 400, "InvalidConfigurationSet");
      throw;
    }
    return obj();
  };
  t["DeleteConfigurationSet"] = [](Json& p, const Ctx& ctx) {
    Json req = obj();
    req["ConfigurationSetName"] = p.get("ConfigurationSetName");
    op("DeleteConfigurationSet", req, ctx);
    return obj();
  };
  t["ListConfigurationSets"] = [](Json& p, const Ctx& ctx) {
    Json req = obj();
    req["NextToken"] = p.get("NextToken");
    req["PageSize"] = p.get("MaxItems");
    Json out = op("ListConfigurationSets", req, ctx);
    Json sets = Json::array();
    for (auto& n : out.get("ConfigurationSets").arr()) {
      Json item = obj();
      item["Name"] = n;
      sets.push(item);
    }
    Json result = obj();
    result["ConfigurationSets"] = sets;
    if (truthy(out.get("NextToken"))) result["NextToken"] = out.get("NextToken");
    return result;
  };
  t["DescribeConfigurationSet"] = [](Json& p, const Ctx& ctx) {
    Json req = obj();
    req["ConfigurationSetName"] = p.get("ConfigurationSetName");
    Json out = op("GetConfigurationSet", req, ctx);
    Json dests = op("GetConfigurationSetEventDestinations", req, ctx);
    static const std::map<std::string, std::string> camel = {
        {"SEND", "send"},         {"REJECT", "reject"}, {"BOUNCE", "bounce"},
        {"COMPLAINT", "complaint"}, {"DELIVERY", "delivery"}, {"OPEN", "open"},
        {"CLICK", "click"},       {"RENDERING_FAILURE", "renderingFailure"},
        {"DELIVERY_DELAY", "deliveryDelay"}, {"SUBSCRIPTION", "subscription"}};
    Json result = obj();
    Json cs = obj();
    cs["Name"] = out.get("ConfigurationSetName");
    result["ConfigurationSet"] = cs;
    Json list = Json::array();
    for (auto& d : dests.get("EventDestinations").arr()) {
      Json item = obj();
      item["Name"] = d.get("Name");
      item["Enabled"] = d.get("Enabled");
      Json types = Json::array();
      for (auto& tp : d.get("MatchingEventTypes").arr()) {
        auto it = camel.find(py_str(tp));
        types.push(it == camel.end() ? tp : Json(it->second));
      }
      item["MatchingEventTypes"] = types;
      list.push(item);
    }
    result["EventDestinations"] = list;
    Json delivery = obj();
    delivery["TlsPolicy"] = py_str(out.get("DeliveryOptions").get("TlsPolicy")) == "REQUIRE" ? "Require" : "Optional";
    result["DeliveryOptions"] = delivery;
    Json rep = obj();
    rep["SendingEnabled"] = out.get("SendingOptions").get("SendingEnabled");
    rep["ReputationMetricsEnabled"] = out.get("ReputationOptions").get("ReputationMetricsEnabled");
    result["ReputationOptions"] = rep;
    return result;
  };
  return table;
}

}  // namespace

std::pair<int, std::string> query_error(const ApiError& e) {
  std::string kind = e.status >= 500 ? "Receiver" : "Sender";
  int status = (e.status == 404 || e.status == 429) ? 400 : e.status;
  return {status, std::string("<ErrorResponse xmlns=\"") + NS + "\"><Error><Type>" + kind + "</Type><Code>" +
                      escape(e.v1) + "</Code><Message>" + escape(e.message) + "</Message></Error><RequestId>" +
                      uuid4() + "</RequestId></ErrorResponse>"};
}

std::pair<int, std::string> query_handle(const std::string& body, const std::string& query, const Ctx& ctx) {
  if (!valid_utf8(body)) return query_error(bad_request("The request body is not UTF-8 form data."));
  Json params = parse_form(body, query);
  std::string name = str_or(params.get("Action"));
  auto& table = actions();
  auto it = table.find(name);
  if (it == table.end())
    return query_error(ApiError("BadRequestException",
                                "The action " + (name.empty() ? std::string("(none)") : name) +
                                    " is not valid for this web service.",
                                400, "InvalidAction"));
  try {
    std::lock_guard<std::recursive_mutex> guard(db().lock);
    return answer(name, it->second(params, ctx));
  } catch (const ApiError& e) {
    return query_error(e);
  }
}

}  // namespace ses
