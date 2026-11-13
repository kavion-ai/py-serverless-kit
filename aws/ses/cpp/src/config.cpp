#include "config.hpp"

#include <netdb.h>
#include <unistd.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <mutex>

#include "util.hpp"

namespace ses {

const char* const VERSION = "1.0.0";
const char* const SIMULATOR = "simulator.amazonses.com";
Config cfg;

namespace {

std::string env(const char* name) {
  const char* v = std::getenv(name);
  return v ? std::string(v) : std::string();
}

// os.environ.get(name) or default
std::string env_or(const char* name, const std::string& def) {
  std::string v = env(name);
  return v.empty() ? def : v;
}

bool flag(const char* name, const char* def) {
  std::string v = lower(strip(env_or(name, def)));
  return !(v == "off" || v == "0" || v == "false" || v == "no");
}

int int_of(const char* name, int def) {
  std::string v = strip(env(name));
  if (v.empty()) return def;
  long long out;
  if (!parse_py_int(v, out)) return def;
  return static_cast<int>(out);
}

double float_of(const char* name, double def) {
  std::string v = strip(env(name));
  if (v.empty()) return def;
  double out;
  if (!parse_py_float(v, out)) return def;
  return out;
}

std::string fqdn() {
  char host[256] = {0};
  if (gethostname(host, sizeof host - 1) != 0) return "";
  std::string name = host;
  struct addrinfo hints;
  std::memset(&hints, 0, sizeof hints);
  hints.ai_flags = AI_CANONNAME;
  struct addrinfo* res = nullptr;
  if (getaddrinfo(host, nullptr, &hints, &res) == 0 && res) {
    if (res->ai_canonname && std::strchr(res->ai_canonname, '.')) name = res->ai_canonname;
    freeaddrinfo(res);
  }
  return name;
}

}  // namespace

void load_config() {
  Config& c = cfg;
  c.port = int_of("SES_PORT", 4579);
  c.bind = env_or("SES_BIND", "0.0.0.0");
  std::string data = env("SES_DATA_DIR");
  if (data.empty()) {
    char cwd[4096];
    data = std::string(getcwd(cwd, sizeof cwd) ? cwd : ".") + "/data";
  }
  c.data_dir = data;
  c.store_file = join_path(data, "ses.json");
  c.messages_dir = join_path(data, "messages");
  c.region = env_or("SES_REGION", "us-east-1");
  c.account = env_or("SES_ACCOUNT_ID", "000000000000");
  c.auth = lower(env_or("SES_AUTH", "sigv4"));
  c.ui_on = flag("SES_UI", "on");
  c.ui_password = env("SES_UI_PASSWORD");
  c.ui_dir = env("SES_UI_DIR");

  c.smtp_on = flag("SES_SMTP", "on");
  c.smtp_port = int_of("SES_SMTP_PORT", 2587);
  c.smtp_bind = env_or("SES_SMTP_BIND", c.bind);
  c.smtp_host = env("SES_SMTP_HOST");
  c.tls_cert = env("SES_TLS_CERT");
  c.tls_key = env("SES_TLS_KEY");
  c.smtp_require_tls = flag("SES_SMTP_REQUIRE_TLS", "off");

  c.relay_host = env("SES_RELAY_HOST");
  c.delivery = lower(env_or("SES_DELIVERY", c.relay_host.empty() ? "direct" : "relay"));
  c.relay_port = int_of("SES_RELAY_PORT", 587);
  c.relay_user = env("SES_RELAY_USER");
  c.relay_password = env("SES_RELAY_PASSWORD");
  c.relay_tls = lower(env_or("SES_RELAY_TLS", c.relay_port == 465 ? "tls" : "starttls"));
  c.relay_tls_verify = flag("SES_RELAY_TLS_VERIFY", "on");
  c.helo_name = env("SES_HELO_NAME");
  if (c.helo_name.empty()) c.helo_name = fqdn();
  if (c.helo_name.empty()) c.helo_name = "localhost";
  c.direct_port = int_of("SES_DIRECT_PORT", 25);
  c.dns_server = env("SES_DNS_SERVER");
  c.delivery_threads = std::max(1, int_of("SES_DELIVERY_THREADS", 4));
  c.retry_hours = float_of("SES_RETRY_HOURS", 12);
  c.retention_days = float_of("SES_RETENTION_DAYS", 14);

  c.verify = lower(env_or("SES_VERIFY", "auto"));
  c.sandbox = flag("SES_SANDBOX", "off");
  c.max_24h = float_of("SES_MAX_24H", 50000);
  c.max_rate = float_of("SES_MAX_RATE", 14);
  c.max_message = static_cast<long long>(float_of("SES_MAX_MESSAGE_MB", 40) * 1024 * 1024);
  c.dkim_check = flag("SES_DKIM_CHECK", "on");

  c.events_url = env("SES_EVENTS_URL");
  c.events_token = env("SES_EVENTS_TOKEN");

  c.max_body = c.max_message * 4 / 3 + 1024 * 1024;

  c.credentials.clear();
  std::string secret = env("SES_SECRET_ACCESS_KEY");
  if (!secret.empty()) c.credentials[env_or("SES_ACCESS_KEY_ID", "pskit")] = secret;
  for (const std::string& raw : split(env("SES_CREDENTIALS"), ',')) {
    std::string pair = strip(raw);
    size_t colon = pair.find(':');
    if (colon == std::string::npos) continue;
    std::string key = pair.substr(0, colon), value = pair.substr(colon + 1);
    if (!key.empty() && !value.empty()) c.credentials[key] = value;
  }
}

void log(const std::string& line) {
  static std::mutex mu;
  time_t now = std::time(nullptr);
  struct tm tm;
  gmtime_r(&now, &tm);
  char stamp[40];
  std::strftime(stamp, sizeof stamp, "%Y-%m-%dT%H:%M:%S+00:00", &tm);
  std::lock_guard<std::mutex> lock(mu);
  std::fprintf(stdout, "%s %s\n", stamp, line.c_str());
  std::fflush(stdout);
}

}  // namespace ses
