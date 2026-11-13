// Strings, UTF-8, base64, URLs, files, time, ids and e-mail address helpers (sesserver/util.py and the parts of
// Python's standard library the server relies on: email.utils address parsing, urllib.parse, base64).
#pragma once

#include <string>
#include <utility>
#include <vector>

#include "json.hpp"

namespace ses {

// ----------------------------------------------------------------------------- strings
std::string strip(const std::string& s, const char* chars = " \t\r\n\f\v");
std::string rstrip(const std::string& s, const char* chars = " \t\r\n\f\v");
std::string lstrip(const std::string& s, const char* chars = " \t\r\n\f\v");
std::string lower(std::string s);
std::string upper(std::string s);
std::vector<std::string> split(const std::string& s, char sep);  // str.split(sep)
std::vector<std::string> split_ws(const std::string& s);          // str.split()
std::string join(const std::vector<std::string>& parts, const std::string& sep);
bool starts_with(const std::string& s, const std::string& prefix);
bool ends_with(const std::string& s, const std::string& suffix);
std::string replace_all(std::string s, const std::string& from, const std::string& to);
bool parse_py_int(const std::string& s, long long& out);  // int(s)
bool parse_py_float(const std::string& s, double& out);   // float(s)
std::string py_repr_str(const std::string& s);            // repr(str)
std::string hex(const std::string& bytes);
inline bool utf8_less(const std::string& a, const std::string& b) { return a < b; }

// ----------------------------------------------------------------------------- UTF-8
void append_utf8(std::string& out, unsigned cp);
unsigned next_utf8(const std::string& s, size_t& i);  // U+FFFD for a bad sequence
size_t utf8_len(const std::string& s);
bool valid_utf8(const std::string& s);
std::string sanitize_utf8(const std::string& s);      // bytes.decode("utf-8", "replace")
std::string latin1_to_utf8(const std::string& s);

// ----------------------------------------------------------------------------- base64, URLs
std::string b64encode(const std::string& data);
std::string b64decode(const std::string& text);  // base64.b64decode(validate=False); throws std::invalid_argument
bool b64decode_strict(const std::string& text, std::string& out);  // validate=True
std::string token_urlsafe(size_t nbytes);
std::string quote(const std::string& s, const std::string& safe);  // urllib.parse.quote
std::string unquote(const std::string& s);                          // urllib.parse.unquote
std::vector<std::pair<std::string, std::string>> parse_qsl(const std::string& qs);  // keep_blank_values=True

// ----------------------------------------------------------------------------- files
std::string join_path(const std::string& a, const std::string& b);
bool is_file(const std::string& path);
bool is_dir(const std::string& path);
bool read_file(const std::string& path, std::string& out);
void make_dirs(const std::string& path);
void write_private(const std::string& path, const std::string& data, bool sync);  // mode 600, throws
void write_atomic(const std::string& path, const std::string& data);              // temp + rename, mode 600
std::vector<std::string> list_dir(const std::string& path);
std::string exe_dir();
std::string real_path(const std::string& path);

// ----------------------------------------------------------------------------- time, ids
double time_now();          // time.time()
double now();               // round(time.time(), 3)
std::string iso(double ts);  // 2026-11-13T10:00:00.000Z
std::string formatdate(double ts);  // email.utils.formatdate(usegmt=True)
std::string random_bytes(size_t n);
std::string uuid4();
std::string message_id();
std::string token(size_t nbytes = 32);
std::string selector();

// ----------------------------------------------------------------------------- addresses
using NameAddr = std::pair<std::string, std::string>;
std::vector<NameAddr> getaddresses(const std::vector<std::string>& values);
NameAddr parseaddr(const std::string& text);
std::string formataddr(const NameAddr& pair);
std::string address(const std::string& text);
std::vector<std::string> addresses(const Json& values);  // throws ApiError
std::string domain_of(const std::string& addr);
bool is_domain(const std::string& text);
bool is_email(const std::string& text);
bool email_re(const std::string& text);
bool name_re(const std::string& text);

}  // namespace ses
