#include "dkim.hpp"

#include <ctime>
#include <map>

#include "util.hpp"

namespace ses {

namespace {

const char* const SIGNED[] = {"from", "reply-to", "subject", "date", "message-id", "to", "cc", "mime-version",
                              "content-type", "content-transfer-encoding", "in-reply-to", "references",
                              "list-unsubscribe", "list-unsubscribe-post", "feedback-id"};

// re.sub(rb"[ \t]+", b" ", s)
std::string collapse_wsp(const std::string& s) {
  std::string out;
  bool in_ws = false;
  for (char c : s) {
    if (c == ' ' || c == '\t') {
      if (!in_ws) out += ' ';
      in_ws = true;
    } else {
      out += c;
      in_ws = false;
    }
  }
  return out;
}

std::string relaxed_header(const std::string& field) {
  size_t colon = field.find(':');
  std::string name = colon == std::string::npos ? field : field.substr(0, colon);
  std::string value = colon == std::string::npos ? "" : field.substr(colon + 1);
  value = replace_all(value, "\r\n", "");
  value = strip(collapse_wsp(value), " \t");
  return lower(strip(name)) + ":" + value;
}

std::string relaxed_body(const std::string& body) {
  std::vector<std::string> lines;
  size_t start = 0;
  while (true) {
    size_t at = body.find("\r\n", start);
    if (at == std::string::npos) {
      lines.push_back(body.substr(start));
      break;
    }
    lines.push_back(body.substr(start, at - start));
    start = at + 2;
  }
  for (auto& ln : lines) ln = rstrip(collapse_wsp(ln), " ");
  while (!lines.empty() && lines.back().empty()) lines.pop_back();
  std::string out;
  for (auto& ln : lines) out += ln + "\r\n";
  return out;
}

const std::string* last_field(const std::vector<Field>& fields, const std::string& name) {
  const std::string* found = nullptr;
  for (auto& f : fields)
    if (f.first == name) found = &f.second;
  return found;
}

}  // namespace

std::string crlf(const std::string& raw) {
  std::string out;
  out.reserve(raw.size() + raw.size() / 30);
  for (size_t i = 0; i < raw.size(); ++i) {
    char c = raw[i];
    if (c == '\r') {
      out += "\r\n";
      if (i + 1 < raw.size() && raw[i + 1] == '\n') ++i;
    } else if (c == '\n') {
      out += "\r\n";
    } else {
      out += c;
    }
  }
  return out;
}

std::pair<std::string, std::string> split_message(const std::string& raw) {
  if (starts_with(raw, "\r\n")) return {"", raw.substr(2)};
  size_t at = raw.find("\r\n\r\n");
  if (at != std::string::npos) return {raw.substr(0, at) + "\r\n", raw.substr(at + 4)};
  return {ends_with(raw, "\r\n") ? raw : raw + "\r\n", ""};
}

std::vector<Field> header_fields(const std::string& head) {
  std::vector<Field> fields;
  size_t start = 0;
  while (start <= head.size()) {
    size_t at = head.find("\r\n", start);
    std::string line = head.substr(start, at == std::string::npos ? std::string::npos : at - start);
    if (!line.empty()) {
      if ((line[0] == ' ' || line[0] == '\t') && !fields.empty()) {
        fields.back().second += "\r\n" + line;
      } else {
        size_t colon = line.find(':');
        std::string name = colon == std::string::npos ? line : line.substr(0, colon);
        fields.emplace_back(lower(strip(name)), line);
      }
    }
    if (at == std::string::npos) break;
    start = at + 2;
  }
  return fields;
}

std::string dkim_sign(const std::string& raw_in, const std::string& domain, const std::string& sel, const Key& key) {
  std::string raw = crlf(raw_in);
  auto parts = split_message(raw);
  std::vector<Field> fields = header_fields(parts.first);
  std::vector<std::string> names;
  for (const char* n : SIGNED)
    if (last_field(fields, n)) names.push_back(n);
  std::string body_hash = b64encode(sha256(relaxed_body(parts.second)));
  std::string unsigned_header = "DKIM-Signature: v=1; a=rsa-sha256; c=relaxed/relaxed; d=" + domain + "; s=" + sel +
                                ";\r\n\tt=" + std::to_string(static_cast<long long>(std::time(nullptr))) +
                                "; h=" + join(names, ":") + ";\r\n\tbh=" + body_hash + ";\r\n\tb=";
  std::string canon;
  for (auto& n : names) canon += relaxed_header(*last_field(fields, n)) + "\r\n";
  canon += relaxed_header(unsigned_header);
  std::string signature = b64encode(key.sign_sha256(canon));
  return unsigned_header + signature + "\r\n" + raw;
}

bool dkim_verify(const std::string& raw_in, const std::string& public_b64) {
  std::string raw = crlf(raw_in);
  auto parts = split_message(raw);
  std::vector<Field> fields = header_fields(parts.first);
  size_t sig_index = fields.size();
  for (size_t i = 0; i < fields.size(); ++i)
    if (fields[i].first == "dkim-signature") {
      sig_index = i;
      break;
    }
  if (sig_index == fields.size()) return false;
  std::string relaxed = relaxed_header(fields[sig_index].second);
  std::map<std::string, std::string> tags;
  for (const std::string& part : split(relaxed.substr(relaxed.find(':') + 1), ';')) {
    std::string item = strip(part);
    size_t eq = item.find('=');
    std::string name = eq == std::string::npos ? item : item.substr(0, eq);
    std::string value = eq == std::string::npos ? "" : item.substr(eq + 1);
    std::string clean;
    for (char c : value)
      if (!(c == ' ' || c == '\t' || c == '\r' || c == '\n')) clean += c;
    if (!name.empty()) tags[name] = clean;
  }
  if (b64encode(sha256(relaxed_body(parts.second))) != tags["bh"]) return false;
  std::vector<Field> others;
  for (size_t i = 0; i < fields.size(); ++i)
    if (i != sig_index) others.push_back(fields[i]);
  std::string canon;
  for (const std::string& n : split(tags["h"], ':')) {
    const std::string* f = last_field(others, n);
    if (f) canon += relaxed_header(*f) + "\r\n";
  }
  size_t b = relaxed.rfind("b=");
  std::string stripped = b == std::string::npos ? relaxed : relaxed.substr(0, b + 2);
  std::string sig;
  try {
    sig = b64decode(tags["b"]);
  } catch (...) {
    return false;
  }
  return verify_sha256(public_b64, canon + stripped, sig);
}

}  // namespace ses
