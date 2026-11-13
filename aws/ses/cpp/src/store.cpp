#include "store.hpp"

#include <unistd.h>

#include <algorithm>
#include <stdexcept>

#include "config.hpp"
#include "util.hpp"

namespace ses {

namespace {

const int FORMAT = 1;

void load_table(const Json& data, const char* key, std::map<std::string, Json>& out) {
  out.clear();
  const Json& table = data.get(key);
  if (!table.is_obj()) return;
  for (auto& kv : table.items()) out[kv.first] = kv.second;
}

Json table_json(const std::map<std::string, Json>& table) {
  Json out = Json::object();
  for (auto& kv : table) out[kv.first] = kv.second;
  return out;
}

}  // namespace

Store& db() {
  static Store store;
  return store;
}

void Store::load() {
  account = Json::object();
  account["SendingEnabled"] = true;
  account["SuppressedReasons"] = Json(std::vector<std::string>{"BOUNCE", "COMPLAINT"});
  if (is_file(cfg.store_file)) {
    std::string text;
    if (!read_file(cfg.store_file, text)) throw std::runtime_error("cannot read " + cfg.store_file);
    Json data;
    try {
      data = parse_json(text.empty() ? "{}" : text);
    } catch (const JsonError& e) {
      throw std::runtime_error(e.message);
    }
    if (!data.is_obj()) throw std::runtime_error("ses.json is not a JSON object");
    const Json& acc = data.get("account");
    if (acc.is_obj())
      for (auto& kv : acc.items()) account[kv.first] = kv.second;
    load_table(data, "identities", identities);
    load_table(data, "templates", templates);
    load_table(data, "configuration_sets", configuration_sets);
    load_table(data, "suppressed", suppressed);
  }
  if (is_dir(cfg.messages_dir)) {
    for (const std::string& name : list_dir(cfg.messages_dir)) {
      if (!ends_with(name, ".json")) continue;
      std::string text;
      std::string path = join_path(cfg.messages_dir, name);
      try {
        if (!read_file(path, text)) throw JsonError{"cannot read the file"};
        Json rec = parse_json(text);
        const Json& id = rec.get("MessageId");
        if (!id.is_str()) throw JsonError{"no MessageId"};
        messages[id.s()] = std::move(rec);
      } catch (const JsonError& e) {
        log("skipping unreadable message record " + name + " " + e.message);
      }
    }
  }
}

void Store::save() {
  std::lock_guard<std::recursive_mutex> guard(lock);
  Json data = Json::object();
  data["format"] = FORMAT;
  data["account"] = account;
  data["identities"] = table_json(identities);
  data["templates"] = table_json(templates);
  data["configuration_sets"] = table_json(configuration_sets);
  data["suppressed"] = table_json(suppressed);
  write_atomic(cfg.store_file, dump_json_file(data));
}

void Store::save_message(const std::string& message_id, const std::string* raw) {
  std::lock_guard<std::recursive_mutex> guard(lock);
  auto it = messages.find(message_id);
  if (it == messages.end()) return;
  if (raw) write_private(join_path(cfg.messages_dir, message_id + ".eml"), *raw, false);
  write_atomic(join_path(cfg.messages_dir, message_id + ".json"), dump_json_file(it->second));
}

std::string Store::raw(const std::string& message_id) {
  std::string out;
  if (!read_file(join_path(cfg.messages_dir, message_id + ".eml"), out))
    throw std::runtime_error("message " + message_id + " has no .eml file");
  return out;
}

void Store::delete_message(const std::string& message_id) {
  std::lock_guard<std::recursive_mutex> guard(lock);
  messages.erase(message_id);
  ::unlink(join_path(cfg.messages_dir, message_id + ".json").c_str());
  ::unlink(join_path(cfg.messages_dir, message_id + ".eml").c_str());
}

int Store::purge() {
  double cutoff = time_now() - std::max(cfg.retention_days, 1.0) * 86400;
  std::vector<std::string> old;
  {
    std::lock_guard<std::recursive_mutex> guard(lock);
    for (auto& kv : messages) {
      const std::string status = kv.second.get("Status").is_str() ? kv.second.get("Status").s() : "";
      if (kv.second.get("Timestamp").num() < cutoff && status != "QUEUED" && status != "DELAYED" &&
          status != "SENDING")
        old.push_back(kv.first);
    }
  }
  for (auto& id : old) delete_message(id);
  return static_cast<int>(old.size());
}

std::vector<const Json*> Store::recent(double since) {
  std::lock_guard<std::recursive_mutex> guard(lock);
  std::vector<const Json*> out;
  for (auto& kv : messages)
    if (kv.second.get("Timestamp").num() >= since) out.push_back(&kv.second);
  return out;
}

}  // namespace ses
