// Everything the server keeps, in memory and on disk under SES_DATA_DIR, in the same files as the Python server:
//   ses.json              account settings, identities (with DKIM keys), templates, configuration sets, suppression
//   messages/<id>.json    one record per message: envelope, status per recipient, events
//   messages/<id>.eml     the message as sent (CRLF, DKIM-signed)
// Callers hold `lock` while they read or change the store.
#pragma once

#include <map>
#include <mutex>
#include <string>
#include <vector>

#include "json.hpp"

namespace ses {

class Store {
 public:
  std::recursive_mutex lock;
  Json account;
  std::map<std::string, Json> identities, templates, configuration_sets, suppressed, messages;
  Json delivery = Json::object();  // delivery settings saved in the console (settings.cpp); {}: the environment's

  void load();  // throws std::runtime_error
  void save();
  void save_message(const std::string& message_id, const std::string* raw = nullptr);
  std::string raw(const std::string& message_id);  // throws std::runtime_error when missing
  void delete_message(const std::string& message_id);
  int purge();
  std::vector<const Json*> recent(double since);
};

Store& db();

}  // namespace ses
