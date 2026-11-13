#include "sigv4.hpp"

#include <algorithm>
#include <cmath>
#include <ctime>
#include <set>
#include <vector>

#include "config.hpp"
#include "errors.hpp"
#include "rsa.hpp"
#include "util.hpp"

namespace ses {

namespace {

ApiError forbidden(const std::string& code, const std::string& message) { return ApiError(code, message, 403, code); }

bool no_comma_ws(const std::string& s) {
  if (s.empty()) return false;
  for (char c : s)
    if (c == ',' || c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' || c == '\v') return false;
  return true;
}

// ^AWS4-HMAC-SHA256\s+Credential=([^,\s]+),\s*SignedHeaders=([^,\s]+),\s*Signature=([0-9a-f]{64})$
bool parse_auth(const std::string& auth, std::string& credential, std::string& signed_headers,
                std::string& signature) {
  const std::string prefix = "AWS4-HMAC-SHA256";
  if (!starts_with(auth, prefix)) return false;
  size_t pos = prefix.size();
  size_t ws = pos;
  while (pos < auth.size() && std::isspace(static_cast<unsigned char>(auth[pos]))) ++pos;
  if (pos == ws) return false;
  auto field = [&](const std::string& name, std::string& out, bool last) {
    if (auth.compare(pos, name.size(), name) != 0) return false;
    pos += name.size();
    size_t end = last ? auth.size() : auth.find(',', pos);
    if (end == std::string::npos) return false;
    out = auth.substr(pos, end - pos);
    pos = end;
    if (!last) {
      ++pos;
      while (pos < auth.size() && std::isspace(static_cast<unsigned char>(auth[pos]))) ++pos;
    }
    return true;
  };
  if (!field("Credential=", credential, false) || !no_comma_ws(credential)) return false;
  if (!field("SignedHeaders=", signed_headers, false) || !no_comma_ws(signed_headers)) return false;
  if (!field("Signature=", signature, true)) return false;
  if (signature.size() != 64) return false;
  for (char c : signature)
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
  return true;
}

bool parse_amz_date(const std::string& s, double& when) {
  if (s.size() != 16 || s[8] != 'T' || s[15] != 'Z') return false;
  for (size_t i = 0; i < 15; ++i)
    if (i != 8 && !std::isdigit(static_cast<unsigned char>(s[i]))) return false;
  struct tm tm = {};
  tm.tm_year = std::stoi(s.substr(0, 4)) - 1900;
  tm.tm_mon = std::stoi(s.substr(4, 2)) - 1;
  tm.tm_mday = std::stoi(s.substr(6, 2));
  tm.tm_hour = std::stoi(s.substr(9, 2));
  tm.tm_min = std::stoi(s.substr(11, 2));
  tm.tm_sec = std::stoi(s.substr(13, 2));
  if (tm.tm_mon < 0 || tm.tm_mon > 11 || tm.tm_mday < 1 || tm.tm_mday > 31 || tm.tm_hour > 23 || tm.tm_min > 59 ||
      tm.tm_sec > 61)
    return false;
  when = static_cast<double>(timegm(&tm));
  return true;
}

}  // namespace

std::pair<std::string, std::string> verify_sigv4(const std::string& method, const std::string& raw_path,
                                                 const std::string& query,
                                                 const std::map<std::string, std::string>& headers,
                                                 const std::string& body) {
  auto header = [&](const std::string& name) -> std::string {
    auto it = headers.find(name);
    return it == headers.end() ? "" : it->second;
  };
  std::string auth = header("authorization");
  if (auth.empty()) throw forbidden("MissingAuthenticationToken", "Request is missing Authentication Token");
  std::string credential, signed_headers, signature;
  if (!parse_auth(strip(auth), credential, signed_headers, signature))
    throw forbidden("IncompleteSignature",
                    "Authorization header requires Credential, SignedHeaders and Signature (AWS4-HMAC-SHA256).");
  std::vector<std::string> parts = split(credential, '/');
  if (parts.size() != 5 || parts[4] != "aws4_request") throw forbidden("IncompleteSignature", "The Credential is not valid.");
  const std::string &access_key = parts[0], &day = parts[1], &region = parts[2], &service = parts[3];
  auto cred = cfg.credentials.find(access_key);
  if (cred == cfg.credentials.end())
    throw forbidden("InvalidClientTokenId", "The security token included in the request is invalid.");
  std::string amz_date = header("x-amz-date");
  double when;
  if (!parse_amz_date(amz_date, when)) throw forbidden("IncompleteSignature", "X-Amz-Date is missing or not valid.");
  if (std::fabs(time_now() - when) > SKEW)
    throw forbidden("SignatureDoesNotMatch", "Signature expired: " + amz_date +
                                                 " is now earlier or later than 15 minutes from the server's time.");
  if (day != amz_date.substr(0, 8) || (service != "ses" && service != "email"))
    throw forbidden("SignatureDoesNotMatch", "The credential scope does not match the request.");
  std::vector<std::string> names = split(signed_headers, ';');
  bool has_host = std::find(names.begin(), names.end(), "host") != names.end();
  bool all_sent = std::all_of(names.begin(), names.end(), [&](const std::string& n) { return headers.count(n) > 0; });
  if (!has_host || !all_sent)
    throw forbidden("SignatureDoesNotMatch", "SignedHeaders must include host and only headers that were sent.");
  std::string payload_hash = hex(sha256(body));
  std::string claimed = header("x-amz-content-sha256");
  if (!claimed.empty() && claimed != payload_hash && claimed != "UNSIGNED-PAYLOAD")
    throw forbidden("SignatureDoesNotMatch", "x-amz-content-sha256 does not match the request body.");
  std::vector<std::pair<std::string, std::string>> pairs;
  for (auto& kv : parse_qsl(query)) pairs.emplace_back(quote(kv.first, ""), quote(kv.second, ""));
  std::sort(pairs.begin(), pairs.end());
  std::vector<std::string> qparts;
  for (auto& kv : pairs) qparts.push_back(kv.first + "=" + kv.second);
  std::string canon_headers;
  for (auto& n : names) canon_headers += n + ":" + join(split_ws(header(n)), " ") + "\n";
  std::string canonical = upper(method) + "\n" + quote(raw_path.empty() ? "/" : raw_path, "/~") + "\n" +
                          join(qparts, "&") + "\n" + canon_headers + "\n" + signed_headers + "\n" +
                          (claimed.empty() ? payload_hash : claimed);
  std::string scope = day + "/" + region + "/" + service + "/aws4_request";
  std::string to_sign = "AWS4-HMAC-SHA256\n" + amz_date + "\n" + scope + "\n" + hex(sha256(canonical));
  std::string key = "AWS4" + cred->second;
  for (const std::string& part : {day, region, service, std::string("aws4_request")}) key = hmac_sha256(key, part);
  std::string expected = hex(hmac_sha256(key, to_sign));
  if (!const_eq(expected, signature))
    throw forbidden("SignatureDoesNotMatch",
                    "The request signature we calculated does not match the signature you provided. Check your AWS "
                    "Secret Access Key and signing method.");
  return {access_key, region};
}

std::string smtp_password(const std::string& secret, const std::string& region) {
  std::string key = "AWS4" + secret;
  for (const std::string& part : {std::string("11111111"), region, std::string("ses"), std::string("aws4_request"),
                                  std::string("SendRawEmail")})
    key = hmac_sha256(key, part);
  return b64encode(std::string("\x04", 1) + key);
}

bool check_smtp_login(const std::string& user, const std::string& password) {
  auto cred = cfg.credentials.find(user);
  if (cred == cfg.credentials.end()) {
    const_eq(password, std::string(44, 'x'));
    return false;
  }
  if (const_eq(password, cred->second)) return true;
  std::string raw;
  if (!b64decode_strict(password, raw)) return false;
  if (raw.size() != 33 || raw[0] != 4) return false;
  std::set<std::string> regions = {cfg.region,      "us-east-1",      "us-east-2",      "us-west-1",
                                   "us-west-2",     "eu-west-1",      "eu-west-2",      "eu-west-3",
                                   "eu-central-1",  "eu-north-1",     "eu-south-1",     "ap-south-1",
                                   "ap-southeast-1", "ap-southeast-2", "ap-northeast-1", "ap-northeast-2",
                                   "ap-northeast-3", "ca-central-1",   "sa-east-1",      "me-south-1",
                                   "af-south-1",    "il-central-1"};
  bool ok = false;
  for (auto& r : regions)
    if (const_eq(smtp_password(cred->second, r), password)) ok = true;
  return ok;
}

}  // namespace ses
