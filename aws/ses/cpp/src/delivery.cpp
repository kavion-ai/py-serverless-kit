#include "delivery.hpp"

#include <algorithm>
#include <cctype>
#include <chrono>
#include <condition_variable>
#include <deque>
#include <map>
#include <mutex>
#include <set>
#include <thread>
#include <tuple>

#include "config.hpp"
#include "dns.hpp"
#include "events.hpp"
#include "net.hpp"
#include "rsa.hpp"
#include "sender.hpp"
#include "store.hpp"
#include "util.hpp"

namespace ses {

namespace {

const int DELAYS[] = {60, 300, 900, 1800, 3600};

struct Result {
  std::string kind;  // ok, temp, perm, suppressed
  std::string response;
  std::string ip;
};

// recipient -> result, in insertion order (a later set replaces an earlier one)
struct Results {
  std::vector<std::pair<std::string, Result>> items;
  void set(const std::string& rcpt, const Result& r) {
    for (auto& kv : items)
      if (kv.first == rcpt) {
        kv.second = r;
        return;
      }
    items.emplace_back(rcpt, r);
  }
  void update(const Results& other) {
    for (auto& kv : other.items) set(kv.first, kv.second);
  }
};

struct HostFailed {
  std::string message;
};
struct Disconnected {
  std::string message;
};

std::string text_of(int code, const std::string& msg) {
  return strip(std::to_string(code) + " " + join(split_ws(msg), " "));
}

class SmtpClient {
 public:
  Conn conn;
  std::map<std::string, std::string> features;
  bool esmtp = false;

