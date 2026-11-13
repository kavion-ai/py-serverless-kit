#include "events.hpp"

#include <chrono>
#include <condition_variable>
#include <deque>
#include <mutex>
#include <set>
#include <thread>

#include "config.hpp"
#include "net.hpp"
#include "store.hpp"
#include "util.hpp"

namespace ses {

namespace {

std::mutex q_mu;
std::condition_variable q_cv;
std::deque<std::string> q;
bool started = false;

std::string str_or(const Json& v, const std::string& def = "") { return truthy(v) ? py_str(v) : def; }

bool wanted(const Json& rec, const std::string& kind) {
  std::string name = str_or(rec.get("ConfigurationSetName"));
  if (name.empty()) return true;
  Store& store = db();
  auto it = store.configuration_sets.find(name);
  if (it == store.configuration_sets.end()) return true;
  const Json& dests = it->second.get("EventDestinations");
  std::set<std::string> types;
  bool any = false;
  if (dests.is_obj()) {
    for (auto& kv : dests.items()) {
      const Json& enabled = kv.second.get("Enabled");
      if (!(enabled.is_null() ? true : truthy(enabled))) continue;
      any = true;
      const Json& m = kv.second.get("MatchingEventTypes");
      if (m.is_arr())
        for (auto& t : m.arr()) types.insert(upper(py_str(t)));
    }
  }
  if (!any) return true;
  return types.count(kind == "DeliveryDelay" ? "DELIVERY_DELAY" : upper(kind)) > 0;
}

void post_loop() {
  while (true) {
    std::string body;
    {
      std::unique_lock<std::mutex> lock(q_mu);
      q_cv.wait(lock, [] { return !q.empty(); });
      body = std::move(q.front());
      q.pop_front();
    }
    std::vector<std::string> headers{"Content-Type: application/json", "User-Agent: pskit-ses (" + cfg.region + ")"};
    if (!cfg.events_token.empty()) headers.push_back("Authorization: Bearer " + cfg.events_token);
    for (int attempt = 0; attempt < 3; ++attempt) {
      std::string error;
      int status = http_post(cfg.events_url, body, headers, error);
      if (status >= 0 && status < 400) break;
      if (status >= 400) error = "HTTP Error " + std::to_string(status);
      if (attempt == 2) log("events: POST to SES_EVENTS_URL failed: " + error);
      else std::this_thread::sleep_for(std::chrono::seconds(1 << attempt));
    }
  }
}

Json recipients_list(const std::vector<std::string>& r) { return Json(r); }

}  // namespace

void add_event(Json& rec, const std::string& kind, const std::vector<std::string>& recipients, const Json& detail) {
  Json event = Json::object();
  event["Type"] = kind;
  event["Timestamp"] = now();
  event["Recipients"] = recipients_list(recipients);
  for (auto& kv : detail.items()) event[kv.first] = kv.second;
  Json& list = rec["Events"];
  if (!list.is_arr()) list = Json::array();
  list.push(event);
  if (!cfg.events_url.empty() && wanted(rec, kind)) {
    std::string body = dump_json(publish_format(rec, event));
    std::lock_guard<std::mutex> lock(q_mu);
    if (!started) {
      std::thread(post_loop).detach();
      started = true;
    }
    if (q.size() >= 10000) {
      log("events: queue full, dropped a " + kind + " event of " + str_or(rec.get("MessageId")));
    } else {
      q.push_back(std::move(body));
      q_cv.notify_one();
    }
  }
}

Json publish_format(const Json& rec, const Json& event) {
  Json tags = Json::object();
  tags["ses:operation"] = Json(std::vector<std::string>{str_or(rec.get("Operation"), "SendEmail")});
  tags["ses:source-ip"] = Json(std::vector<std::string>{str_or(rec.get("SourceIp"))});
  tags["ses:from-domain"] = Json(std::vector<std::string>{str_or(rec.get("FromDomain"))});
  tags["ses:caller-identity"] = Json(std::vector<std::string>{str_or(rec.get("Caller"))});
  if (truthy(rec.get("ConfigurationSetName")))
    tags["ses:configuration-set"] = Json(std::vector<std::string>{py_str(rec.get("ConfigurationSetName"))});
  if (rec.get("Tags").is_arr())
    for (auto& t : rec.get("Tags").arr()) {
      Json& list = tags[py_str(t.get("Name"))];
      if (!list.is_arr()) list = Json::array();
      list.push(t.get("Value"));
    }
  double ts = rec.get("Timestamp").num();
  Json mail = Json::object();
  mail["timestamp"] = iso(ts);
  mail["source"] = str_or(rec.get("Source"));
  mail["sourceArn"] = str_or(rec.get("SourceArn"));
  mail["sendingAccountId"] = cfg.account;
  mail["messageId"] = rec.get("MessageId");
  mail["destination"] = truthy(rec.get("Destinations")) ? rec.get("Destinations") : Json::array();
  mail["headersTruncated"] = rec.has("HeadersTruncated") ? rec.get("HeadersTruncated") : Json(false);
  mail["headers"] = truthy(rec.get("Headers")) ? rec.get("Headers") : Json::array();
  mail["commonHeaders"] = truthy(rec.get("CommonHeaders")) ? rec.get("CommonHeaders") : Json::object();
  mail["tags"] = tags;
  std::string kind = py_str(event.get("Type"));
  std::string ets = iso(event.get("Timestamp").num());
  const Json& rcpts = event.get("Recipients");
  std::string message_id = str_or(rec.get("MessageId"));
  Json out = Json::object();
  out["eventType"] = kind;
  out["mail"] = mail;
  if (kind == "Send") {
    out["send"] = Json::object();
  } else if (kind == "Reject") {
    Json r = Json::object();
    r["reason"] = str_or(event.get("Reason"), "Bad content");
    out["reject"] = r;
  } else if (kind == "Delivery") {
    Json d = Json::object();
    d["timestamp"] = ets;
    d["processingTimeMillis"] = static_cast<long long>((event.get("Timestamp").num() - ts) * 1000);
    d["recipients"] = rcpts;
    d["smtpResponse"] = str_or(event.get("SmtpResponse"));
    d["reportingMTA"] = cfg.helo_name;
    d["remoteMtaIp"] = str_or(event.get("RemoteMtaIp"));
    out["delivery"] = d;
  } else if (kind == "Bounce") {
    Json b = Json::object();
    b["bounceType"] = str_or(event.get("BounceType"), "Permanent");
    b["bounceSubType"] = str_or(event.get("BounceSubType"), "General");
    Json list = Json::array();
    for (auto& r : rcpts.arr()) {
      Json item = Json::object();
      item["emailAddress"] = r;
      item["action"] = "failed";
      item["status"] = str_or(event.get("Status"), "5.0.0");
      item["diagnosticCode"] = str_or(event.get("DiagnosticCode"));
      list.push(item);
    }
    b["bouncedRecipients"] = list;
    b["timestamp"] = ets;
    b["feedbackId"] = str_or(event.get("FeedbackId"), message_id);
    b["reportingMTA"] = "dsn; " + cfg.helo_name;
    out["bounce"] = b;
  } else if (kind == "Complaint") {
    Json c = Json::object();
    Json list = Json::array();
    for (auto& r : rcpts.arr()) {
      Json item = Json::object();
      item["emailAddress"] = r;
      list.push(item);
    }
    c["complainedRecipients"] = list;
    c["timestamp"] = ets;
    c["feedbackId"] = str_or(event.get("FeedbackId"), message_id);
    c["complaintFeedbackType"] = str_or(event.get("FeedbackType"), "abuse");
    out["complaint"] = c;
  } else if (kind == "DeliveryDelay") {
    Json d = Json::object();
    d["timestamp"] = ets;
    d["delayType"] = str_or(event.get("DelayType"), "TransientCommunicationFailure");
    const Json& exp = event.get("ExpirationTime");
    d["expirationTime"] = iso(truthy(exp) ? exp.num() : event.get("Timestamp").num());
    Json list = Json::array();
    for (auto& r : rcpts.arr()) {
      Json item = Json::object();
      item["emailAddress"] = r;
      item["status"] = str_or(event.get("Status"), "4.0.0");
      item["diagnosticCode"] = str_or(event.get("DiagnosticCode"));
      list.push(item);
    }
    d["delayedRecipients"] = list;
    out["deliveryDelay"] = d;
  }
  return out;
}

int http_post(const std::string& url, const std::string& body, const std::vector<std::string>& headers,
              std::string& error, double timeout) {
  bool tls;
  std::string rest;
  if (starts_with(lower(url), "https://")) {
    tls = true;
    rest = url.substr(8);
  } else if (starts_with(lower(url), "http://")) {
    tls = false;
    rest = url.substr(7);
  } else {
    error = "unknown url type: " + url;
    return -1;
  }
  size_t slash = rest.find('/');
  std::string hostport = slash == std::string::npos ? rest : rest.substr(0, slash);
  std::string path = slash == std::string::npos ? "/" : rest.substr(slash);
  size_t at = hostport.rfind('@');
  if (at != std::string::npos) hostport = hostport.substr(at + 1);
  std::string host = hostport;
  int port = tls ? 443 : 80;
  size_t colon = hostport.rfind(':');
  size_t bracket = hostport.rfind(']');
  if (colon != std::string::npos && (bracket == std::string::npos || colon > bracket)) {
    host = hostport.substr(0, colon);
    port = std::atoi(hostport.c_str() + colon + 1);
  }
  if (host.size() > 2 && host.front() == '[') host = host.substr(1, host.size() - 2);
  int fd = connect_to(host, port, timeout, error);
  if (fd < 0) return -1;
  Conn conn(fd);
  conn.set_timeout(timeout);
  if (tls && !conn.start_tls_client(host, true, error)) return -1;
  std::string req = "POST " + path + " HTTP/1.1\r\nHost: " + hostport + "\r\nContent-Length: " +
                    std::to_string(body.size()) + "\r\nConnection: close\r\n";
  for (auto& h : headers) req += h + "\r\n";
  req += "\r\n" + body;
  if (!conn.write_all(req)) {
    error = "connection lost";
    return -1;
  }
  std::string line;
  if (!conn.read_line(line, 8192)) {
    error = "no answer";
    return -1;
  }
  std::vector<std::string> parts = split_ws(line);
  if (parts.size() < 2) {
    error = "bad answer";
    return -1;
  }
  return std::atoi(parts[1].c_str());
}

}  // namespace ses
