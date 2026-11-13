#include "json.hpp"

#include <algorithm>
#include <cerrno>
#include <climits>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "util.hpp"

namespace ses {

namespace {
const Json kNull;
}

Json::Json(std::vector<std::string> list) : t_(ARR) {
  for (auto& s : list) arr_.emplace_back(std::move(s));
}

double Json::num() const {
  if (t_ == INT) return s_.empty() ? static_cast<double>(i_) : std::strtod(s_.c_str(), nullptr);
  if (t_ == FLOAT) return d_;
  if (t_ == BOOL) return b_ ? 1 : 0;
  return 0;
}

const Json* Json::find(const std::string& key) const {
  if (t_ != OBJ) return nullptr;
  for (auto& kv : obj_)
    if (kv.first == key) return &kv.second;
  return nullptr;
}

Json* Json::find(const std::string& key) {
  if (t_ != OBJ) return nullptr;
  for (auto& kv : obj_)
    if (kv.first == key) return &kv.second;
  return nullptr;
}

const Json& Json::get(const std::string& key) const {
  const Json* found = find(key);
  return found ? *found : kNull;
}

Json& Json::operator[](const std::string& key) {
  if (t_ == NUL) t_ = OBJ;
  if (Json* found = find(key)) return *found;
  obj_.emplace_back(key, Json());
  return obj_.back().second;
}

bool Json::erase(const std::string& key) {
  if (t_ != OBJ) return false;
  for (auto it = obj_.begin(); it != obj_.end(); ++it) {
    if (it->first == key) {
      obj_.erase(it);
      return true;
    }
  }
  return false;
}

void Json::push(Json value) {
  if (t_ == NUL) t_ = ARR;
  arr_.push_back(std::move(value));
}

size_t Json::size() const {
  if (t_ == ARR) return arr_.size();
  if (t_ == OBJ) return obj_.size();
  if (t_ == STR) return s_.size();
  return 0;
}

bool Json::operator==(const Json& o) const {
  if (is_number() && o.is_number()) {
    if (t_ == INT && o.t_ == INT && s_.empty() && o.s_.empty()) return i_ == o.i_;
    if (t_ == INT && o.t_ == INT) return py_int_str(*this) == py_int_str(o);
    return num() == o.num();
  }
  if (t_ != o.t_) {
    // Python: True == 1, False == 0
    if (t_ == BOOL && o.is_number()) return (b_ ? 1.0 : 0.0) == o.num();
    if (o.t_ == BOOL && is_number()) return (o.b_ ? 1.0 : 0.0) == num();
    return false;
  }
  switch (t_) {
    case NUL: return true;
    case BOOL: return b_ == o.b_;
    case STR: return s_ == o.s_;
    case ARR: return arr_ == o.arr_;
    case OBJ: {
      if (obj_.size() != o.obj_.size()) return false;
      for (auto& kv : obj_) {
        const Json* other = o.find(kv.first);
        if (!other || !(*other == kv.second)) return false;
      }
      return true;
    }
    default: return false;
  }
}

// ----------------------------------------------------------------------------- Python semantics

bool truthy(const Json& v) {
  switch (v.type()) {
    case Json::NUL: return false;
    case Json::BOOL: return v.b();
    case Json::INT: return v.big() || v.i() != 0;
    case Json::FLOAT: return v.d() != 0;
    case Json::STR: return !v.s().empty();
    case Json::ARR:
    case Json::OBJ: return v.size() != 0;
  }
  return false;
}

std::string py_int_str(const Json& v) {
  if (v.type() == Json::INT) return v.big() ? v.s() : std::to_string(v.i());
  if (v.type() == Json::BOOL) return v.b() ? "1" : "0";
  return "0";
}

std::string py_float_repr(double v) {
  if (std::isnan(v)) return "nan";
  if (std::isinf(v)) return v > 0 ? "inf" : "-inf";
  if (v == 0) return std::signbit(v) ? "-0.0" : "0.0";
  char buf[64];
  for (int p = 1; p <= 17; ++p) {
    std::snprintf(buf, sizeof buf, "%.*e", p - 1, v);
    if (std::strtod(buf, nullptr) == v) break;
  }
  std::string text = buf;
  bool neg = false;
  size_t pos = 0;
  if (text[0] == '-') {
    neg = true;
    pos = 1;
  }
  size_t e = text.find('e');
  std::string mant = text.substr(pos, e - pos);
  int exp10 = std::atoi(text.c_str() + e + 1);
  std::string digits;
  for (char c : mant)
    if (c != '.') digits += c;
  while (digits.size() > 1 && digits.back() == '0') digits.pop_back();
  int decpt = exp10 + 1;
  int n = static_cast<int>(digits.size());
  std::string out = neg ? "-" : "";
  if (decpt > -4 && decpt <= 16) {
    if (decpt <= 0) {
      out += "0." + std::string(static_cast<size_t>(-decpt), '0') + digits;
    } else if (decpt >= n) {
      out += digits + std::string(static_cast<size_t>(decpt - n), '0') + ".0";
    } else {
      out += digits.substr(0, static_cast<size_t>(decpt)) + "." + digits.substr(static_cast<size_t>(decpt));
    }
  } else {
    out += digits.substr(0, 1);
    if (n > 1) out += "." + digits.substr(1);
    int x = decpt - 1;
    char eb[16];
    std::snprintf(eb, sizeof eb, "e%c%02d", x < 0 ? '-' : '+', x < 0 ? -x : x);
    out += eb;
  }
  return out;
}

static std::string py_repr(const Json& v);

std::string py_str(const Json& v) {
  switch (v.type()) {
    case Json::NUL: return "None";
    case Json::BOOL: return v.b() ? "True" : "False";
    case Json::INT: return py_int_str(v);
    case Json::FLOAT: return py_float_repr(v.d());
    case Json::STR: return v.s();
    default: return py_repr(v);
  }
}

static std::string py_repr(const Json& v) {
  switch (v.type()) {
    case Json::STR: return py_repr_str(v.s());
    case Json::ARR: {
      std::string out = "[";
      for (size_t i = 0; i < v.arr().size(); ++i) out += (i ? ", " : "") + py_repr(v.arr()[i]);
      return out + "]";
    }
    case Json::OBJ: {
      std::string out = "{";
      bool first = true;
      for (auto& kv : v.items()) {
        out += (first ? "" : ", ") + py_repr_str(kv.first) + ": " + py_repr(kv.second);
        first = false;
      }
      return out + "}";
    }
    default: return py_str(v);
  }
}

// ----------------------------------------------------------------------------- parser

namespace {

struct Parser {
  const std::string& text;
  size_t pos = 0;
  int depth = 0;