  void send(const std::string& line) {
    if (!conn.write_all(line + "\r\n")) throw Disconnected{"Server not connected"};
  }
  int reply(std::string& text) {
    std::vector<std::string> lines;
    int code = -1;
    while (true) {
      std::string line;
      if (!conn.read_line(line, 8193)) {
        conn.close();
        throw Disconnected{"Connection unexpectedly closed"};
      }
      std::string body = line.size() > 4 ? rstrip(line.substr(4), " \t\r\n") : "";
      lines.push_back(body);
      std::string c = line.substr(0, 3);
      try {
        code = std::stoi(c);
      } catch (...) {
        code = -1;
        break;
      }
      if (line.size() < 4 || line[3] != '-') break;
    }
    text = join(lines, "\n");
    return code;
  }
  int cmd(const std::string& line, std::string& text) {
    send(line);
    return reply(text);
  }
  int ehlo(const std::string& name) {
    std::string text;
    int code = cmd("ehlo " + name, text);
    features.clear();
    esmtp = false;
    if (code != 250) return code;
    esmtp = true;
    std::vector<std::string> lines = split(text, '\n');
    for (size_t i = 1; i < lines.size(); ++i) {
      const std::string& each = lines[i];
      size_t k = 0;
      while (k < each.size() && (std::isalnum(static_cast<unsigned char>(each[k])) || (k > 0 && each[k] == '-'))) ++k;
      if (k == 0) continue;
      std::string feature = lower(each.substr(0, k));
      std::string params = strip(each.substr(k));
      if (feature == "auth") features[feature] += " " + params;
      else features[feature] = params;
      if (starts_with(upper(each), "AUTH=")) features["auth"] += " " + each.substr(5);
    }
    return code;
  }
  bool has(const std::string& name) const { return features.count(name) > 0; }
};

struct AuthFailed {
  int code;
  std::string text;
};

// smtplib.SMTP.login: CRAM-MD5, PLAIN, LOGIN in that order of preference
void login(SmtpClient& c, const std::string& user, const std::string& password) {
  if (!c.has("auth")) throw Disconnected{"SMTP AUTH extension not supported by server."};
  std::vector<std::string> advertised = split_ws(upper(c.features["auth"]));
  std::vector<std::string> methods;
  for (const char* m : {"CRAM-MD5", "PLAIN", "LOGIN"})
    if (std::find(advertised.begin(), advertised.end(), m) != advertised.end()) methods.push_back(m);
  if (methods.empty()) throw Disconnected{"No suitable authentication method found."};
  AuthFailed last{535, ""};
  for (auto& m : methods) {
    std::string text;
    int code;
    int challenges;
    if (m == "CRAM-MD5") {
      code = c.cmd("AUTH CRAM-MD5", text);
      challenges = 0;
    } else if (m == "PLAIN") {
      code = c.cmd("AUTH PLAIN " + b64encode(std::string("\0", 1) + user + std::string("\0", 1) + password), text);
      challenges = 1;
    } else {
      code = c.cmd("AUTH LOGIN " + b64encode(user), text);
      challenges = 1;
    }
    while (code == 334) {
      ++challenges;
      std::string challenge;
      try {
        challenge = b64decode(text);
      } catch (...) {
      }
      std::string answer;
      if (m == "CRAM-MD5") answer = user + " " + hex(hmac_md5(password, challenge));
      else if (m == "PLAIN") answer = std::string("\0", 1) + user + std::string("\0", 1) + password;
      else answer = challenges < 2 ? user : password;
      code = c.cmd(b64encode(answer), text);
      if (challenges > 5) throw Disconnected{"Server AUTH mechanism infinite loop."};
    }
    if (code == 235 || code == 503) return;
    last = AuthFailed{code, text};
  }
  throw last;
}

Results session(const std::string& host, int port, const std::vector<std::string>& rcpts, const std::string& mail_from,
                const std::string& raw, const std::string& tls, bool require_tls, bool verify,
                const std::string& user = "", const std::string& password = "") {
  Results results;
  SmtpClient c;
  std::string error;
  int fd = connect_to(host, port, 60, error);
  if (fd < 0) throw HostFailed{"421 4.4.1 Connection to " + host + ":" + std::to_string(port) + " failed: " + error};
  c.conn.attach(fd);
  c.conn.set_timeout(60);
  std::string ip = c.conn.peer_ip();
  try {
    if (tls == "tls" && !c.conn.start_tls_client(host, verify, error))
      throw HostFailed{"421 4.4.1 Connection to " + host + ":" + std::to_string(port) + " failed: " + error};
    std::string text;
    int code = c.reply(text);
    if (code != 220)
      throw HostFailed{"421 4.4.1 Connection to " + host + ":" + std::to_string(port) + " failed: (" +
                       std::to_string(code) + ", " + py_repr_str(text) + ")"};
  } catch (const Disconnected& e) {
    throw HostFailed{"421 4.4.1 Connection to " + host + ":" + std::to_string(port) + " failed: " + e.message};
  }
  try {
    c.ehlo(cfg.helo_name);
    if (tls == "starttls" || tls == "opportunistic") {
      if (c.has("starttls")) {
        std::string text;
        int code = c.cmd("STARTTLS", text);
        if (code == 220 && !c.conn.start_tls_client(host, verify, error)) {
          if (require_tls || tls == "starttls") throw HostFailed{"421 4.4.2 " + host + ": " + error};
          c.conn.close();
          return session(host, port, rcpts, mail_from, raw, "none", false, false);
        }
        c.ehlo(cfg.helo_name);
      } else if (require_tls) {
        throw HostFailed{"421 4.7.10 " + host + " does not offer STARTTLS, which is required"};
      }
    }
    if (!user.empty()) {
      try {
        login(c, user, password);
      } catch (const AuthFailed& e) {
        throw HostFailed{text_of(e.code, e.text) + " (check SES_RELAY_USER / PASSWORD)"};
      }
    }
    std::string text;
    int code = c.cmd("MAIL FROM:<" + mail_from + ">", text);
    if (code >= 400) {
      std::string kind = code >= 500 ? "perm" : "temp";
      for (auto& r : rcpts) results.set(r, Result{kind, text_of(code, text), ip});
      return results;
    }
    std::vector<std::string> accepted;
    for (auto& r : rcpts) {
      code = c.cmd("RCPT TO:<" + r + ">", text);
      if (code == 250 || code == 251 || code == 252) accepted.push_back(r);
      else results.set(r, Result{code >= 500 ? "perm" : "temp", text_of(code, text), ip});
    }
    if (!accepted.empty()) {
      code = c.cmd("DATA", text);
      if (code == 354) {
        std::string q;
        q.reserve(raw.size() + 64);
        bool bol = true;
        for (char ch : raw) {
          if (bol && ch == '.') q += '.';
          q += ch;
          bol = ch == '\n';
        }
        if (!ends_with(q, "\r\n")) q += "\r\n";
        q += ".\r\n";
        if (!c.conn.write_all(q)) throw Disconnected{"Server not connected"};
        code = c.reply(text);
      }
      std::string kind = code == 250 ? "ok" : (code >= 500 ? "perm" : "temp");
      for (auto& r : accepted) results.set(r, Result{kind, text_of(code, text), ip});
    }
    try {
      c.cmd("QUIT", text);
    } catch (const Disconnected&) {
    }
    return results;
  } catch (const Disconnected& e) {
    throw HostFailed{"421 4.4.2 " + host + ": " + e.message};
  }
}

Results relay(const std::vector<std::string>& rcpts, const std::string& mail_from, const std::string& raw,
              const std::string& tls_policy) {
  try {
    return session(cfg.relay_host, cfg.relay_port, rcpts, mail_from, raw, cfg.relay_tls,
                   tls_policy == "REQUIRE" || (cfg.relay_tls == "starttls" && !cfg.relay_user.empty()),
                   cfg.relay_tls_verify, cfg.relay_user, cfg.relay_password);
  } catch (const HostFailed& e) {
    Results out;
    for (auto& r : rcpts) out.set(r, Result{"temp", e.message, ""});
    return out;
  }
}

Results direct(const std::string& domain, const std::vector<std::string>& rcpts, const std::string& mail_from,
               const std::string& raw, const std::string& tls_policy) {
  Results out;
  std::vector<std::pair<int, std::string>> hosts;
  try {
    hosts = dns_mx(domain);
  } catch (const DnsError& e) {
    for (auto& r : rcpts) {
      if (e.kind == "HOST_NOT_FOUND")
        out.set(r, Result{"perm", "550 5.1.2 Host or domain name not found: " + domain, ""});
      else if (e.kind == "TYPE_NOT_FOUND")
        out.set(r, Result{"perm", "556 5.1.10 " + domain + " does not accept mail (null MX)", ""});
      else
        out.set(r, Result{"temp", "451 4.4.3 DNS lookup of " + domain + " failed: " + e.message, ""});
    }
    return out;
  }
  std::string last = "451 4.4.1 No MX host of " + domain + " answered";
  for (size_t i = 0; i < hosts.size() && i < 5; ++i) {
    try {
      return session(hosts[i].second, cfg.direct_port, rcpts, mail_from, raw, "opportunistic", tls_policy == "REQUIRE",
                     false);
    } catch (const HostFailed& e) {
      last = e.message;
    }
  }
  for (auto& r : rcpts) out.set(r, Result{"temp", last, ""});
  return out;
}

std::string enhanced(const std::string& response) {
  std::vector<std::string> parts = split_ws(response);
  if (parts.size() > 1 && std::count(parts[1].begin(), parts[1].end(), '.') == 2) {
    std::string digits = replace_all(parts[1], ".", "");
    if (!digits.empty() && std::all_of(digits.begin(), digits.end(), [](char c) { return std::isdigit(static_cast<unsigned char>(c)); }))
      return parts[1];
  }
  return "";
}

std::string str_or(const Json& v, const std::string& def = "") { return truthy(v) ? py_str(v) : def; }

void record(const std::string& message_id, const Results& results, const std::vector<std::string>& complaints) {
  Store& store = db();
  double ts = now();
  std::lock_guard<std::recursive_mutex> guard(store.lock);
  auto mit = store.messages.find(message_id);
  if (mit == store.messages.end()) return;
  Json& rec = mit->second;
  Json reasons;
  auto csit = store.configuration_sets.find(str_or(rec.get("ConfigurationSetName")));
  if (csit != store.configuration_sets.end() && !csit->second.get("SuppressedReasons").is_null())
    reasons = csit->second.get("SuppressedReasons");
  else
    reasons = truthy(store.account.get("SuppressedReasons")) ? store.account.get("SuppressedReasons") : Json::array();
  bool suppress_bounces = false;
  if (reasons.is_arr())
    for (auto& r : reasons.arr())
      if (r.is_str() && r.s() == "BOUNCE") suppress_bounces = true;
  std::map<std::pair<std::string, std::string>, std::vector<std::string>> groups;
  bool any_perm = false;
  for (auto& kv : results.items) {
    const std::string& rcpt = kv.first;
    const Result& res = kv.second;
    Json& st = rec["Recipients"][rcpt];
    long long attempts = static_cast<long long>(st.get("Attempts").num()) + (res.kind == "suppressed" ? 0 : 1);
    st["Attempts"] = attempts;
    st["LastAttempt"] = ts;
    st["Response"] = res.response;
    if (!res.ip.empty()) st["RemoteMtaIp"] = res.ip;
    if (res.kind == "ok") {
      st["Status"] = "DELIVERED";
      st.erase("NextAttempt");
      groups[{"Delivery", res.response + std::string("\0", 1) + res.ip}].push_back(rcpt);
    } else if (res.kind == "perm" || res.kind == "suppressed") {
      st["Status"] = "BOUNCED";
      st.erase("NextAttempt");
      groups[{res.kind == "perm" ? "Bounce" : "Suppressed", res.response}].push_back(rcpt);
      if (res.kind == "perm") any_perm = true;
      if (res.kind == "perm" && suppress_bounces && domain_of(rcpt) != SIMULATOR) {
        Json entry = Json::object();
        entry["EmailAddress"] = rcpt;
        entry["Reason"] = "BOUNCE";
        entry["LastUpdateTime"] = ts;
        entry["MessageId"] = message_id;
        entry["FeedbackId"] = message_id;
        store.suppressed[lower(rcpt)] = entry;
      }
    } else {
      double retry_at = ts + DELAYS[std::min<long long>(std::max<long long>(attempts - 1, 0), 4)];
      double deadline = rec.has("Deadline") ? rec.get("Deadline").num() : retry_at;
      if (retry_at > deadline) {
        st["Status"] = "BOUNCED";
        st.erase("NextAttempt");
        groups[{"Expired", res.response}].push_back(rcpt);
      } else {
        st["Status"] = "DELAYED";
        st["NextAttempt"] = retry_at;
        groups[{"DeliveryDelay", res.response}].push_back(rcpt);
      }
    }
  }
  for (auto& g : groups) {
    const std::string& kind = g.first.first;
    const std::string& key = g.first.second;
    std::string response = key.substr(0, key.find('\0'));
    std::string status = enhanced(response);
    Json d = Json::object();
    if (kind == "Delivery") {
      d["SmtpResponse"] = response;
      d["RemoteMtaIp"] = key.substr(key.find('\0') + 1);
      add_event(rec, "Delivery", g.second, d);
    } else if (kind == "Bounce") {
      d["BounceType"] = "Permanent";
      d["BounceSubType"] = "General";
      d["Status"] = status.empty() ? "5.0.0" : status;
      d["DiagnosticCode"] = "smtp; " + response;
      add_event(rec, "Bounce", g.second, d);
    } else if (kind == "Suppressed") {
      d["BounceType"] = "Permanent";
      d["BounceSubType"] = "OnAccountSuppressionList";
      d["Status"] = "5.1.1";
      d["DiagnosticCode"] = response;
      add_event(rec, "Bounce", g.second, d);
    } else if (kind == "Expired") {
      d["BounceType"] = "Undetermined";
      d["BounceSubType"] = "Undetermined";
      d["Status"] = status.empty() ? "4.4.7" : status;
      d["DiagnosticCode"] = "Delivery expired: " + response;
      add_event(rec, "Bounce", g.second, d);
    } else {
      d["DelayType"] = "TransientCommunicationFailure";
      d["Status"] = status.empty() ? "4.0.0" : status;
      d["DiagnosticCode"] = response;
      d["ExpirationTime"] = rec.get("Deadline");
      add_event(rec, "DeliveryDelay", g.second, d);
    }
  }
  for (auto& r : complaints) {
    Json d = Json::object();
    d["FeedbackType"] = "abuse";
    add_event(rec, "Complaint", {r}, d);
  }
  rec["Status"] = overall(rec);
  store.save_message(message_id);
  if (any_perm) store.save();
}

// ----------------------------------------------------------------------------- the worker

std::mutex cond_mu;
std::condition_variable cond;
bool kicked = false;
std::mutex inflight_mu;
std::set<std::string> inflight;
std::mutex pool_mu;
std::condition_variable pool_cv;
std::deque<std::string> pool_queue;

void run_one(const std::string& message_id) {
  try {
    deliver(message_id);
  } catch (const std::exception& e) {
    log("delivery of " + message_id + " failed: " + e.what());
  } catch (...) {
    log("delivery of " + message_id + " failed");
  }
  {
    std::lock_guard<std::mutex> lock(inflight_mu);
    inflight.erase(message_id);
  }
  wake_delivery();
}

void pool_thread() {
  while (true) {
    std::string id;
    {
      std::unique_lock<std::mutex> lock(pool_mu);
      pool_cv.wait(lock, [] { return !pool_queue.empty(); });
      id = std::move(pool_queue.front());
      pool_queue.pop_front();
    }
    run_one(id);
  }
}

std::vector<std::string> due(double& wait) {
  Store& store = db();
  double ts = now();
  std::vector<std::string> out;
  wait = 30.0;
  std::lock_guard<std::recursive_mutex> guard(store.lock);
  std::lock_guard<std::mutex> lock(inflight_mu);
  for (auto& kv : store.messages) {
    std::string status = str_or(kv.second.get("Status"));
    if (!(status == "QUEUED" || status == "DELAYED" || status == "SENDING") || inflight.count(kv.first)) continue;
    bool any = false;
    double first = 0;
    for (auto& r : kv.second.get("Recipients").items()) {
      std::string s = str_or(r.second.get("Status"));
      if (s != "QUEUED" && s != "DELAYED") continue;
      double t = truthy(r.second.get("NextAttempt")) ? r.second.get("NextAttempt").num() : 0;
      if (!any || t < first) first = t;
      any = true;
    }
    if (!any) continue;
    if (first <= ts) {
      out.push_back(kv.first);
      inflight.insert(kv.first);
    } else {
      wait = std::min(wait, first - ts);
    }
  }
  return out;
}

void loop() {
  double last_purge = 0;
  while (true) {
    double wait = 30.0;
    {
      std::lock_guard<std::mutex> lock(cond_mu);
      kicked = false;
    }
    try {
      for (auto& id : due(wait)) {
        std::lock_guard<std::mutex> lock(pool_mu);
        pool_queue.push_back(id);
        pool_cv.notify_one();
      }
      if (time_now() - last_purge > 3600) {
        last_purge = time_now();
        int gone = db().purge();
        if (gone) log("removed " + std::to_string(gone) + " messages older than the retention period");
      }
    } catch (const std::exception& e) {
      log(std::string("delivery worker error: ") + e.what());
    }
    std::unique_lock<std::mutex> lock(cond_mu);
    if (!kicked)
      cond.wait_for(lock, std::chrono::milliseconds(static_cast<long long>(std::max(0.05, std::min(wait, 30.0)) * 1000)));
    kicked = false;
  }
}

}  // namespace

void wake_delivery() {
  std::lock_guard<std::mutex> lock(cond_mu);
  kicked = true;
  cond.notify_all();
}

void start_delivery_worker() {
  for (int i = 0; i < cfg.delivery_threads; ++i) std::thread(pool_thread).detach();
  std::thread(loop).detach();
}

void deliver(const std::string& message_id) {
  Store& store = db();
  double ts = now();
  std::vector<std::string> due_rcpts;
  std::string mail_from, mode, tls_policy;
  {
    std::lock_guard<std::recursive_mutex> guard(store.lock);
    auto it = store.messages.find(message_id);
    if (it == store.messages.end()) return;
    const Json& rec = it->second;
    for (auto& kv : rec.get("Recipients").items()) {
      std::string s = str_or(kv.second.get("Status"));
      double next = truthy(kv.second.get("NextAttempt")) ? kv.second.get("NextAttempt").num() : 0;
      if ((s == "QUEUED" || s == "DELAYED") && next <= ts) due_rcpts.push_back(kv.first);
    }
    mail_from = str_or(rec.get("MailFrom"), py_str(rec.get("From")));
    mode = str_or(rec.get("Delivery"), cfg.delivery);
    tls_policy = str_or(rec.get("TlsPolicy"), "OPTIONAL");
  }
  if (due_rcpts.empty()) return;
  std::string raw = store.raw(message_id);
  Results results;
  std::vector<std::string> real, complaints;
  for (auto& r : due_rcpts) {
    if (domain_of(r) != SIMULATOR) {
      real.push_back(r);
      continue;
    }
    std::string box = lower(r.substr(0, r.find('@')));
    if (box == "bounce") {
      results.set(r, Result{"perm", "550 5.1.1 user unknown (mailbox simulator)", ""});
    } else if (box == "suppressionlist") {
      results.set(r, Result{"suppressed", "550 5.1.1 recipient is on the suppression list (mailbox simulator)", ""});
    } else {
      results.set(r, Result{"ok", "250 2.6.0 Message received (mailbox simulator)", ""});
      if (box == "complaint") complaints.push_back(r);
    }
  }
  if (!real.empty()) {
    if (mode == "capture") {
      for (auto& r : real)
        results.set(r, Result{"ok", "250 2.0.0 Captured: kept on the server, not sent (SES_DELIVERY=capture)", ""});
    } else if (mode == "relay") {
      results.update(relay(real, mail_from, raw, tls_policy));
    } else {
      std::set<std::string> domains;
      for (auto& r : real) domains.insert(domain_of(r));
      for (auto& d : domains) {
        std::vector<std::string> mine;
        for (auto& r : real)
          if (domain_of(r) == d) mine.push_back(r);
        results.update(direct(d, mine, mail_from, raw, tls_policy));
      }
    }
  }
  record(message_id, results, complaints);
}

}  // namespace ses
