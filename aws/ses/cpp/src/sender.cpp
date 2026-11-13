#include "sender.hpp"

#include <algorithm>
#include <deque>
#include <mutex>

#include "config.hpp"
#include "dkim.hpp"
#include "errors.hpp"
#include "events.hpp"
#include "identities.hpp"
#include "mime.hpp"
#include "store.hpp"
#include "util.hpp"

namespace ses {

namespace {

std::deque<double> sent;
std::mutex rate_mu;
std::function<void()> wake;

bool tag_ok(const std::string& s) {
  if (s.empty() || s.size() > 256) return false;
  for (char c : s)
    if (!(std::isalnum(static_cast<unsigned char>(c)) || c == '_' || c == '-')) return false;
  return true;
}

void check_rate(size_t count) {
  if (static_cast<double>(sent_last_24h() + static_cast<long long>(count)) > cfg.max_24h)
    throw ApiError("LimitExceededException", "Daily message quota exceeded.", 400, "Throttling");
  std::lock_guard<std::mutex> lock(rate_mu);
  double cutoff = time_now() - 1.0;
  while (!sent.empty() && sent.front() < cutoff) sent.pop_front();
  if (static_cast<double>(sent.size() + count) > std::max(cfg.max_rate, static_cast<double>(count)))
    throw ApiError("TooManyRequestsException", "Maximum sending rate exceeded.", 429, "Throttling");
  double t = time_now();
  for (size_t i = 0; i < count; ++i) sent.push_back(t);
}

Json message_tags(const Json& tags) {
  Json out = Json::array();
  if (!tags.is_arr()) return out;
  for (const Json& tag : tags.arr()) {
    std::string name = truthy(tag.get("Name")) ? py_str(tag.get("Name")) : "";
    std::string value = truthy(tag.get("Value")) ? py_str(tag.get("Value")) : "";
    if (!tag_ok(name) || !tag_ok(value))
      throw bad_request("Message tag names and values may contain only ASCII letters, digits, '_' and '-'.");
    Json t = Json::object();
    t["Name"] = name;
    t["Value"] = value;
    out.push(t);
  }
  return out;
}

std::string region_upper() { return upper(cfg.region); }

}  // namespace

void on_queued(std::function<void()> callback) { wake = std::move(callback); }

void wake_worker() {
  if (wake) wake();
}

long long sent_last_24h() {
  double since = time_now() - 86400;
  long long total = 0;
  for (const Json* r : db().recent(since)) total += static_cast<long long>(r->get("Destinations").size());
  return total;
}

const Json* configuration_set(const std::string& name) {
  if (name.empty()) return nullptr;
  auto it = db().configuration_sets.find(name);
  if (it == db().configuration_sets.end())
    throw not_found("Configuration set <" + name + "> does not exist.", "ConfigurationSetDoesNotExist");
  return &it->second;
}

std::string check_sender(const std::string& source) {
  const Json* enabled = db().account.find("SendingEnabled");
  if (enabled && !truthy(*enabled))
    throw ApiError("SendingPausedException", "Sending is paused for this account.", 400,
                   "AccountSendingPausedException");
  std::string addr = address(source);
  if (addr.empty())
    throw source.empty() ? bad_request("Missing final '@domain'")
                         : bad_request("Illegal address: " + py_repr_str(source) + ".");
  if (cfg.verify != "off" && sending_identity(addr).empty())
    throw rejected("Email address is not verified. The following identities failed the check in region " +
                   region_upper() + ": " + addr);
  return addr;
}

std::string accept(const AcceptArgs& a) {
  Store& store = db();
  std::lock_guard<std::recursive_mutex> guard(store.lock);
  const Json* cs = configuration_set(a.configuration_set_name);
  if (cs) {
    const Json* enabled = cs->find("SendingEnabled");
    if (enabled && !truthy(*enabled))
      throw ApiError("SendingPausedException", "Sending is paused for configuration set <" + py_str(cs->get("Name")) + ">.",
                     400, "ConfigurationSetSendingPausedException");
  }
  std::string sender = check_sender(a.source);
  std::vector<std::string> recipients;
  std::vector<std::string> pool;
  if (a.has_envelope && !a.envelope.empty()) {
    pool = a.envelope;
  } else {
    pool = a.to;
    pool.insert(pool.end(), a.cc.begin(), a.cc.end());
    pool.insert(pool.end(), a.bcc.begin(), a.bcc.end());
  }
  for (auto& addr : pool) {
    bool dup = false;
    for (auto& r : recipients)
      if (lower(r) == lower(addr)) dup = true;
    if (!dup) recipients.push_back(addr);
  }
  if (recipients.empty())
    throw a.has_envelope ? rejected("No recipients.") : bad_request("Missing required header 'To'.");
  if (recipients.size() > static_cast<size_t>(MAX_RECIPIENTS))
    throw rejected("Recipient count exceeds " + std::to_string(MAX_RECIPIENTS) + ".");
  if (cfg.sandbox) {
    std::vector<std::string> unverified;
    for (auto& r : recipients)
      if (domain_of(r) != SIMULATOR && !identity_verified(r)) unverified.push_back(r);
    if (!unverified.empty())
      throw rejected("Email address is not verified. The following identities failed the check in region " +
                     region_upper() + ": " + join(unverified, ", "));
  }
  Json tags = message_tags(a.tags);
  check_rate(recipients.size());
  std::string ident = message_id();
  double ts = now();
  std::string raw = a.build("<" + ident + "@" + domain_of(sender) + ">", ts);
  if (static_cast<long long>(raw.size()) > cfg.max_message)
    throw rejected("Message length is more than " + std::to_string(cfg.max_message / (1024 * 1024)) + " MB.");
  std::unique_ptr<Signer> signer = dkim_signer(sender);
  if (signer) raw = dkim_sign(raw, signer->domain, signer->selector, signer->key);

  std::string sending_id = sending_identity(sender);
  if (sending_id.empty()) sending_id = sender;
  std::string mail_from = a.return_path.empty() ? "" : address(a.return_path);
  if (mail_from.empty()) {
    auto it = store.identities.find(sending_id);
    const Json& mf = it == store.identities.end() ? Json() : it->second.get("MailFrom");
    if (mf.is_obj() && mf.get("MailFromDomainStatus").is_str() && mf.get("MailFromDomainStatus").s() == "SUCCESS")
      mail_from = "bounce@" + py_str(mf.get("MailFromDomain"));
    else
      mail_from = sender;
  }
  Json reasons = cs && cs->has("SuppressedReasons") && !cs->get("SuppressedReasons").is_null()
                     ? cs->get("SuppressedReasons")
                     : (truthy(store.account.get("SuppressedReasons")) ? store.account.get("SuppressedReasons")
                                                                     : Json::array());
  Json heads = mime_summary(raw);
  double max_seconds = cs && truthy(cs->get("MaxDeliverySeconds")) ? cs->get("MaxDeliverySeconds").num() : 1e12;
  double deadline = ts + std::min(cfg.retry_hours * 3600, max_seconds);
  Json rec = Json::object();
  rec["MessageId"] = ident;
  rec["Timestamp"] = ts;
  rec["Operation"] = a.operation;
  rec["Caller"] = a.caller;
  rec["SourceIp"] = a.source_ip;
  rec["Source"] = a.source;
  rec["From"] = sender;
  rec["FromDomain"] = domain_of(sender);
  rec["SourceArn"] = arn("identity", sending_id);
  rec["MailFrom"] = mail_from;
  rec["Destinations"] = Json(recipients);
  const Json& subj = heads.get("commonHeaders").get("subject");
  rec["Subject"] = truthy(subj) ? py_str(subj) : "";
  rec["ConfigurationSetName"] = a.configuration_set_name;
  rec["Tags"] = tags;
  rec["Size"] = static_cast<long long>(raw.size());
  rec["DkimDomain"] = signer ? signer->domain : "";
  rec["Headers"] = heads.get("headers");
  rec["CommonHeaders"] = heads.get("commonHeaders");
  rec["HeadersTruncated"] = heads.get("headersTruncated");
  rec["Delivery"] = cfg.delivery;
  rec["TlsPolicy"] = cs && truthy(cs->get("TlsPolicy")) ? py_str(cs->get("TlsPolicy")) : "OPTIONAL";
  rec["Deadline"] = deadline;
  rec["Recipients"] = Json::object();
  rec["Events"] = Json::array();
  std::vector<std::string> suppressed;
  for (auto& r : recipients) {
    auto it = store.suppressed.find(lower(r));
    bool hit = false;
    if (it != store.suppressed.end() && domain_of(r) != SIMULATOR && reasons.is_arr()) {
      const Json& reason = it->second.get("Reason");
      for (auto& x : reasons.arr())
        if (x == reason) hit = true;
    }
    Json st = Json::object();
    if (hit) {
      st["Status"] = "SUPPRESSED";
      st["Attempts"] = 0;
      st["Response"] = "Recipient is on the account-level suppression list";
      suppressed.push_back(r);
    } else {
      st["Status"] = "QUEUED";
      st["Attempts"] = 0;
      st["NextAttempt"] = ts;
      st["Response"] = "";
    }
    rec["Recipients"][r] = st;
  }
  add_event(rec, "Send", recipients);
  if (!suppressed.empty()) {
    Json detail = Json::object();
    detail["BounceType"] = "Permanent";
    detail["BounceSubType"] = "OnAccountSuppressionList";
    detail["Status"] = "5.1.1";
    detail["DiagnosticCode"] =
        "Amazon SES did not send the message to this address because it is on the suppression list for your account.";
    add_event(rec, "Bounce", suppressed, detail);
  }
  rec["Status"] = overall(rec);
  store.messages[ident] = rec;
  store.save_message(ident, &raw);
  wake_worker();
  return ident;
}

std::string overall(const Json& rec) {
  std::vector<std::string> states;
  for (auto& kv : rec.get("Recipients").items()) states.push_back(py_str(kv.second.get("Status")));
  auto any = [&](const char* s) { return std::find(states.begin(), states.end(), s) != states.end(); };
  if (any("SENDING")) return "SENDING";
  if (any("QUEUED")) return "QUEUED";
  if (any("DELAYED")) return "DELAYED";
  if (!states.empty() && std::all_of(states.begin(), states.end(), [](const std::string& s) { return s == "DELIVERED"; }))
    return "DELIVERED";
  if (!states.empty() && std::all_of(states.begin(), states.end(), [](const std::string& s) {
        return s == "BOUNCED" || s == "SUPPRESSED";
      }))
    return "BOUNCED";
  return "PARTIAL";
}

}  // namespace ses
