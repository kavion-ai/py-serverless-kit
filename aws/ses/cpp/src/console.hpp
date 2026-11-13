// The web console's server side: sign-in (with throttling), sessions in memory, and the console's static files
// (sesserver/console.py). The UI folder: SES_UI_DIR, else `ui` next to the binary, else in the folders above it.
#pragma once

#include <map>
#include <string>

namespace ses {

struct Session {
  std::string id, user, csrf;
  double expires = 0;
};

extern const char* const CSP;
extern const std::map<std::string, std::string> PAGE_HEADERS;
extern const std::map<std::string, std::string> ASSET_HEADERS;

bool console_check_login(const std::string& user, const std::string& password);
bool console_throttled(const std::string& ip);
void console_failed(const std::string& ip);
Session console_new_session(const std::string& user);
bool console_session(const std::string& cookie_header, Session& out);
void console_end_session(const std::string& sid);
std::string console_index_html();
// (content, type) of ui/assets/<rel>; false when it is not there (or not allowed).
bool console_asset(const std::string& rel, std::string& content, std::string& type);

}  // namespace ses
