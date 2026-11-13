// The SES v2 REST API (/v2/email/..., JSON): each route calls an operation; path and query parameters are merged
// into its parameters (sesserver/rest.py).
#pragma once

#include <string>

#include "json.hpp"
#include "operations.hpp"

namespace ses {

bool is_rest(const std::string& path);
Json rest_handle(const std::string& method, const std::string& path, const std::string& query, const std::string& body,
                 const Ctx& ctx);

}  // namespace ses
