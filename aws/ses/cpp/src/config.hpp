// Settings from the environment (SES_*), limits and the credentials clients sign with: the same variables and
// defaults as the Python server's sesserver/config.py (see that file for what each one does).
#pragma once

#include <map>
#include <string>

namespace ses {

extern const char* const VERSION;

struct Config {
  int port = 4579;
  std::string bind = "0.0.0.0";
  std::string data_dir;
  std::string store_file;
  std::string messages_dir;
  std::string region = "us-east-1";
  std::string account = "000000000000";
  std::string auth = "sigv4";
  bool ui_on = true;
  std::string ui_password;
  std::string ui_dir;

  bool smtp_on = true;
  int smtp_port = 2587;
  std::string smtp_bind;
  std::string smtp_host;
  std::string tls_cert;
  std::string tls_key;
  bool smtp_require_tls = false;

  std::string relay_host;
  std::string delivery;
  int relay_port = 587;
  std::string relay_user;
  std::string relay_password;
  std::string relay_tls;
  bool relay_tls_verify = true;
  std::string helo_name;
  int direct_port = 25;
  std::string dns_server;
  int delivery_threads = 4;
  double retry_hours = 12;
  double retention_days = 14;

  std::string verify = "auto";
  bool sandbox = false;
  double max_24h = 50000;
  double max_rate = 14;
  long long max_message = 40LL * 1024 * 1024;
  bool dkim_check = true;

  std::string events_url;
  std::string events_token;

  long long max_body = 0;
  std::map<std::string, std::string> credentials;
};

extern Config cfg;

constexpr int MAX_RECIPIENTS = 50;
constexpr int SKEW = 15 * 60;
constexpr int SESSION_TTL = 12 * 3600;
extern const char* const SIMULATOR;

void load_config();
void log(const std::string& line);

}  // namespace ses
