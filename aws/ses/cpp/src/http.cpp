#include "http.hpp"

#include <sys/socket.h>
#include <unistd.h>

#include <ctime>
#include <exception>
#include <stdexcept>
#include <map>
#include <thread>
#include <vector>

#include "config.hpp"
#include "console.hpp"
#include "errors.hpp"
#include "net.hpp"
#include "operations.hpp"
#include "query.hpp"
#include "rest.hpp"
#include "rsa.hpp"
#include "sigv4.hpp"
#include "store.hpp"
#include "util.hpp"

namespace ses {

namespace {

struct Request {
  std::string method, target, version;
  std::vector<std::pair<std::string, std::string>> headers;  // as sent
  std::string body;
  bool body_bad = false;  // Content-Length missing a number, negative or too large
  std::string ip;
  std::string path, query;  // urlsplit(target)

  std::string header(const std::string& name) const {
    for (auto& h : headers)
      if (lower(h.first) == lower(name)) return h.second;
    return "";
  }
  bool has_header(const std::string& name) const {
    for (auto& h : headers)
      if (lower(h.first) == lower(name)) return true;
    return false;
  }
  std::map<std::string, std::string> lower_headers() const {
    std::map<std::string, std::string> out;
    for (auto& h : headers) {
      std::string low = lower(h.first);
      if (out.count(low)) continue;
      std::vector<std::string> values;
      for (auto& g : headers)
        if (lower(g.first) == low) values.push_back(strip(g.second));
      out[low] = join(values, ",");
    }
    return out;
  }
};

struct Response {
  int status = 200;
  std::string body, type = "application/json";
  std::vector<std::pair<std::string, std::string>> extra;
};

const char* reason(int status) {
  switch (status) {
    case 200: return "OK";
    case 302: return "Found";
    case 400: return "Bad Request";
    case 401: return "Unauthorized";
    case 403: return "Forbidden";
    case 404: return "Not Found";
    case 413: return "Request Entity Too Large";
    case 429: return "Too Many Requests";
    case 500: return "Internal Server Error";
    case 501: return "Not Implemented";
    default: return "Unknown";
  }
}

std::string http_date() {
  time_t now_ = std::time(nullptr);
  struct tm tm;
  gmtime_r(&now_, &tm);
  char buf[64];
  std::strftime(buf, sizeof buf, "%a, %d %b %Y %H:%M:%S GMT", &tm);
  return buf;
}

Response json_response(int status, const Json& data,
                       std::vector<std::pair<std::string, std::string>> extra = {}) {
  Response r;
  r.status = status;
  r.body = dump_json(data);
  r.type = "application/json";
  r.extra = std::move(extra);
  return r;
}

Response rest_error(const ApiError& e) {
  Json body = Json::object();
  body["message"] = e.message;
  body["__type"] = e.code;
  return json_response(e.status, body, {{"x-amzn-ErrorType", e.code}});
}

Response ui_error(const ApiError& e) {
  Json body = Json::object();
  body["__type"] = e.code;
  body["message"] = e.message;
  return json_response(e.status, body, {{"Cache-Control", "no-store"}});
}

const std::string& body_of(const Request& req) {
  if (req.body_bad) throw ApiError("BadRequestException", "The request body is too large.", 413, "MessageRejected");
  return req.body;
}

Ctx auth(const Request& req, const std::string& method, const std::string& raw_path, const std::string& query,
         const std::string& body) {
  Ctx ctx;
  if (cfg.auth == "off") {
    ctx.caller = "anonymous";
    ctx.region = cfg.region;
  } else {
    auto who = verify_sigv4(method, raw_path, query, req.lower_headers(), body);
    ctx.caller = who.first;
    ctx.region = who.second;
  }
  ctx.source_ip = req.ip;
  ctx.user = ctx.caller;
  return ctx;
}

Response rest(const Request& req, const std::string& method) {
  std::string raw_path = req.target.substr(0, req.target.find('?'));
  try {
    const std::string& body = body_of(req);
    Ctx ctx = auth(req, method, raw_path, req.query, body);
    return json_response(200, rest_handle(method, req.path, req.query, body, ctx));
  } catch (const ApiError& e) {
    return rest_error(e);
  } catch (const std::exception& e) {
    log(std::string("error: ") + e.what());
    return rest_error(ApiError("InternalFailure", "The server failed to process the request.", 500));
  }
}

Response do_get(const Request& req) {
  const std::string& path = req.path;
  if (path == "/health" || path == "/healthz") {
    Json data = Json::object();
    std::lock_guard<std::recursive_mutex> guard(db().lock);
    data["status"] = "ok";
    data["version"] = VERSION;
    data["identities"] = static_cast<long long>(db().identities.size());
    data["messages"] = static_cast<long long>(db().messages.size());
    return json_response(200, data);
  }
  if (is_rest(path)) return rest(req, "GET");
  if (cfg.ui_on && (path == "/" || path == "/ui")) {
    Response r;
    r.status = 302;
    r.type = "text/plain";
    r.extra = {{"Location", "/ui/"}};
    return r;
  }
  if (cfg.ui_on && path == "/ui/") {
    Response r;
    r.body = console_index_html();
    r.type = "text/html; charset=utf-8";
    for (auto& h : PAGE_HEADERS) r.extra.emplace_back(h.first, h.second);
    return r;
  }
  if (cfg.ui_on && starts_with(path, "/ui/assets/")) {
    std::string content, type;
    if (!console_asset(unquote(path.substr(11)), content, type)) return ui_error(ApiError("NotFound", "Not found.", 404));
    Response r;
    r.body = content;
    r.type = type;
    for (auto& h : ASSET_HEADERS) r.extra.emplace_back(h.first, h.second);
    return r;
  }
  if (cfg.ui_on && path == "/ui/session") {
    Session s;
    bool found = console_session(req.header("Cookie"), s);
    Json data = Json::object();
    if (cfg.auth == "off") {
      data["authenticated"] = true;
      data["user"] = "";
      data["auth"] = false;
      data["csrf"] = "";
      data["password_login"] = false;
    } else {
      data["authenticated"] = found;
      data["user"] = found ? s.user : "";
      data["auth"] = true;
      data["csrf"] = found ? s.csrf : "";
      data["password_login"] = !cfg.ui_password.empty();
    }
    return json_response(200, data, {{"Cache-Control", "no-store"}});
  }
  return ui_error(ApiError("NotFound", "Not found. The SES API takes POST / (Action=...) and /v2/email/...", 404));
}

Response ui_post(const Request& req, const std::string& path, const std::string& body) {
  const std::string& ip = req.ip;
  if (path == "/ui/login") {
    if (cfg.auth == "off") {
      Json data = Json::object();
      data["authenticated"] = true;
      data["csrf"] = "";
      return json_response(200, data);
    }
    if (console_throttled(ip)) throw ApiError("ThrottlingException", "Too many failed sign-ins; wait 5 minutes.", 429);
    Json data;
    try {
      if (!valid_utf8(body)) throw JsonError{"not UTF-8"};
      data = parse_json(body.empty() ? "{}" : body);
    } catch (const JsonError&) {
      throw ApiError("BadRequestException", "The request body is not valid JSON.");
    }
    if (!data.is_obj()) throw std::runtime_error("the login body is not an object");
    std::string user = truthy(data.get("user")) ? py_str(data.get("user")) : "";
    std::string password = truthy(data.get("password")) ? py_str(data.get("password")) : "";
    if (!console_check_login(user, password)) {
      console_failed(ip);
      log("console sign-in refused from " + ip);
      throw ApiError("AccessDeniedException", "Wrong access key or password.", 401);
    }
    Session s = console_new_session(user.empty() ? "console" : user);
    log("console sign-in " + (user.empty() ? std::string("console") : user) + " from " + ip);
    Json out = Json::object();
    out["authenticated"] = true;
    out["user"] = user;
    out["csrf"] = s.csrf;
    return json_response(200, out,
                         {{"Set-Cookie", "ses_session=" + s.id + "; Path=/ui/; HttpOnly; SameSite=Strict; Max-Age=" +
                                             std::to_string(SESSION_TTL)},
                          {"Cache-Control", "no-store"}});
  }
  Session s;
  bool found = console_session(req.header("Cookie"), s);
  if (path == "/ui/logout") {
    if (found) console_end_session(s.id);
    Json out = Json::object();
    out["authenticated"] = false;
    return json_response(200, out, {{"Set-Cookie", "ses_session=; Path=/ui/; HttpOnly; Max-Age=0"}});
  }
  if (!starts_with(path, "/ui/api/")) throw ApiError("NotFound", "Not found.", 404);
  if (cfg.auth != "off") {
    if (!found) throw ApiError("AccessDeniedException", "Sign in first.", 401);
    if (!const_eq(req.header("X-SES-CSRF"), s.csrf))
      throw ApiError("AccessDeniedException", "The console's request token is missing; reload the page.", 403);
  }
  Json params = Json::object();
  if (!strip(body, " \t\r\n\f\v").empty()) {
    try {
      if (!valid_utf8(body)) throw JsonError{"not UTF-8"};
      params = parse_json(body);
    } catch (const JsonError&) {
      throw ApiError("BadRequestException", "The request body is not valid JSON.");
    }
  }
  if (!params.is_obj()) throw ApiError("BadRequestException", "The request body must be a JSON object.");
  std::string user = found ? s.user : "";
  Ctx ctx;
  ctx.caller = user.empty() ? "console" : "console:" + user;
  ctx.region = cfg.region;
  ctx.source_ip = ip;
  ctx.user = user;
  return json_response(200, run(path.substr(8), params, ctx), {{"Cache-Control", "no-store"}});
}

Response do_post(const Request& req) {
  if (starts_with(req.path, "/ui/")) {
    try {
      if (!cfg.ui_on) throw ApiError("NotFound", "The web console is off (SES_UI=off).", 404);
      return ui_post(req, req.path, body_of(req));
    } catch (const ApiError& e) {
      return ui_error(e);
    } catch (const std::exception& e) {
      log(std::string("error: ") + e.what());
      return ui_error(ApiError("InternalFailure", "The server failed to process the request.", 500));
    }
  }
  if (is_rest(req.path)) return rest(req, "POST");
  std::pair<int, std::string> out;
  try {
    const std::string& body = body_of(req);
    Ctx ctx = auth(req, "POST", req.path, req.query, body);
    out = query_handle(body, req.query, ctx);
  } catch (const ApiError& e) {
    out = query_error(e);
  } catch (const std::exception& e) {
    log(std::string("error: ") + e.what());
    out = query_error(ApiError("InternalFailure", "The server failed to process the request.", 500));
  }
  Response r;
  r.status = out.first;
  r.body = out.second;
  r.type = "text/xml";
  return r;
}

Response dispatch(const Request& req) {
  if (req.method == "GET" || req.method == "HEAD") return do_get(req);
  if (req.method == "PUT") return rest(req, "PUT");
  if (req.method == "DELETE") return rest(req, "DELETE");
  if (req.method == "POST") return do_post(req);
  Response r;
  r.status = 501;
  r.type = "text/html;charset=utf-8";
  r.body = "<!DOCTYPE HTML><html><head><title>Error response</title></head><body><h1>Error response</h1>"
           "<p>Error code: 501</p><p>Message: Unsupported method (" + req.method + ").</p></body></html>\n";
  return r;
}

void split_target(Request& req) {
  std::string t = req.target;
  if (starts_with(t, "http://") || starts_with(t, "https://")) {
    size_t slash = t.find('/', t.find("//") + 2);
    t = slash == std::string::npos ? "/" : t.substr(slash);
  }
  size_t hash = t.find('#');
  if (hash != std::string::npos) t = t.substr(0, hash);
  size_t q = t.find('?');
  req.path = q == std::string::npos ? t : t.substr(0, q);
  req.query = q == std::string::npos ? "" : t.substr(q + 1);
}

void handle_connection(int fd) {
  Conn conn(fd);
  conn.set_timeout(300);
  std::string ip = conn.peer_ip();
  while (true) {
    Request req;
    req.ip = ip;
    std::string line;
    if (!conn.read_line(line, 65537)) return;
    line = rstrip(line, "\r\n");
    if (line.empty()) continue;
    std::vector<std::string> parts = split_ws(line);
    if (parts.size() != 3 || !starts_with(parts[2], "HTTP/")) {
      conn.write_all("HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
      return;
    }
    req.method = parts[0];
    req.target = parts[1];
    req.version = parts[2];
    int count = 0;
    while (true) {
      if (!conn.read_line(line, 65537)) return;
      if (line == "\r\n" || line == "\n") break;
      if (++count > 100) {
        conn.write_all("HTTP/1.1 431 Too many headers\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
        return;
      }
      line = rstrip(line, "\r\n");
      if ((line[0] == ' ' || line[0] == '\t') && !req.headers.empty()) {
        req.headers.back().second += " " + strip(line);
        continue;
      }
      size_t colon = line.find(':');
      if (colon == std::string::npos) continue;
      req.headers.emplace_back(line.substr(0, colon), strip(line.substr(colon + 1)));
    }
    split_target(req);
    bool close_after = false;
    std::string connection = lower(req.header("Connection"));
    if (connection == "close" || (req.version == "HTTP/1.0" && connection != "keep-alive")) close_after = true;
    if (lower(req.header("Expect")) == "100-continue" && req.version != "HTTP/1.0")
      conn.write_all("HTTP/1.1 100 Continue\r\n\r\n");
    long long length = 0;
    std::string cl = req.header("Content-Length");
    if (!cl.empty() && !parse_py_int(cl, length)) length = -1;
    if (length < 0 || length > cfg.max_body) {
      req.body_bad = true;
      close_after = true;
    } else if (length > 0 && !conn.read_exact(static_cast<size_t>(length), req.body)) {
      return;
    }
    Response r;
    try {
      r = dispatch(req);
    } catch (const std::exception& e) {
      log(std::string("error: ") + e.what());
      r = rest_error(ApiError("InternalFailure", "The server failed to process the request.", 500));
    }
    std::string out = "HTTP/1.1 " + std::to_string(r.status) + " " + reason(r.status) + "\r\n";
    out += "Server: pskit-ses/" + std::string(VERSION) + "\r\nDate: " + http_date() + "\r\n";
    out += "Content-Type: " + r.type + "\r\nContent-Length: " + std::to_string(r.body.size()) + "\r\n";
    out += "x-amzn-RequestId: " + uuid4() + "\r\n";
    for (auto& h : r.extra) out += h.first + ": " + h.second + "\r\n";
    if (close_after) out += "Connection: close\r\n";
    out += "\r\n";
    if (req.method != "HEAD") out += r.body;
    if (!conn.write_all(out) || close_after) return;
  }
}

}  // namespace

int http_listen(const std::string& bind, int port, std::string& error) { return listen_on(bind, port, error); }

void http_serve(int fd) {
  while (true) {
    int c = ::accept4(fd, nullptr, nullptr, SOCK_CLOEXEC);
    if (c < 0) continue;
    std::thread(handle_connection, c).detach();
  }
}

int http_check() {
  std::string host = (cfg.bind == "0.0.0.0" || cfg.bind.empty() || cfg.bind == "::") ? "127.0.0.1" : cfg.bind;
  std::string error;
  int fd = connect_to(host, cfg.port, 3, error);
  if (fd < 0) return 1;
  Conn conn(fd);
  conn.set_timeout(3);
  if (!conn.write_all("GET /health HTTP/1.1\r\nHost: " + host + "\r\nConnection: close\r\n\r\n")) return 1;
  std::string line;
  if (!conn.read_line(line, 4096)) return 1;
  std::vector<std::string> parts = split_ws(line);
  return parts.size() >= 2 && parts[1] == "200" ? 0 : 1;
}

}  // namespace ses
