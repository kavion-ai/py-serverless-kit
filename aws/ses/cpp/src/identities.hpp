// Identities (domains and addresses), their verification (SES_VERIFY) and DKIM, the DNS checks, and which identity
// lets an address send (sesserver/identities.py).
#pragma once

#include <atomic>
#include <memory>
#include <string>
#include <vector>

#include "json.hpp"
#include "rsa.hpp"

namespace ses {

std::string arn(const std::string& kind, const std::string& name);
std::string identity_kind(const std::string& name);  // EMAIL_ADDRESS or DOMAIN; throws ApiError
std::string normalize_identity(const Json& name);
Json new_identity(const std::string& name, const Json& dkim);
void set_dkim(Json& rec, const Json& attrs);
std::vector<std::string> domains_up(const std::string& domain);
bool identity_verified(const std::string& name);
std::string sending_identity(const std::string& addr);  // "" when none
std::string status_of(const Json& rec);

struct Signer {
  std::string domain, selector;
  Key key;
};
std::unique_ptr<Signer> dkim_signer(const std::string& addr);

Json check_identity(const std::string& name);  // looks the records up now (does its own locking)
std::vector<std::string> pending_identities();
void check_later(const std::string& name);
void checker_loop();
Json dns_records(const Json& rec);
Json set_verified(const std::string& name, bool value);

}  // namespace ses
