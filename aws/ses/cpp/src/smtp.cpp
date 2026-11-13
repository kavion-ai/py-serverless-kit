#include "smtp.hpp"

#include <openssl/ssl.h>
#include <sys/socket.h>

#include <cctype>
#include <mutex>
#include <thread>
#include <vector>

#include "config.hpp"
#include "errors.hpp"
#include "net.hpp"
#include "operations.hpp"
#include "sigv4.hpp"
#include "store.hpp"
#include "util.hpp"

namespace ses {

namespace {

const size_t MAX_LINE = 4096;
SSL_CTX* tls_ctx = nullptr;

// ^\s*(?:FROM|TO)\s*:\s*<([^<>]*)>(.*)$ (case-insensitive)
bool match_addr(const std::string& arg, std::string& addr, std::string& rest) {
  size_t i = 0;
  auto ws = [&]() {
    while (i < arg.size() && std::isspace(static_cast<unsigned char>(arg[i]))) ++i;
  };
  ws();
  std::string up = upper(arg);
  if (up.compare(i, 4, "FROM") == 0) i += 4;
  else if (up.compare(i, 2, "TO") == 0) i += 2;
  else return false;
  ws();
  if (i >= arg.size() || arg[i] != ':') return false;
  ++i;
  ws();
  if (i >= arg.size() || arg[i] != '<') return false;
  size_t close = arg.find('>', i + 1);
  if (close == std::string::npos) return false;
  addr = arg.substr(i + 1, close - i - 1);
  if (addr.find('<') != std::string::npos) return false;
  rest = arg.substr(close + 1);
  return rest.find('\n') == std::string::npos;
}

class SmtpSession {
 public:
  explicit SmtpSession(int fd) : conn_(fd) {}

  void run() {
    conn_.set_timeout(300);
    ip_ = conn_.peer_ip();
    user_ = cfg.auth != "off" ? "" : "anonymous";
    say("220 " + cfg.helo_name + " ESMTP pskit SES " + VERSION);
    while (true) {
      std::string raw;
      if (!readline(raw)) return;
      std::string text = sanitize_utf8(raw);
      size_t sp = text.find(' ');
      std::string verb = upper(sp == std::string::npos ? text : text.substr(0, sp));
      std::string arg = strip(sp == std::string::npos ? "" : text.substr(sp + 1));
      bool alpha = !verb.empty();
      for (char c : verb)
        if (!std::isalpha(static_cast<unsigned char>(c))) alpha = false;
      if (!alpha) {
        say("502 5.5.2 Command not recognized");
        continue;
      }
      if (verb == "EHLO") ehlo();
      else if (verb == "HELO") helo();
      else if (verb == "STARTTLS") {
        if (!starttls()) return;
      } else if (verb == "AUTH") auth(arg);
      else if (verb == "MAIL") mail(arg);
      else if (verb == "RCPT") rcpt(arg);
      else if (verb == "DATA") {
        if (!data()) return;
      } else if (verb == "RSET") {
        reset();
        say("250 2.0.0 Ok");
      } else if (verb == "NOOP") say("250 2.0.0 Ok");
      else if (verb == "VRFY") say("252 2.0.0 Cannot VRFY user");
      else if (verb == "QUIT") {
        say("221 2.0.0 Bye");
        return;
      } else say("502 5.5.2 Command not recognized");
      if (dead_) return;
    }
  }

 private:
  Conn conn_;
  std::string ip_, user_;
  bool secure_ = false, has_from_ = false, dead_ = false;
  std::string mail_from_;
  std::vector<std::string> rcpts_;

  void say(const std::string& line) {
    if (!conn_.write_all(line + "\r\n")) dead_ = true;
  }
  bool readline(std::string& out) {
    std::string line;
    if (!conn_.read_line(line, MAX_LINE + 2)) return false;
    out = rstrip(line, "\r\n");
    return true;
  }
  void reset() {
    has_from_ = false;
    mail_from_.clear();
    rcpts_.clear();
  }

  void ehlo() {
    reset();
    std::vector<std::string> lines = {cfg.helo_name, "8BITMIME", "PIPELINING", "SIZE " + std::to_string(cfg.max_message)};
    if (tls_ctx && !secure_) lines.push_back("STARTTLS");
    if (cfg.auth != "off" && (secure_ || !cfg.smtp_require_tls)) lines.push_back("AUTH PLAIN LOGIN");
    for (size_t i = 0; i < lines.size(); ++i) say(std::string("250") + (i + 1 < lines.size() ? "-" : " ") + lines[i]);
  }

  void helo() {
    reset();
    say("250 " + cfg.helo_name);
  }

  bool starttls() {
    if (!tls_ctx || secure_) {
      say("502 5.5.1 STARTTLS not available");
      return true;
    }
    say("220 2.0.0 Ready to start TLS");
    if (!conn_.start_tls_server(tls_ctx)) return false;
    secure_ = true;
    reset();
    user_ = cfg.auth != "off" ? "" : "anonymous";
    return true;
  }

  static bool decode(const std::string& text, std::string& out) {
    try {
      out = b64decode(text);
    } catch (const std::exception&) {
      return false;
    }
    return valid_utf8(out);
  }

