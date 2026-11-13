#include "console.hpp"

#include <mutex>
#include <vector>

#include "config.hpp"
#include "rsa.hpp"
#include "util.hpp"

namespace ses {

const char* const CSP =
    "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; "
    "img-src 'self' data: blob:; font-src 'self'; frame-src blob:; frame-ancestors 'none'; form-action 'self'; "
    "base-uri 'none'";

const std::map<std::string, std::string> PAGE_HEADERS = {{"Cache-Control", "no-store"},
                                                         {"X-Frame-Options", "DENY"},
                                                         {"X-Content-Type-Options", "nosniff"},
                                                         {"Referrer-Policy", "no-referrer"},
                                                         {"Content-Security-Policy", CSP}};
const std::map<std::string, std::string> ASSET_HEADERS = {{"Cache-Control", "no-cache"},
                                                          {"X-Content-Type-Options", "nosniff"}};

namespace {

std::mutex mu;
std::map<std::string, Session> sessions;
std::map<std::string, std::vector<double>> failures;

const char* const MISSING = "<!doctype html><title>SES console</title><p>The console page (index.html) is missing.";

std::string ui_dir() {
  std::vector<std::string> candidates;
  if (!cfg.ui_dir.empty()) candidates.push_back(cfg.ui_dir);
  std::string here = exe_dir();
  candidates.push_back(join_path(here, "ui"));
  candidates.push_back(join_path(here, "../ui"));
  candidates.push_back(join_path(here, "../../ui"));
  for (auto& c : candidates)
    if (is_file(join_path(c, "index.html"))) return c;
  return "";
}

}  // namespace

bool console_check_login(const std::string& user, const std::string& password) {
  if (!cfg.ui_password.empty()) return const_eq(password, cfg.ui_password);
  auto it = cfg.credentials.find(user);
  bool ok = const_eq(password, it == cfg.credentials.end() ? std::string(32, '\0') : it->second);
  return ok && it != cfg.credentials.end();
}

bool console_throttled(const std::string& ip) {
  double now_ = time_now();
  std::lock_guard<std::mutex> lock(mu);
  std::vector<double> recent;
  for (double t : failures[ip])
    if (now_ - t < 300) recent.push_back(t);
  failures[ip] = recent;
  return recent.size() >= 10;
}

void console_failed(const std::string& ip) {
  std::lock_guard<std::mutex> lock(mu);
  failures[ip].push_back(time_now());
}

Session console_new_session(const std::string& user) {
  Session s;
  s.id = token_urlsafe(32);
  s.csrf = token_urlsafe(24);
  s.user = user;
  std::lock_guard<std::mutex> lock(mu);
  double now_ = time_now();
  for (auto it = sessions.begin(); it != sessions.end();) {
    if (it->second.expires < now_) it = sessions.erase(it);
    else ++it;
  }
  s.expires = now_ + SESSION_TTL;
  sessions[s.id] = s;
  return s;
}

bool console_session(const std::string& cookie_header, Session& out) {
  for (const std::string& part : split(cookie_header, ';')) {
    std::string item = strip(part);
    size_t eq = item.find('=');
    std::string name = eq == std::string::npos ? item : item.substr(0, eq);
    std::string value = eq == std::string::npos ? "" : item.substr(eq + 1);
    if (name != "ses_session") continue;
    std::lock_guard<std::mutex> lock(mu);
    auto it = sessions.find(value);
    if (it != sessions.end() && it->second.expires > time_now()) {
      out = it->second;
      return true;
    }
  }
  return false;
}

void console_end_session(const std::string& sid) {
  std::lock_guard<std::mutex> lock(mu);
  sessions.erase(sid);
}

std::string console_index_html() {
  std::string base = ui_dir();
  std::string out;
  if (!base.empty() && read_file(join_path(base, "index.html"), out)) return out;
  return MISSING;
}

bool console_asset(const std::string& rel, std::string& content, std::string& type) {
  std::string base = ui_dir();
  if (base.empty() || rel.empty() || rel.find('\\') != std::string::npos || rel.find('\0') != std::string::npos)
    return false;
  for (const std::string& p : split(rel, '/'))
    if (p.empty() || p[0] == '.') return false;
  std::string root = real_path(join_path(base, "assets"));
  std::string path = real_path(join_path(join_path(base, "assets"), rel));
  if (root.empty() || path.empty() || !starts_with(path, root + "/")) return false;
  if (!is_file(path) || !read_file(path, content)) return false;
  static const std::map<std::string, std::string> types = {{".js", "text/javascript; charset=utf-8"},
                                                           {".css", "text/css; charset=utf-8"},
                                                           {".svg", "image/svg+xml"},
                                                           {".png", "image/png"},
                                                           {".ico", "image/x-icon"},
                                                           {".woff2", "font/woff2"},
                                                           {".json", "application/json"},
                                                           {".html", "text/html; charset=utf-8"}};
  size_t dot = path.rfind('.');
  size_t slash = path.rfind('/');
  std::string suffix = (dot == std::string::npos || (slash != std::string::npos && dot < slash)) ? "" : lower(path.substr(dot));
  auto it = types.find(suffix);
  type = it == types.end() ? "application/octet-stream" : it->second;
  return true;
}

}  // namespace ses
