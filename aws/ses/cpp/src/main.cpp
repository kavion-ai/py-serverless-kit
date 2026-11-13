// pskit's Amazon SES compatible server, C++ (a drop-in replacement for ../python/server.py: the same settings, API,
// SMTP endpoint, console and data files).
//
//   ses-server                   serve (HTTP API + console, the SMTP endpoint, the delivery worker)
//   ses-server --check           exit 0 when the server answers on /health (a container health check)
//   ses-server --smtp-password   print the SES SMTP password of SES_SECRET_ACCESS_KEY and exit
#include <signal.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <string>
#include <thread>

#include "config.hpp"
#include "delivery.hpp"
#include "http.hpp"
#include "identities.hpp"
#include "net.hpp"
#include "sender.hpp"
#include "sigv4.hpp"
#include "smtp.hpp"
#include "store.hpp"

using namespace ses;

static int fail(const std::string& message) {
  std::fprintf(stderr, "%s\n", message.c_str());
  return 2;
}

int main(int argc, char** argv) {
  signal(SIGPIPE, SIG_IGN);
  init_openssl();
  load_config();
  bool check = false, password = false;
  for (int i = 1; i < argc; ++i) {
    if (std::strcmp(argv[i], "--check") == 0) check = true;
    if (std::strcmp(argv[i], "--smtp-password") == 0) password = true;
  }
  if (check) return http_check();
  if (password) {
    const char* secret = std::getenv("SES_SECRET_ACCESS_KEY");
    if (!secret || !*secret) return fail("set SES_SECRET_ACCESS_KEY");
    std::printf("%s\n", smtp_password(secret, cfg.region).c_str());
    return 0;
  }
  if (cfg.auth != "sigv4" && cfg.auth != "off") return fail("SES_AUTH must be sigv4 or off");
  if (cfg.auth != "off" && cfg.credentials.empty())
    return fail("set SES_SECRET_ACCESS_KEY (and SES_ACCESS_KEY_ID), or SES_CREDENTIALS=id:secret, or SES_AUTH=off");
  if (cfg.delivery != "relay" && cfg.delivery != "direct" && cfg.delivery != "capture")
    return fail("SES_DELIVERY must be relay, direct or capture");
  if (cfg.delivery == "relay" && cfg.relay_host.empty()) return fail("SES_DELIVERY=relay needs SES_RELAY_HOST");
  if (cfg.verify != "auto" && cfg.verify != "dns" && cfg.verify != "manual" && cfg.verify != "off")
    return fail("SES_VERIFY must be auto, dns, manual or off");
  Store& store = db();
  try {
    store.load();
  } catch (const std::exception& e) {
    return fail("ses: cannot read " + cfg.data_dir + ": " + e.what());
  }
  on_queued(wake_delivery);
  start_delivery_worker();
  std::thread(checker_loop).detach();
  for (auto& name : pending_identities()) check_later(name);
  std::string error;
  if (cfg.smtp_on && !serve_smtp(cfg.smtp_bind, cfg.smtp_port, error))
    return fail("ses: cannot listen for SMTP on " + cfg.smtp_bind + ":" + std::to_string(cfg.smtp_port) + ": " + error);
  int http_fd = http_listen(cfg.bind, cfg.port, error);
  if (http_fd < 0) return fail("ses: cannot listen on " + cfg.bind + ":" + std::to_string(cfg.port) + ": " + error);
  std::string line = "SES compatible server " + std::string(VERSION) + " (C++) on " + cfg.bind + ":" +
                     std::to_string(cfg.port);
  if (cfg.smtp_on) line += ", SMTP " + cfg.smtp_bind + ":" + std::to_string(cfg.smtp_port);
  line += ", data " + cfg.data_dir + ", delivery " + cfg.delivery;
  if (cfg.delivery == "relay") line += " via " + cfg.relay_host;
  line += ", verify " + cfg.verify + ", " + std::to_string(store.identities.size()) + " identities, " +
          std::to_string(store.messages.size()) + " messages, auth " + cfg.auth;
  if (cfg.ui_on) line += ", console /ui/";
  log(line);
  if (cfg.auth == "off") log("warning: SES_AUTH=off, anyone who reaches the port can send mail");
  http_serve(http_fd);
  return 0;
}
