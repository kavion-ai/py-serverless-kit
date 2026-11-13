#include "settings.hpp"

#include <cctype>
#include <cmath>
#include <mutex>

#include "config.hpp"
#include "errors.hpp"
#include "store.hpp"
#include "util.hpp"

namespace ses {

namespace {

bool label_ok(const std::string& l) {
  if (l.empty() || l.size() > 63 || l[0] == '-') return false;
  for (char c : l)
    if (!(std::isalnum(static_cast<unsigned char>(c)) || c == '-')) return false;
  return true;
}

// ^(?!-)[A-Za-z0-9-]{1,63}(\.(?!-)[A-Za-z0-9-]{1,63})*$
bool helo_ok(const std::string& s) {
  for (const std::string& l : split(s, '.'))
    if (!label_ok(l)) return false;
  return true;
}

// ^(?!-)[A-Za-z0-9.-]{1,253}$|^\[?[0-9A-Fa-f:.]{2,45}\]?$
bool host_ok(const std::string& s) {
  bool a = !s.empty() && s.size() <= 253 && s[0] != '-';
  for (char c : s)
    if (!(std::isalnum(static_cast<unsigned char>(c)) || c == '.' || c == '-')) a = false;
  if (a) return true;
  std::string t = s;
  if (!t.empty() && t.front() == '[') t.erase(0, 1);
  if (!t.empty() && t.back() == ']') t.pop_back();
  if (t.size() < 2 || t.size() > 45) return false;
  for (char c : t)
    if (!(std::isxdigit(static_cast<unsigned char>(c)) || c == ':' || c == '.')) return false;
  return true;
}

// int(value); false where Python's int() raises
bool to_int(const Json& v, long long& out) {
  if (v.is_int() && !v.big()) {
    out = v.i();
    return true;
  }
  if (v.is_float() && std::isfinite(v.d())) {
    out = static_cast<long long>(v.d());
    return true;
  }
  if (v.is_bool()) {
    out = v.b();
    return true;
  }
  if (v.is_str()) return parse_py_int(v.s(), out);
  return false;
}

std::string str_or(const Json& v, const std::string& def = "") { return truthy(v) ? py_str(v) : def; }

}  // namespace

Json delivery_environment() {
  Json out = Json::object();
  out["Mode"] = cfg.delivery;
  out["RelayHost"] = cfg.relay_host;
  out["RelayPort"] = cfg.relay_port;
  out["RelayUser"] = cfg.relay_user;
  out["RelayPassword"] = cfg.relay_password;
  out["RelayTls"] = cfg.relay_tls;
  out["RelayTlsVerify"] = cfg.relay_tls_verify;
  out["HeloName"] = cfg.helo_name;
  return out;
}

Json delivery_effective() {
  Json out = delivery_environment();
  std::lock_guard<std::recursive_mutex> guard(db().lock);
  const Json& saved = db().delivery;
  if (!truthy(saved)) {
    out["Source"] = "environment";
    return out;
  }
  for (auto& kv : saved.items()) out[kv.first] = kv.second;
  out["Source"] = "console";
  return out;
}

Json delivery_public(const Json& values) {
  Json out = Json::object();
  for (auto& kv : values.items())
    if (kv.first != "RelayPassword") out[kv.first] = kv.second;
  out["RelayPasswordSet"] = truthy(values.get("RelayPassword"));
  return out;
}

Json delivery_check(const Json& params) {
  std::string mode = lower(str_or(params.get("Mode")));
  if (mode != "capture" && mode != "relay" && mode != "direct")
    throw bad_request("Mode must be capture, relay or direct.");
  Json current = delivery_effective();
  std::string helo = rstrip(lower(strip(str_or(params.get("HeloName"), str_or(current.get("HeloName"))))), ".");
  if (!helo_ok(helo)) throw bad_request("HeloName must be a host name such as mail.example.com.");
  Json out = Json::object();
  out["Mode"] = mode;
  out["HeloName"] = helo;
  if (mode == "relay") {
    std::string host = strip(str_or(params.get("RelayHost")));
    if (host.empty() || !host_ok(host))
      throw bad_request("RelayHost must be the relay's host name or IP address, e.g. smtp.office365.com.");
    long long port = 587;
    if (truthy(params.get("RelayPort")) && !to_int(params.get("RelayPort"), port))
      throw bad_request("RelayPort must be a number.");
    if (port < 1 || port > 65535) throw bad_request("RelayPort must be between 1 and 65535.");
    std::string tls = lower(str_or(params.get("RelayTls"), port == 465 ? "tls" : "starttls"));
    if (tls != "starttls" && tls != "tls" && tls != "none") throw bad_request("RelayTls must be starttls, tls or none.");
    std::string user = strip(str_or(params.get("RelayUser")));
    Json password = params.get("RelayPassword");
    if (password.is_null()) {
      bool same = current.get("RelayHost") == Json(host) && current.get("RelayUser") == Json(user);
      password = same ? current.get("RelayPassword") : Json("");
    }
    std::string pw = str_or(password);
    if (!user.empty() && pw.empty()) throw bad_request("RelayPassword is required with RelayUser.");
    if (!user.empty() && tls == "none")
      throw bad_request(
          "A relay login needs TLS (starttls or tls): the password would cross the network in plain text.");
    const Json& verify = params.get("RelayTlsVerify");
    out["RelayHost"] = host;
    out["RelayPort"] = port;
    out["RelayTls"] = tls;
    out["RelayUser"] = user;
    out["RelayPassword"] = pw;
    out["RelayTlsVerify"] = verify.is_null() ? true : truthy(verify);
  }
  return out;
}

void delivery_save(const Json& values) {
  Store& store = db();
  std::lock_guard<std::recursive_mutex> guard(store.lock);
  store.delivery = values.is_obj() ? values : Json::object();
  store.save();
}

}  // namespace ses
