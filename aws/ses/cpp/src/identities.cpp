#include "identities.hpp"

#include <chrono>
#include <stdexcept>
#include <thread>

#include "config.hpp"
#include "dns.hpp"
#include "errors.hpp"
#include "settings.hpp"
#include "store.hpp"
#include "util.hpp"

namespace ses {

namespace {

const double PENDING_FOR = 72 * 3600;
const int RECHECK = 600;

std::string str_or(const Json& v, const std::string& def = "") { return truthy(v) ? py_str(v) : def; }

std::string dkim_key_of(const std::string& record) {
  std::string p;
  for (const std::string& part : split(record, ';')) {
    std::string item = strip(part);
    size_t eq = item.find('=');
    std::string k = strip(eq == std::string::npos ? item : item.substr(0, eq));
    std::string v = eq == std::string::npos ? "" : item.substr(eq + 1);
    if (k == "p") p = join(split_ws(v), "");
  }
  return p;
}

}  // namespace

std::string arn(const std::string& kind, const std::string& name) {
  return "arn:aws:ses:" + cfg.region + ":" + cfg.account + ":" + kind + "/" + name;
}

std::string identity_kind(const std::string& name) {
  if (name.find('@') != std::string::npos) {
    if (!is_email(name)) throw bad_request("Invalid email address <" + name + ">.");
    return "EMAIL_ADDRESS";
  }
  if (!is_domain(name)) throw bad_request("Invalid domain name <" + name + ">.");
  return "DOMAIN";
}

std::string normalize_identity(const Json& name) {
  std::string text = strip(truthy(name) ? py_str(name) : "");
  size_t at = text.rfind('@');
  if (at != std::string::npos) return text.substr(0, at) + "@" + lower(text.substr(at + 1));
  return rstrip(lower(text), ".");
}

Json new_identity(const std::string& name, const Json& dkim) {
  std::string kind = identity_kind(name);
  double ts = now();
  bool auto_ok = cfg.verify == "auto" || cfg.verify == "off";
  Json rec = Json::object();
  rec["IdentityName"] = name;
  rec["IdentityType"] = kind;
  rec["CreatedTimestamp"] = ts;
  rec["VerificationStatus"] = auto_ok ? "SUCCESS" : "PENDING";
  Json info = Json::object();
  info["LastCheckedTimestamp"] = ts;
  if (auto_ok) info["LastSuccessTimestamp"] = ts;
  rec["VerificationInfo"] = info;
  rec["FeedbackForwardingStatus"] = true;
  rec["Tags"] = Json::array();
  rec["Policies"] = Json::object();
  if (kind == "DOMAIN") {
    rec["VerificationToken"] = token();
    set_dkim(rec, dkim);
  }
  return rec;
}

void set_dkim(Json& rec, const Json& attrs_in) {
  Json attrs = attrs_in.is_obj() ? attrs_in : Json::object();
  std::string origin = str_or(attrs.get("DomainSigningAttributesOrigin"),
                              truthy(attrs.get("DomainSigningPrivateKey")) ? "EXTERNAL" : "AWS_SES");
  std::string length = str_or(attrs.get("NextSigningKeyLength"), "RSA_2048_BIT");
  std::string sel;
  Key key;
  if (origin == "EXTERNAL") {
    sel = str_or(attrs.get("DomainSigningSelector"));
    if (sel.empty() || !is_domain(sel + ".x") || sel.find('.') != std::string::npos)
      throw bad_request("DomainSigningSelector must be a DNS label such as 'mail2026'.");
    try {
      key = Key::load(str_or(attrs.get("DomainSigningPrivateKey")));
    } catch (const std::exception& e) {
      throw bad_request(std::string("DomainSigningPrivateKey is not an RSA private key in base64: ") + e.what());
    }
    if (key.bits() != 1024 && key.bits() != 2048) throw bad_request("The DKIM key must be a 1024 or 2048 bit RSA key.");
    length = "RSA_" + std::to_string(key.bits()) + "_BIT";
  } else {
    origin = "AWS_SES";
    sel = selector();
    key = Key::generate(length == "RSA_1024_BIT" ? 1024 : 2048);
  }
  Json dk = Json::object();
  dk["SigningEnabled"] = true;
  dk["Status"] = cfg.dkim_check ? "PENDING" : "SUCCESS";
  dk["Selector"] = sel;
  dk["PrivateKey"] = key.private_b64();
  dk["PublicKey"] = key.public_b64();
  dk["Origin"] = origin;
  dk["CurrentSigningKeyLength"] = length;
  dk["NextSigningKeyLength"] = length;
  dk["LastKeyGenerationTimestamp"] = now();
  rec["Dkim"] = dk;
}

std::vector<std::string> domains_up(const std::string& domain) {
  std::vector<std::string> parts = split(domain, '.');
  std::vector<std::string> out;
  for (size_t i = 0; i + 1 < parts.size(); ++i)
    out.push_back(join(std::vector<std::string>(parts.begin() + static_cast<long>(i), parts.end()), "."));
  return out;
}

static bool is_success(const Json* rec) {
  return rec && rec->get("VerificationStatus").is_str() && rec->get("VerificationStatus").s() == "SUCCESS";
}

static const Json* find_identity(const std::string& name) {
  Store& store = db();
  auto it = store.identities.find(name);
  return it == store.identities.end() ? nullptr : &it->second;
}

bool identity_verified(const std::string& name) {
  if (cfg.verify == "off") return true;
  std::lock_guard<std::recursive_mutex> guard(db().lock);
  if (is_success(find_identity(name))) return true;
  std::string domain = name.find('@') != std::string::npos ? domain_of(name) : name;
  for (auto& d : domains_up(domain))
    if (d != name && is_success(find_identity(d))) return true;
  return false;
}

std::string sending_identity(const std::string& addr) {
  std::lock_guard<std::recursive_mutex> guard(db().lock);
  if (is_success(find_identity(addr))) return addr;
  for (auto& d : domains_up(domain_of(addr)))
    if (is_success(find_identity(d))) return d;
  return "";
}

std::string status_of(const Json& rec) {
  std::string status = py_str(rec.get("VerificationStatus"));
  if (status != "SUCCESS" && py_str(rec.get("IdentityType")) == "EMAIL_ADDRESS" &&
      identity_verified(py_str(rec.get("IdentityName"))))
    return "SUCCESS";
  return status;
}

std::unique_ptr<Signer> dkim_signer(const std::string& addr) {
  std::lock_guard<std::recursive_mutex> guard(db().lock);
  for (auto& d : domains_up(domain_of(addr))) {
    const Json* rec = find_identity(d);
    if (!rec) continue;
    const Json& dk = rec->get("Dkim");
    if (truthy(dk) && truthy(dk.get("SigningEnabled")) && dk.get("Status").is_str() && dk.get("Status").s() == "SUCCESS") {
      std::unique_ptr<Signer> s(new Signer{d, py_str(dk.get("Selector")), Key::load(py_str(dk.get("PrivateKey")))});
      return s;
    }
  }
  return nullptr;
}

Json check_identity(const std::string& name) {
  Store& store = db();
  std::string token_;
  Json dk;
  {
    std::lock_guard<std::recursive_mutex> guard(store.lock);
    const Json* rec = find_identity(name);
    if (!rec || py_str(rec->get("IdentityType")) != "DOMAIN") return rec ? *rec : Json::object();
    token_ = str_or(rec->get("VerificationToken"));
    dk = rec->get("Dkim").is_obj() ? rec->get("Dkim") : Json::object();
  }
  double ts = now();
  bool found_token = false, found_dkim = false;
  std::string error;
  try {
    for (auto& t : dns_txt("_amazonses." + name))
      if (strip(t) == token_) found_token = true;
  } catch (const DnsError& e) {
    error = e.kind;
  }
  if (dk.size()) {
    try {
      std::vector<std::string> records = dns_txt(py_str(dk.get("Selector")) + "._domainkey." + name);
      for (auto& t : records)
        if (dkim_key_of(t) == py_str(dk.get("PublicKey"))) found_dkim = true;
      if (!found_dkim && error.empty()) error = records.empty() ? "TYPE_NOT_FOUND" : "INVALID_VALUE";
    } catch (const DnsError& e) {
      if (error.empty()) error = e.kind;
    }
  }
  std::lock_guard<std::recursive_mutex> guard(store.lock);
  auto it = store.identities.find(name);
  if (it == store.identities.end()) return Json::object();
  Json& rec = it->second;
  Json& info = rec["VerificationInfo"];
  if (!info.is_obj()) info = Json::object();
  info["LastCheckedTimestamp"] = ts;
  bool expired = ts - rec.get("CreatedTimestamp").num() > PENDING_FOR;
  if (found_token || found_dkim) {
    info["LastSuccessTimestamp"] = ts;
    info.erase("ErrorType");
    if (cfg.verify == "dns" && py_str(rec.get("VerificationStatus")) != "SUCCESS") {
      rec["VerificationStatus"] = "SUCCESS";
      log("identity verified: " + name);
    }
  } else if (!error.empty()) {
    info["ErrorType"] = error;
    if (cfg.verify == "dns" && py_str(rec.get("VerificationStatus")) == "PENDING" && expired)
      rec["VerificationStatus"] = "FAILED";
  }
  if (truthy(rec.get("Dkim"))) {
    Json& d = rec["Dkim"];
    if (found_dkim) {
      if (py_str(d.get("Status")) != "SUCCESS") log("DKIM record found, signing mail from " + name);
      d["Status"] = "SUCCESS";
    } else if (py_str(d.get("Status")) != "SUCCESS") {
      d["Status"] = expired ? "FAILED" : (error == "DNS_SERVER_ERROR" ? "TEMPORARY_FAILURE" : "PENDING");
    }
  }
  store.save();
  return rec;
}

std::vector<std::string> pending_identities() {
  Store& store = db();
  std::lock_guard<std::recursive_mutex> guard(store.lock);
  std::vector<std::string> out;
  for (auto& kv : store.identities) {
    const Json& r = kv.second;
    if (py_str(r.get("IdentityType")) != "DOMAIN") continue;
    std::string ds = r.get("Dkim").is_obj() ? str_or(r.get("Dkim").get("Status")) : "";
    if (ds == "PENDING" || ds == "TEMPORARY_FAILURE" ||
        (cfg.verify == "dns" && py_str(r.get("VerificationStatus")) == "PENDING"))
      out.push_back(kv.first);
  }
  return out;
}

static void safe_check(const std::string& name) {
  try {
    check_identity(name);
  } catch (const std::exception& e) {
    log("DNS check of " + name + " failed: " + e.what());
  }
}

void check_later(const std::string& name) {
  if (cfg.dkim_check) std::thread(safe_check, name).detach();
}

void checker_loop() {
  while (true) {
    std::this_thread::sleep_for(std::chrono::seconds(RECHECK));
    if (!cfg.dkim_check) continue;
    for (auto& name : pending_identities()) safe_check(name);
  }
}

Json dns_records(const Json& rec) {
  Json out = Json::array();
  if (py_str(rec.get("IdentityType")) != "DOMAIN") return out;
  std::string name = py_str(rec.get("IdentityName"));
  auto row = [](const std::string& type, const std::string& n, const std::string& value, const std::string& purpose,
                const Json& status) {
    Json r = Json::object();
    r["Type"] = type;
    r["Name"] = n;
    r["Value"] = value;
    r["Purpose"] = purpose;
    r["Status"] = status;
    return r;
  };
  const Json& dk = rec.get("Dkim");
  if (truthy(dk))
    out.push(row("TXT", py_str(dk.get("Selector")) + "._domainkey." + name, "v=DKIM1; k=rsa; p=" + py_str(dk.get("PublicKey")),
                 "DKIM", dk.get("Status")));
  out.push(row("TXT", "_amazonses." + name, str_or(rec.get("VerificationToken")), "Verification",
               rec.get("VerificationStatus")));
  Json delivery = delivery_effective();
  std::string helo = py_str(delivery.get("HeloName"));
  std::string spf = py_str(delivery.get("Mode")) == "relay"
                        ? "v=spf1 include:<your relay provider's SPF domain> ~all  (relay: " +
                              py_str(delivery.get("RelayHost")) + ")"
                        : "v=spf1 a:" + helo + " ~all";
  out.push(row("TXT", name, spf, "SPF (recommended)", ""));
  out.push(row("TXT", "_dmarc." + name, "v=DMARC1; p=none; rua=mailto:postmaster@" + name, "DMARC (recommended)", ""));
  const Json& mf = rec.get("MailFrom");
  std::string mail_from = mf.is_obj() ? str_or(mf.get("MailFromDomain")) : "";
  if (!mail_from.empty()) {
    out.push(row("MX", mail_from, "10 " + helo, "Custom MAIL FROM",
                 mf.has("MailFromDomainStatus") ? mf.get("MailFromDomainStatus") : Json("")));
    out.push(row("TXT", mail_from, spf, "Custom MAIL FROM (SPF)", ""));
  }
  return out;
}

Json set_verified(const std::string& name, bool value) {
  Store& store = db();
  std::lock_guard<std::recursive_mutex> guard(store.lock);
  Json& rec = store.identities.at(name);
  rec["VerificationStatus"] = value ? "SUCCESS" : "PENDING";
  Json& info = rec["VerificationInfo"];
  if (!info.is_obj()) info = Json::object();
  info["LastCheckedTimestamp"] = now();
  if (value) info["LastSuccessTimestamp"] = now();
  store.save();
  return rec;
}

}  // namespace ses
