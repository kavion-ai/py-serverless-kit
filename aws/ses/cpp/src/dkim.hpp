// DKIM signatures (RFC 6376): rsa-sha256, relaxed/relaxed, the header list Amazon SES signs (sesserver/dkim.py).
#pragma once

#include <string>
#include <utility>
#include <vector>

#include "rsa.hpp"

namespace ses {

using Field = std::pair<std::string, std::string>;  // (lower-case name, the whole field without its last CRLF)

std::string crlf(const std::string& raw);
std::pair<std::string, std::string> split_message(const std::string& raw);  // (header block with final CRLF, body)
std::vector<Field> header_fields(const std::string& head);
std::string dkim_sign(const std::string& raw, const std::string& domain, const std::string& selector, const Key& key);
bool dkim_verify(const std::string& raw, const std::string& public_b64);

}  // namespace ses