  void auth(const std::string& arg) {
    if (cfg.auth == "off") {
      say("235 2.7.0 Authentication successful");
      return;
    }
    if (!user_.empty()) {
      say("503 5.5.1 Already authenticated");
      return;
    }
    if (cfg.smtp_require_tls && !secure_) {
      say("530 5.7.0 Must issue a STARTTLS command first");
      return;
    }
    size_t sp = arg.find(' ');
    std::string mech = upper(sp == std::string::npos ? arg : arg.substr(0, sp));
    std::string initial = sp == std::string::npos ? "" : arg.substr(sp + 1);
    std::string user, password;
    if (mech == "PLAIN") {
      if (initial.empty()) {
        say("334 ");
        if (!readline(initial)) initial.clear();
      }
      std::string decoded;
      std::vector<std::string> parts;
      if (decode(initial, decoded)) parts = split(decoded, '\0');
      if (parts.size() != 3) {
        say("501 5.5.2 Cannot decode the login");
        return;
      }
      user = parts[1];
      password = parts[2];
    } else if (mech == "LOGIN") {
      std::string line;
      if (!initial.empty()) {
        line = initial;
      } else {
        say("334 VXNlcm5hbWU6");
        if (!readline(line)) line.clear();
      }
      if (!decode(line, user)) {
        say("501 5.5.2 Cannot decode the login");
        return;
      }
      say("334 UGFzc3dvcmQ6");
      if (!readline(line)) line.clear();
      if (!decode(line, password)) {
        say("501 5.5.2 Cannot decode the login");
        return;
      }
    } else {
      say("504 5.5.4 Unrecognized authentication type");
      return;
    }
    if (check_smtp_login(user, password)) {
      user_ = user;
      say("235 2.7.0 Authentication successful");
    } else {
      log("SMTP login refused for " + py_repr_str(user) + " from " + ip_);
      say("535 5.7.8 Authentication credentials invalid");
    }
  }

  void mail(const std::string& arg) {
    if (user_.empty()) {
      say("530 5.7.1 Authentication required");
      return;
    }
    std::string addr, rest;
    if (!match_addr(arg, addr, rest) || !starts_with(lstrip(upper(arg)), "FROM")) {
      say("501 5.5.4 Syntax: MAIL FROM:<address>");
      return;
    }
    std::string up = upper(rest);
    size_t at = up.find("SIZE=");
    if (at != std::string::npos) {
      size_t k = at + 5;
      std::string digits;
      while (k < rest.size() && std::isdigit(static_cast<unsigned char>(rest[k]))) digits += rest[k++];
      if (!digits.empty() && (digits.size() > 18 || std::stoll(digits) > cfg.max_message)) {
        say("552 5.3.4 Message size exceeds the limit");
        return;
      }
    }
    mail_from_ = addr;
    has_from_ = true;
    rcpts_.clear();
    say("250 2.1.0 Ok");
  }

  void rcpt(const std::string& arg) {
    if (!has_from_) {
      say("503 5.5.1 MAIL first");
      return;
    }
    std::string addr, rest;
    if (!match_addr(arg, addr, rest) || addr.empty() || !starts_with(lstrip(upper(arg)), "TO")) {
      say("501 5.5.4 Syntax: RCPT TO:<address>");
      return;
    }
    if (rcpts_.size() >= 50) {
      say("452 4.5.3 Too many recipients");
      return;
    }
    rcpts_.push_back(addr);
    say("250 2.1.5 Ok");
  }

  bool data() {
    if (!has_from_ || rcpts_.empty()) {
      say("503 5.5.1 RCPT first");
      return true;
    }
    say("354 End data with <CR><LF>.<CR><LF>");
    std::string message;
    long long size = 0;
    bool too_big = false;
    while (true) {
      std::string line;
      if (!conn_.read_line(line, 1024 * 1024)) return false;
      if (line == ".\r\n" || line == ".\n") break;
      if (!line.empty() && line[0] == '.') line.erase(0, 1);
      size += static_cast<long long>(line.size());
      if (size > cfg.max_message) too_big = true;
      else if (!too_big) message += line;
    }
    if (too_big) {
      reset();
      say("552 5.3.4 Message size exceeds the limit");
      return true;
    }
    say(send(message));
    reset();
    return true;
  }

  std::string send(const std::string& raw) {
    Ctx ctx;
    ctx.caller = user_;
    ctx.source_ip = ip_;
    ctx.region = cfg.region;
    try {
      std::lock_guard<std::recursive_mutex> guard(db().lock);
      Json list = Json::array();
      for (auto& r : rcpts_) list.push(r);
      SendArgs a;
      a.operation = "SendSmtpEmail";
      a.ctx = ctx;
      Json content = Json::object();
      Json r = Json::object();
      r["Data"] = b64encode(raw);
      content["Raw"] = r;
      a.content = content;
      a.return_path = mail_from_;
      a.has_envelope = true;
      a.envelope = addresses(list);
      return "250 Ok " + send_message(a);
    } catch (const ApiError& e) {
      if (e.code == "TooManyRequestsException" || e.code == "LimitExceededException")
        return "454 4.7.0 Throttling failure: " + e.message;
      return "554 5.7.1 Transaction failed: " + e.message;
    } catch (const std::exception& e) {
      log(std::string("SMTP send failed: ") + e.what());
      return "451 4.3.0 Temporary server error, try again later";
    }
  }
};

void session_thread(int fd) {
  SmtpSession s(fd);
  s.run();
}

}  // namespace

bool serve_smtp(const std::string& bind, int port, std::string& error) {
  if (!cfg.tls_cert.empty() && !cfg.tls_key.empty()) {
    tls_ctx = server_tls_context(cfg.tls_cert, cfg.tls_key, error);
    if (!tls_ctx) return false;
  }
  int fd = listen_on(bind, port, error);
  if (fd < 0) return false;
  std::thread([fd]() {
    while (true) {
      int c = ::accept4(fd, nullptr, nullptr, SOCK_CLOEXEC);
      if (c < 0) continue;
      std::thread(session_thread, c).detach();
    }
  }).detach();
  return true;
}

}  // namespace ses
