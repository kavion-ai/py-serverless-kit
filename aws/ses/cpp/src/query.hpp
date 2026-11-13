// The SES v1 API (POST / with Action=...&Version=2010-12-01, answers in XML), translated to and from the operations
// (sesserver/query.py).
#pragma once

#include <string>
#include <utility>

#include "errors.hpp"
#include "operations.hpp"

namespace ses {

std::pair<int, std::string> query_handle(const std::string& body, const std::string& query, const Ctx& ctx);
std::pair<int, std::string> query_error(const ApiError& e);

}  // namespace ses
