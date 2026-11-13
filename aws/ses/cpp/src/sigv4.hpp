// AWS Signature Version 4 (the check every API request passes) and SES SMTP passwords (sesserver/sigv4.py).
#pragma once

#include <map>
#include <string>
#include <utility>

namespace ses {

// (access key id, region) of a correctly signed request, else ApiError (403) as AWS answers it. `headers` are
// lower-case names with the values of repeated headers joined by ",". `raw_path` is the path as sent.
std::pair<std::string, std::string> verify_sigv4(const std::string& method, const std::string& raw_path,
                                                 const std::string& query,
                                                 const std::map<std::string, std::string>& headers,
                                                 const std::string& body);
std::string smtp_password(const std::string& secret, const std::string& region);
bool check_smtp_login(const std::string& user, const std::string& password);

}  // namespace ses
