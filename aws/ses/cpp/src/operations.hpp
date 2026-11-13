// The API operations, in the shape of the SES v2 API (sesserver/operations.py): the v2 REST routes call them
// directly, the v1 Query API translates to and from them, and the console calls them (and the console-only
// operations) through POST /ui/api/<Operation>.
#pragma once

#include <string>
#include <utility>
#include <vector>

#include "json.hpp"

namespace ses {

struct Ctx {
  std::string caller, region, source_ip, user;
};

// Runs an operation with the store lock held (CheckEmailIdentity locks as it goes). Throws ApiError.
Json run(const std::string& name, Json params, const Ctx& ctx);
// The same, for a caller that already holds the lock.
Json run_unlocked(const std::string& name, Json& params, const Ctx& ctx);

// Shared with the v1 Query API
std::pair<std::vector<Json>, std::string> page(const std::vector<Json>& items, const Json& params, int def = 100,
                                               int limit = 1000);
Json create_identity(const std::string& name, const Json& params, bool idempotent);
Json account_out(const Ctx& ctx);
Json dkim_out(const Json& rec);

struct SendArgs {
  std::string operation;
  Ctx ctx;
  std::string source;
  std::vector<std::string> to, cc, bcc, reply_to;
  Json content;
  std::string configuration_set;
  Json tags;
  std::string return_path;
  bool has_envelope = false;
  std::vector<std::string> envelope;
};
std::string send_message(const SendArgs& args);

}  // namespace ses
