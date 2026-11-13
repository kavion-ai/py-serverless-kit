// Accepting a message: every check SES makes before it answers with a MessageId, then the queue (sesserver/sender.py).
#pragma once

#include <functional>
#include <string>
#include <vector>

#include "json.hpp"

namespace ses {

using Builder = std::function<std::string(const std::string& message_id, double date)>;

struct AcceptArgs {
  std::string operation, caller, source_ip, source;
  std::vector<std::string> to, cc, bcc;
  bool has_envelope = false;
  std::vector<std::string> envelope;
  Builder build;
  std::string return_path, configuration_set_name;
  Json tags;
};

void on_queued(std::function<void()> callback);
void wake_worker();
long long sent_last_24h();
const Json* configuration_set(const std::string& name);  // nullptr for ""; throws NotFound
std::string check_sender(const std::string& source);
std::string accept(const AcceptArgs& args);  // the caller holds the store lock
std::string overall(const Json& rec);

}  // namespace ses