  [[noreturn]] void fail(const std::string& what) {
    throw JsonError{what + " at char " + std::to_string(pos)};
  }
  void ws() {
    while (pos < text.size() && (text[pos] == ' ' || text[pos] == '\t' || text[pos] == '\n' || text[pos] == '\r'))
      ++pos;
  }
  bool lit(const char* word) {
    size_t n = std::strlen(word);
    if (text.compare(pos, n, word) == 0) {
      pos += n;
      return true;
    }
    return false;
  }
  unsigned hex4() {
    if (pos + 4 > text.size()) fail("Invalid \\uXXXX escape");
    unsigned v = 0;
    for (int k = 0; k < 4; ++k) {
      char c = text[pos++];
      v <<= 4;
      if (c >= '0' && c <= '9') v |= static_cast<unsigned>(c - '0');
      else if (c >= 'a' && c <= 'f') v |= static_cast<unsigned>(c - 'a' + 10);
      else if (c >= 'A' && c <= 'F') v |= static_cast<unsigned>(c - 'A' + 10);
      else fail("Invalid \\uXXXX escape");
    }
    return v;
  }
  std::string string() {
    ++pos;  // opening quote
    std::string out;
    while (true) {
      if (pos >= text.size()) fail("Unterminated string");
      unsigned char c = static_cast<unsigned char>(text[pos]);
      if (c == '"') {
        ++pos;
        return out;
      }
      if (c < 0x20) fail("Invalid control character");
      if (c != '\\') {
        out += static_cast<char>(c);
        ++pos;
        continue;
      }
      ++pos;
      if (pos >= text.size()) fail("Unterminated string");
      char e = text[pos++];
      switch (e) {
        case '"': out += '"'; break;
        case '\\': out += '\\'; break;
        case '/': out += '/'; break;
        case 'b': out += '\b'; break;
        case 'f': out += '\f'; break;
        case 'n': out += '\n'; break;
        case 'r': out += '\r'; break;
        case 't': out += '\t'; break;
        case 'u': {
          unsigned cp = hex4();
          if (cp >= 0xD800 && cp <= 0xDBFF && pos + 6 <= text.size() && text[pos] == '\\' && text[pos + 1] == 'u') {
            size_t save = pos;
            pos += 2;
            unsigned lo = hex4();
            if (lo >= 0xDC00 && lo <= 0xDFFF) {
              cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
            } else {
              pos = save;
            }
          }
          if (cp >= 0xD800 && cp <= 0xDFFF) cp = 0xFFFD;  // a lone surrogate
          append_utf8(out, cp);
          break;
        }
        default: fail("Invalid \\escape");
      }
    }
  }
  Json number() {
    size_t start = pos;
    if (text[pos] == '-') {
      ++pos;
      if (lit("Infinity")) return Json(-INFINITY);
    }
    if (pos >= text.size() || !std::isdigit(static_cast<unsigned char>(text[pos]))) fail("Expecting value");
    if (text[pos] == '0') {
      ++pos;
    } else {
      while (pos < text.size() && std::isdigit(static_cast<unsigned char>(text[pos]))) ++pos;
    }
    bool is_float = false;
    if (pos + 1 < text.size() && text[pos] == '.' && std::isdigit(static_cast<unsigned char>(text[pos + 1]))) {
      is_float = true;
      ++pos;
      while (pos < text.size() && std::isdigit(static_cast<unsigned char>(text[pos]))) ++pos;
    }
    if (pos < text.size() && (text[pos] == 'e' || text[pos] == 'E')) {
      size_t save = pos;
      ++pos;
      if (pos < text.size() && (text[pos] == '+' || text[pos] == '-')) ++pos;
      if (pos < text.size() && std::isdigit(static_cast<unsigned char>(text[pos]))) {
        is_float = true;
        while (pos < text.size() && std::isdigit(static_cast<unsigned char>(text[pos]))) ++pos;
      } else {
        pos = save;
      }
    }
    std::string lexeme = text.substr(start, pos - start);
    if (is_float) return Json(std::strtod(lexeme.c_str(), nullptr));
    errno = 0;
    long long v = std::strtoll(lexeme.c_str(), nullptr, 10);
    if (errno == ERANGE) {
      std::string digits = lexeme;
      return Json::big_int(digits);
    }
    return Json(v);
  }
  Json value() {
    ws();
    if (pos >= text.size()) fail("Expecting value");
    char c = text[pos];
    if (c == '{') {
      if (++depth > 500) fail("Too deeply nested");
      ++pos;
      Json obj = Json::object();
      ws();
      if (pos < text.size() && text[pos] == '}') {
        ++pos;
        --depth;
        return obj;
      }
      while (true) {
        ws();
        if (pos >= text.size() || text[pos] != '"') fail("Expecting property name enclosed in double quotes");
        std::string key = string();
        ws();
        if (pos >= text.size() || text[pos] != ':') fail("Expecting ':' delimiter");
        ++pos;
        obj[key] = value();
        ws();
        if (pos < text.size() && text[pos] == ',') {
          ++pos;
          continue;
        }
        if (pos < text.size() && text[pos] == '}') {
          ++pos;
          --depth;
          return obj;
        }
        fail("Expecting ',' delimiter");
      }
    }
    if (c == '[') {
      if (++depth > 500) fail("Too deeply nested");
      ++pos;
      Json arr = Json::array();
      ws();
      if (pos < text.size() && text[pos] == ']') {
        ++pos;
        --depth;
        return arr;
      }
      while (true) {
        arr.push(value());
        ws();
        if (pos < text.size() && text[pos] == ',') {
          ++pos;
          continue;
        }
        if (pos < text.size() && text[pos] == ']') {
          ++pos;
          --depth;
          return arr;
        }
        fail("Expecting ',' delimiter");
      }
    }
    if (c == '"') return Json(string());
    if (lit("true")) return Json(true);
    if (lit("false")) return Json(false);
    if (lit("null")) return Json();
    if (lit("NaN")) return Json(NAN);
    if (lit("Infinity")) return Json(INFINITY);
    if (c == '-' || std::isdigit(static_cast<unsigned char>(c))) return number();
    fail("Expecting value");
  }
};

void dump_string(std::string& out, const std::string& s) {
  out += '"';
  size_t i = 0;
  while (i < s.size()) {
    unsigned char c = static_cast<unsigned char>(s[i]);
    if (c < 0x80) {
      ++i;
      switch (c) {
        case '"': out += "\\\""; break;
        case '\\': out += "\\\\"; break;
        case '\n': out += "\\n"; break;
        case '\r': out += "\\r"; break;
        case '\t': out += "\\t"; break;
        case '\b': out += "\\b"; break;
        case '\f': out += "\\f"; break;
        default:
          if (c < 0x20 || c == 0x7f) {
            char buf[8];
            std::snprintf(buf, sizeof buf, "\\u%04x", c);
            out += buf;
          } else {
            out += static_cast<char>(c);
          }
      }
      continue;
    }
    unsigned cp = next_utf8(s, i);
    char buf[16];
    if (cp >= 0x10000) {
      unsigned v = cp - 0x10000;
      std::snprintf(buf, sizeof buf, "\\u%04x\\u%04x", 0xD800 + (v >> 10), 0xDC00 + (v & 0x3FF));
    } else {
      std::snprintf(buf, sizeof buf, "\\u%04x", cp);
    }
    out += buf;
  }
  out += '"';
}

void dump_number(std::string& out, const Json& v) {
  if (v.type() == Json::INT) {
    out += py_int_str(v);
    return;
  }
  double d = v.d();
  if (std::isnan(d)) out += "NaN";
  else if (std::isinf(d)) out += d > 0 ? "Infinity" : "-Infinity";
  else out += py_float_repr(d);
}

void dump(std::string& out, const Json& v, int indent, int level, bool sort) {
  switch (v.type()) {
    case Json::NUL: out += "null"; return;
    case Json::BOOL: out += v.b() ? "true" : "false"; return;
    case Json::INT:
    case Json::FLOAT: dump_number(out, v); return;
    case Json::STR: dump_string(out, v.s()); return;
    case Json::ARR: {
      if (v.arr().empty()) {
        out += "[]";
        return;
      }
      out += '[';
      for (size_t i = 0; i < v.arr().size(); ++i) {
        if (indent >= 0) {
          out += i ? ",\n" : "\n";
          out += std::string(static_cast<size_t>(indent * (level + 1)), ' ');
        } else if (i) {
          out += ", ";
        }
        dump(out, v.arr()[i], indent, level + 1, sort);
      }
      if (indent >= 0) out += "\n" + std::string(static_cast<size_t>(indent * level), ' ');
      out += ']';
      return;
    }
    case Json::OBJ: {
      if (v.items().empty()) {
        out += "{}";
        return;
      }
      std::vector<const std::pair<std::string, Json>*> items;
      for (auto& kv : v.items()) items.push_back(&kv);
      if (sort)
        std::stable_sort(items.begin(), items.end(),
                         [](const std::pair<std::string, Json>* a, const std::pair<std::string, Json>* b) {
                           return utf8_less(a->first, b->first);
                         });
      out += '{';
      for (size_t i = 0; i < items.size(); ++i) {
        if (indent >= 0) {
          out += i ? ",\n" : "\n";
          out += std::string(static_cast<size_t>(indent * (level + 1)), ' ');
        } else if (i) {
          out += ", ";
        }
        dump_string(out, items[i]->first);
        out += ": ";
        dump(out, items[i]->second, indent, level + 1, sort);
      }
      if (indent >= 0) out += "\n" + std::string(static_cast<size_t>(indent * level), ' ');
      out += '}';
      return;
    }
  }
}

}  // namespace

Json parse_json(const std::string& text) {
  Parser p{text};
  Json v = p.value();
  p.ws();
  if (p.pos != text.size()) p.fail("Extra data");
  return v;
}

std::string dump_json(const Json& value) {
  std::string out;
  dump(out, value, -1, 0, false);
  return out;
}

std::string dump_json_file(const Json& value) {
  std::string out;
  dump(out, value, 1, 0, true);
  return out;
}

}  // namespace ses
