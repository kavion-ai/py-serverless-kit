#include "util.hpp"

#include <dirent.h>
#include <fcntl.h>
#include <limits.h>
#include <openssl/rand.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <unistd.h>

#include <algorithm>
#include <cctype>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <stdexcept>
#include <system_error>
#include <thread>

#include "config.hpp"
#include "errors.hpp"

namespace ses {

// ----------------------------------------------------------------------------- strings

std::string strip(const std::string& s, const char* chars) { return lstrip(rstrip(s, chars), chars); }

std::string rstrip(const std::string& s, const char* chars) {
  size_t end = s.find_last_not_of(chars);
  return end == std::string::npos ? std::string() : s.substr(0, end + 1);
}

std::string lstrip(const std::string& s, const char* chars) {
  size_t start = s.find_first_not_of(chars);
  return start == std::string::npos ? std::string() : s.substr(start);
}

std::string lower(std::string s) {
  for (auto& c : s)
    if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
  return s;
}

std::string upper(std::string s) {
  for (auto& c : s)
    if (c >= 'a' && c <= 'z') c = static_cast<char>(c - 'a' + 'A');
  return s;
}

std::vector<std::string> split(const std::string& s, char sep) {
  std::vector<std::string> out;
  size_t start = 0;
  while (true) {
    size_t at = s.find(sep, start);
    if (at == std::string::npos) {
      out.push_back(s.substr(start));
      return out;
    }
    out.push_back(s.substr(start, at - start));
    start = at + 1;
  }
}

std::vector<std::string> split_ws(const std::string& s) {
  std::vector<std::string> out;
  std::string cur;
  for (char c : s) {
    if (c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' || c == '\v') {
      if (!cur.empty()) out.push_back(cur);
      cur.clear();
    } else {
      cur += c;
    }
  }
  if (!cur.empty()) out.push_back(cur);
  return out;
}

std::string join(const std::vector<std::string>& parts, const std::string& sep) {
  std::string out;
  for (size_t i = 0; i < parts.size(); ++i) {
    if (i) out += sep;
    out += parts[i];
  }
  return out;
}

bool starts_with(const std::string& s, const std::string& p) { return s.size() >= p.size() && s.compare(0, p.size(), p) == 0; }

bool ends_with(const std::string& s, const std::string& p) {
  return s.size() >= p.size() && s.compare(s.size() - p.size(), p.size(), p) == 0;
}

std::string replace_all(std::string s, const std::string& from, const std::string& to) {
  if (from.empty()) return s;
  size_t pos = 0;
  while ((pos = s.find(from, pos)) != std::string::npos) {
    s.replace(pos, from.size(), to);
    pos += to.size();
  }
  return s;
}

bool parse_py_int(const std::string& raw, long long& out) {
  std::string s = strip(raw);
  std::string clean;
  for (size_t i = 0; i < s.size(); ++i) {
    if (s[i] == '_' && i > 0 && i + 1 < s.size() && std::isdigit(static_cast<unsigned char>(s[i - 1])) &&
        std::isdigit(static_cast<unsigned char>(s[i + 1])))
      continue;
    clean += s[i];
  }
  if (clean.empty()) return false;
  size_t i = 0;
  if (clean[0] == '+' || clean[0] == '-') i = 1;
  if (i >= clean.size()) return false;
  for (size_t k = i; k < clean.size(); ++k)
    if (!std::isdigit(static_cast<unsigned char>(clean[k]))) return false;
  errno = 0;
  out = std::strtoll(clean.c_str(), nullptr, 10);
  return errno != ERANGE;
}

bool parse_py_float(const std::string& raw, double& out) {
  std::string s = lower(strip(raw));
  if (s.empty()) return false;
  std::string body = (s[0] == '+' || s[0] == '-') ? s.substr(1) : s;
  if (body == "inf" || body == "infinity" || body == "nan") {
    double v = body == "nan" ? NAN : INFINITY;
    out = s[0] == '-' ? -v : v;
    return true;
  }
  for (char c : body)
    if (!(std::isdigit(static_cast<unsigned char>(c)) || c == '.' || c == 'e' || c == '+' || c == '-' || c == '_'))
      return false;
  std::string clean = replace_all(s, "_", "");
  char* end = nullptr;
  out = std::strtod(clean.c_str(), &end);
  return end && *end == '\0' && end != clean.c_str();
}

std::string py_repr_str(const std::string& s) {
  bool has_single = s.find('\'') != std::string::npos, has_double = s.find('"') != std::string::npos;
  char q = (has_single && !has_double) ? '"' : '\'';
  std::string out(1, q);
  size_t i = 0;
  while (i < s.size()) {
    unsigned char c = static_cast<unsigned char>(s[i]);
    if (c >= 0x80) {
      size_t start = i;
      unsigned cp = next_utf8(s, i);
      if (cp == 0xFFFD && !(i - start == 3 && s.compare(start, 3, "\xEF\xBF\xBD") == 0)) {
        char buf[8];
        std::snprintf(buf, sizeof buf, "\\udc%02x", c);
        out += buf;
        i = start + 1;
      } else {
        out += s.substr(start, i - start);
      }
      continue;
    }
    ++i;
    if (c == static_cast<unsigned char>(q) || c == '\\') {
      out += '\\';
      out += static_cast<char>(c);
    } else if (c == '\n') {
      out += "\\n";
    } else if (c == '\r') {
      out += "\\r";
    } else if (c == '\t') {
      out += "\\t";
    } else if (c < 0x20 || c == 0x7f) {
      char buf[8];
      std::snprintf(buf, sizeof buf, "\\x%02x", c);
      out += buf;
    } else {
      out += static_cast<char>(c);
    }
  }
  out += q;
  return out;
}

std::string hex(const std::string& bytes) {
  static const char* digits = "0123456789abcdef";
  std::string out;
  for (unsigned char c : bytes) {
    out += digits[c >> 4];
    out += digits[c & 15];
  }
  return out;
}

// ----------------------------------------------------------------------------- UTF-8

void append_utf8(std::string& out, unsigned cp) {
  if (cp < 0x80) {
    out += static_cast<char>(cp);
  } else if (cp < 0x800) {
    out += static_cast<char>(0xC0 | (cp >> 6));
    out += static_cast<char>(0x80 | (cp & 0x3F));
  } else if (cp < 0x10000) {
    out += static_cast<char>(0xE0 | (cp >> 12));
    out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
    out += static_cast<char>(0x80 | (cp & 0x3F));
  } else {
    out += static_cast<char>(0xF0 | (cp >> 18));
    out += static_cast<char>(0x80 | ((cp >> 12) & 0x3F));
    out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
    out += static_cast<char>(0x80 | (cp & 0x3F));
  }
}

unsigned next_utf8(const std::string& s, size_t& i) {
  unsigned char c = static_cast<unsigned char>(s[i]);
  if (c < 0x80) {
    ++i;
    return c;
  }
  int n;
  unsigned cp, min;
  if ((c & 0xE0) == 0xC0) {
    n = 1;
    cp = c & 0x1F;
    min = 0x80;
  } else if ((c & 0xF0) == 0xE0) {
    n = 2;
    cp = c & 0x0F;
    min = 0x800;
  } else if ((c & 0xF8) == 0xF0) {
    n = 3;
    cp = c & 0x07;
    min = 0x10000;
  } else {
    ++i;
    return 0xFFFD;
  }
  size_t k = i + 1;
  for (int j = 0; j < n; ++j, ++k) {
    if (k >= s.size() || (static_cast<unsigned char>(s[k]) & 0xC0) != 0x80) {
      i = k;
      return 0xFFFD;
    }
    cp = (cp << 6) | (static_cast<unsigned char>(s[k]) & 0x3F);
  }
  i = k;
  if (cp < min || cp > 0x10FFFF || (cp >= 0xD800 && cp <= 0xDFFF)) return 0xFFFD;
  return cp;
}

size_t utf8_len(const std::string& s) {
  size_t n = 0;
  for (size_t i = 0; i < s.size();) {
    next_utf8(s, i);
    ++n;
  }
  return n;
}

bool valid_utf8(const std::string& s) {
  for (size_t i = 0; i < s.size();) {
    size_t start = i;
    unsigned cp = next_utf8(s, i);
    if (cp == 0xFFFD && !(i - start == 3 && s.compare(start, 3, "\xEF\xBF\xBD") == 0)) return false;
  }
  return true;
}

std::string sanitize_utf8(const std::string& s) {
  std::string out;
  out.reserve(s.size());
  for (size_t i = 0; i < s.size();) {
    unsigned char c = static_cast<unsigned char>(s[i]);
    if (c < 0x80) {
      out += static_cast<char>(c);
      ++i;
      continue;
    }
    size_t start = i;
    unsigned cp = next_utf8(s, i);
    if (cp == 0xFFFD && !(i - start == 3 && s.compare(start, 3, "\xEF\xBF\xBD") == 0)) {
      out += "\xEF\xBF\xBD";
      if (i == start) ++i;
    } else {
      out.append(s, start, i - start);
    }
  }
  return out;
}

std::string latin1_to_utf8(const std::string& s) {
  std::string out;
  for (unsigned char c : s) append_utf8(out, c);
  return out;
}

// ----------------------------------------------------------------------------- base64, URLs

static const char* B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

std::string b64encode(const std::string& data) {
  std::string out;
  out.reserve((data.size() + 2) / 3 * 4);
  size_t i = 0;
  while (i + 2 < data.size()) {
    unsigned v = (static_cast<unsigned char>(data[i]) << 16) | (static_cast<unsigned char>(data[i + 1]) << 8) |
                 static_cast<unsigned char>(data[i + 2]);
    out += B64[(v >> 18) & 63];
    out += B64[(v >> 12) & 63];
    out += B64[(v >> 6) & 63];
    out += B64[v & 63];
    i += 3;
  }
  if (i + 1 == data.size()) {
    unsigned v = static_cast<unsigned char>(data[i]) << 16;
    out += B64[(v >> 18) & 63];
    out += B64[(v >> 12) & 63];
    out += "==";
  } else if (i + 2 == data.size()) {
    unsigned v = (static_cast<unsigned char>(data[i]) << 16) | (static_cast<unsigned char>(data[i + 1]) << 8);
    out += B64[(v >> 18) & 63];
    out += B64[(v >> 12) & 63];
    out += B64[(v >> 6) & 63];
    out += '=';
  }
  return out;
}

static int b64val(unsigned char c) {
  if (c >= 'A' && c <= 'Z') return c - 'A';
  if (c >= 'a' && c <= 'z') return c - 'a' + 26;
  if (c >= '0' && c <= '9') return c - '0' + 52;
  if (c == '+') return 62;
  if (c == '/') return 63;
  return -1;
}

// CPython's binascii.a2b_base64 in non-strict mode.
std::string b64decode(const std::string& text) {
  std::string out;
  int quad = 0, pads = 0;
  unsigned left = 0;
  for (unsigned char c : text) {
    if (c == '=') {
      if (quad >= 2 && quad + ++pads >= 4) return out;
      continue;
    }
    int v = b64val(c);
    if (v < 0) continue;
    pads = 0;
    switch (quad) {
      case 0:
        quad = 1;
        left = static_cast<unsigned>(v);
        break;
      case 1:
        quad = 2;
        out += static_cast<char>((left << 2) | (static_cast<unsigned>(v) >> 4));
        left = static_cast<unsigned>(v) & 0x0f;
        break;
      case 2:
        quad = 3;
        out += static_cast<char>((left << 4) | (static_cast<unsigned>(v) >> 2));
        left = static_cast<unsigned>(v) & 0x03;
        break;
      default:
        quad = 0;
        out += static_cast<char>((left << 6) | static_cast<unsigned>(v));
        left = 0;
    }
  }
  if (quad == 1) throw std::invalid_argument("Invalid base64-encoded string");
  if (quad != 0) throw std::invalid_argument("Incorrect padding");
  return out;
}

bool b64decode_strict(const std::string& text, std::string& out) {
  if (text.size() % 4) return false;
  size_t pad = 0;
  for (size_t i = 0; i < text.size(); ++i) {
    unsigned char c = static_cast<unsigned char>(text[i]);
    if (c == '=') {
      if (i + 2 < text.size()) return false;
      ++pad;
    } else if (b64val(c) < 0 || pad) {
      return false;
    }
  }
  try {
    out = b64decode(text);
  } catch (const std::invalid_argument&) {
    return false;
  }
  return true;
}

std::string token_urlsafe(size_t nbytes) {
  std::string out = b64encode(random_bytes(nbytes));
  for (auto& c : out) {
    if (c == '+') c = '-';
    else if (c == '/') c = '_';
  }
  while (!out.empty() && out.back() == '=') out.pop_back();
  return out;
}

std::string quote(const std::string& s, const std::string& safe) {
  static const char* digits = "0123456789ABCDEF";
  std::string out;
  for (unsigned char c : s) {
    if (std::isalnum(c) || c == '_' || c == '.' || c == '-' || c == '~' || safe.find(static_cast<char>(c)) != std::string::npos) {
      out += static_cast<char>(c);
    } else {
      out += '%';
      out += digits[c >> 4];
      out += digits[c & 15];
    }
  }
  return out;
}

static int hexval(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

std::string unquote(const std::string& s) {
  std::string out;
  for (size_t i = 0; i < s.size(); ++i) {
    if (s[i] == '%' && i + 2 < s.size() && hexval(s[i + 1]) >= 0 && hexval(s[i + 2]) >= 0) {
      out += static_cast<char>(hexval(s[i + 1]) * 16 + hexval(s[i + 2]));
      i += 2;
    } else {
      out += s[i];
    }
  }
  return sanitize_utf8(out);  // errors="replace"
}

std::vector<std::pair<std::string, std::string>> parse_qsl(const std::string& qs) {
  std::vector<std::pair<std::string, std::string>> out;
  for (const std::string& field : split(qs, '&')) {
    if (field.empty()) continue;
    size_t eq = field.find('=');
    std::string name = eq == std::string::npos ? field : field.substr(0, eq);
    std::string value = eq == std::string::npos ? "" : field.substr(eq + 1);
    out.emplace_back(unquote(replace_all(name, "+", " ")), unquote(replace_all(value, "+", " ")));
  }
  return out;
}

// ----------------------------------------------------------------------------- files

std::string join_path(const std::string& a, const std::string& b) {
  if (a.empty()) return b;
  return a.back() == '/' ? a + b : a + "/" + b;
}

bool is_file(const std::string& path) {
  struct stat st;
  return ::stat(path.c_str(), &st) == 0 && S_ISREG(st.st_mode);
}

bool is_dir(const std::string& path) {
  struct stat st;
  return ::stat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode);
}

bool read_file(const std::string& path, std::string& out) {
  FILE* f = std::fopen(path.c_str(), "rb");
  if (!f) return false;
  out.clear();
  char buf[65536];
  size_t n;
  while ((n = std::fread(buf, 1, sizeof buf, f)) > 0) out.append(buf, n);
  bool ok = !std::ferror(f);
  std::fclose(f);
  return ok;
}

void make_dirs(const std::string& path) {
  if (path.empty() || is_dir(path)) return;
  size_t slash = path.find_last_of('/');
  if (slash != std::string::npos && slash > 0) make_dirs(path.substr(0, slash));
  if (::mkdir(path.c_str(), 0777) != 0 && errno != EEXIST)
    throw std::system_error(errno, std::generic_category(), "mkdir " + path);
}

static std::string parent_of(const std::string& path) {
  size_t slash = path.find_last_of('/');
  return slash == std::string::npos ? std::string() : path.substr(0, slash);
}

void write_private(const std::string& path, const std::string& data, bool sync) {
  make_dirs(parent_of(path));
  int fd = ::open(path.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
  if (fd < 0) throw std::system_error(errno, std::generic_category(), "open " + path);
  size_t off = 0;
  while (off < data.size()) {
    ssize_t n = ::write(fd, data.data() + off, data.size() - off);
    if (n < 0) {
      if (errno == EINTR) continue;
      int err = errno;
      ::close(fd);
      throw std::system_error(err, std::generic_category(), "write " + path);
    }
    off += static_cast<size_t>(n);
  }
  if (sync) ::fsync(fd);
  ::close(fd);
}

void write_atomic(const std::string& path, const std::string& data) {
  std::string tmp = path + ".tmp";
  write_private(tmp, data, true);
  if (::rename(tmp.c_str(), path.c_str()) != 0)
    throw std::system_error(errno, std::generic_category(), "rename " + path);
}

std::vector<std::string> list_dir(const std::string& path) {
  std::vector<std::string> out;
  DIR* d = ::opendir(path.c_str());
  if (!d) return out;
  while (struct dirent* e = ::readdir(d)) {
    std::string name = e->d_name;
    if (name != "." && name != "..") out.push_back(name);
  }
  ::closedir(d);
  std::sort(out.begin(), out.end());
  return out;
}

std::string real_path(const std::string& path) {
  char buf[PATH_MAX];
  if (::realpath(path.c_str(), buf)) return buf;
  return "";
}

std::string exe_dir() {
  std::string exe = real_path("/proc/self/exe");
  if (exe.empty()) return ".";
  return parent_of(exe);
}

// ----------------------------------------------------------------------------- time, ids

double time_now() {
  struct timeval tv;
  gettimeofday(&tv, nullptr);
  return static_cast<double>(tv.tv_sec) + static_cast<double>(tv.tv_usec) / 1e6;
}

double now() { return std::round(time_now() * 1000.0) / 1000.0; }

std::string iso(double ts) {
  time_t secs = static_cast<time_t>(std::floor(ts));
  struct tm tm;
  gmtime_r(&secs, &tm);
  char buf[64];
  std::strftime(buf, sizeof buf, "%Y-%m-%dT%H:%M:%S.", &tm);
  long long ms = static_cast<long long>(ts * 1000) % 1000;
  if (ms < 0) ms += 1000;
  char tail[16];
  std::snprintf(tail, sizeof tail, "%03lldZ", ms);
  return std::string(buf) + tail;
}

std::string formatdate(double ts) {
  static const char* days[] = {"Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"};
  static const char* months[] = {"Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};
  time_t secs = static_cast<time_t>(ts ? ts : time_now());
  struct tm tm;
  gmtime_r(&secs, &tm);
  char buf[64];
  std::snprintf(buf, sizeof buf, "%s, %02d %s %04d %02d:%02d:%02d GMT", days[tm.tm_wday], tm.tm_mday,
                months[tm.tm_mon], tm.tm_year + 1900, tm.tm_hour, tm.tm_min, tm.tm_sec);
  return buf;
}

std::string random_bytes(size_t n) {
  std::string out(n, '\0');
  if (n && RAND_bytes(reinterpret_cast<unsigned char*>(&out[0]), static_cast<int>(n)) != 1)
    throw std::runtime_error("RAND_bytes failed");
  return out;
}

std::string uuid4() {
  std::string b = random_bytes(16);
  b[6] = static_cast<char>((b[6] & 0x0f) | 0x40);
  b[8] = static_cast<char>((b[8] & 0x3f) | 0x80);
  std::string h = hex(b);
  return h.substr(0, 8) + "-" + h.substr(8, 4) + "-" + h.substr(12, 4) + "-" + h.substr(16, 4) + "-" + h.substr(20);
}

std::string message_id() {
  char buf[32];
  std::snprintf(buf, sizeof buf, "%016llx", static_cast<unsigned long long>(time_now() * 1000));
  return std::string(buf) + "-" + uuid4() + "-000000";
}

std::string token(size_t nbytes) { return b64encode(random_bytes(nbytes)); }

std::string selector() {
  static const char* alphabet = "abcdefghijklmnopqrstuvwxyz234567";
  std::string out;
  while (out.size() < 32) {
    std::string r = random_bytes(32);
    for (unsigned char c : r) {
      if (out.size() == 32) break;
      out += alphabet[c & 31];
    }
  }
  return out;
}

// ----------------------------------------------------------------------------- addresses (email._parseaddr)

namespace {

const std::string SPECIALS = "()<>@,:;.\"[]";
const std::string LWS = " \t";
const std::string CR = "\r\n";
const std::string FWS = LWS + CR;
const std::string ATOMENDS = SPECIALS + LWS + CR;
const std::string PHRASEENDS = "()<>@,:;\"[]" + LWS + CR;  // atomends without '.'

bool in(char c, const std::string& set) { return set.find(c) != std::string::npos; }

struct AddressList {
  std::string field;
  size_t pos = 0;
  std::vector<std::string> commentlist;

  explicit AddressList(std::string f) : field(std::move(f)) {}

  std::string gotonext() {
    std::string ws;
    while (pos < field.size()) {
      char c = field[pos];
      if (in(c, LWS + "\n\r")) {
        if (c != '\n' && c != '\r') ws += c;
        ++pos;
      } else if (c == '(') {
        commentlist.push_back(getcomment());
      } else {
        break;
      }
    }
    return ws;
  }

  std::vector<NameAddr> getaddrlist() {
    std::vector<NameAddr> result;
    while (pos < field.size()) {
      std::vector<NameAddr> ad = getaddress();
      if (!ad.empty()) result.insert(result.end(), ad.begin(), ad.end());
      else result.emplace_back("", "");
    }
    return result;
  }

  std::vector<NameAddr> getaddress() {
    commentlist.clear();
    gotonext();
    size_t oldpos = pos;
    std::vector<std::string> oldcl = commentlist;
    std::vector<std::string> plist = getphraselist();
    gotonext();
    std::vector<NameAddr> ret;
    if (pos >= field.size()) {
      if (!plist.empty()) ret.emplace_back(join(commentlist, " "), plist[0]);
    } else if (in(field[pos], ".@")) {
      pos = oldpos;
      commentlist = oldcl;
      std::string spec = getaddrspec();
      ret.emplace_back(join(commentlist, " "), spec);
    } else if (field[pos] == ':') {
      ++pos;
      while (pos < field.size()) {
        gotonext();
        if (pos < field.size() && field[pos] == ';') {
          ++pos;
          break;
        }
        std::vector<NameAddr> more = getaddress();
        ret.insert(ret.end(), more.begin(), more.end());
      }
    } else if (field[pos] == '<') {
      std::string route = getrouteaddr();
      if (!commentlist.empty())
        ret.emplace_back(join(plist, " ") + " (" + join(commentlist, " ") + ")", route);
      else
        ret.emplace_back(join(plist, " "), route);
    } else {
      if (!plist.empty()) ret.emplace_back(join(commentlist, " "), plist[0]);
      else if (in(field[pos], SPECIALS)) ++pos;
    }
    gotonext();
    if (pos < field.size() && field[pos] == ',') ++pos;
    return ret;
  }

  std::string getrouteaddr() {
    if (field[pos] != '<') return "";
    bool expectroute = false;
    ++pos;
    gotonext();
    std::string adlist;
    while (pos < field.size()) {
      if (expectroute) {
        getdomain();
        expectroute = false;
      } else if (field[pos] == '>') {
        ++pos;
        break;
      } else if (field[pos] == '@') {
        ++pos;
        expectroute = true;
      } else if (field[pos] == ':') {
        ++pos;
      } else {
        adlist = getaddrspec();
        ++pos;
        break;
      }
      gotonext();
    }
    return adlist;
  }

  std::string getaddrspec() {
    std::vector<std::string> aslist;
    gotonext();
    while (pos < field.size()) {
      bool preserve_ws = true;
      char c = field[pos];
      if (c == '.') {
        if (!aslist.empty() && strip(aslist.back()).empty()) aslist.pop_back();
        aslist.push_back(".");
        ++pos;
        preserve_ws = false;
      } else if (c == '"') {
        std::string q = getquote();
        q = replace_all(replace_all(q, "\\", "\\\\"), "\"", "\\\"");
        aslist.push_back("\"" + q + "\"");
      } else if (in(c, ATOMENDS)) {
        if (!aslist.empty() && strip(aslist.back()).empty()) aslist.pop_back();
        break;
      } else {
        aslist.push_back(getatom(ATOMENDS));
      }
      std::string ws = gotonext();
      if (preserve_ws && !ws.empty()) aslist.push_back(ws);
    }
    std::string local = join(aslist, "");
    if (pos >= field.size() || field[pos] != '@') return local;
    ++pos;
    gotonext();
    std::string domain = getdomain();
    if (domain.empty()) return "";
    return local + "@" + domain;
  }

  std::string getdomain() {
    std::string sd;
    while (pos < field.size()) {
      char c = field[pos];
      if (in(c, LWS)) {
        ++pos;
      } else if (c == '(') {
        commentlist.push_back(getcomment());
      } else if (c == '[') {
        sd += "[" + getdelimited('[', "]\r", false) + "]";
      } else if (c == '.') {
        ++pos;
        sd += ".";
      } else if (c == '@') {
        return "";
      } else if (in(c, ATOMENDS)) {
        break;
      } else {
        sd += getatom(ATOMENDS);
      }
    }
    return sd;
  }

  std::string getdelimited(char begin, const std::string& endchars, bool allowcomments) {
    if (pos >= field.size() || field[pos] != begin) return "";
    std::string out;
    bool quoted = false;
    ++pos;
    while (pos < field.size()) {
      char c = field[pos];
      if (quoted) {
        out += c;
        quoted = false;
      } else if (in(c, endchars)) {
        ++pos;
        break;
      } else if (allowcomments && c == '(') {
        out += getcomment();
        continue;
      } else if (c == '\\') {
        quoted = true;
      } else {
        out += c;
      }
      ++pos;
    }
    return out;
  }

  std::string getquote() { return getdelimited('"', "\"\r", false); }
  std::string getcomment() { return getdelimited('(', ")\r", true); }

  std::string getatom(const std::string& ends) {
    std::string atom;
    while (pos < field.size() && !in(field[pos], ends)) atom += field[pos++];
    return atom;
  }

  std::vector<std::string> getphraselist() {
    std::vector<std::string> plist;
    while (pos < field.size()) {
      char c = field[pos];
      if (in(c, FWS)) {
        ++pos;
      } else if (c == '"') {
        plist.push_back(getquote());
      } else if (c == '(') {
        commentlist.push_back(getcomment());
      } else if (in(c, PHRASEENDS)) {
        break;
      } else {
        plist.push_back(getatom(PHRASEENDS));
      }
    }
    return plist;
  }
};

bool parens_balanced(const std::string& s) {
  int depth = 0;
  bool esc = false;
  for (char c : s) {
    if (esc) {
      esc = false;
    } else if (c == '\\') {
      esc = true;
    } else if (c == '(') {
      ++depth;
    } else if (c == ')') {
      if (--depth < 0) return false;
    }
  }
  return depth == 0;
}

}  // namespace

std::vector<NameAddr> getaddresses(const std::vector<std::string>& values) {
  for (const auto& v : values)
    if (!parens_balanced(v)) return {NameAddr("", "")};
  AddressList list(join(values, ", "));
  std::vector<NameAddr> out = list.getaddrlist();
  for (auto& pair : out)
    if (pair.second.find('[') != std::string::npos) return {NameAddr("", "")};
  return out;
}

NameAddr parseaddr(const std::string& text) {
  if (!parens_balanced(text)) return NameAddr("", "");
  AddressList list(text);
  std::vector<NameAddr> addrs = list.getaddrlist();
  if (addrs.size() != 1) return NameAddr("", "");
  if (addrs[0].second.find('[') != std::string::npos) return NameAddr("", "");
  return addrs[0];
}

std::string formataddr(const NameAddr& pair) {
  const std::string& name = pair.first;
  if (name.empty()) return pair.second;
  bool ascii = true;
  for (unsigned char c : name)
    if (c >= 0x80) ascii = false;
  if (!ascii) return "=?utf-8?b?" + b64encode(name) + "?= <" + pair.second + ">";
  bool special = name.find_first_of("][\\()<>@,:;\".") != std::string::npos;
  if (special) {
    std::string q = replace_all(replace_all(name, "\\", "\\\\"), "\"", "\\\"");
    return "\"" + q + "\" <" + pair.second + ">";
  }
  return name + " <" + pair.second + ">";
}

std::string address(const std::string& text) {
  std::string addr = strip(parseaddr(text).second);
  if (!email_re(addr)) return "";
  size_t at = addr.rfind('@');
  return addr.substr(0, at) + "@" + lower(addr.substr(at + 1));
}

std::vector<std::string> addresses(const Json& values) {
  std::vector<std::string> out;
  if (!truthy(values)) return out;
  std::vector<std::string> list;
  if (values.is_arr()) {
    for (const Json& v : values.arr()) list.push_back(py_str(v));
  } else {
    list.push_back(py_str(values));
  }
  for (const NameAddr& pair : getaddresses(list)) {
    std::string clean = address(pair.second);
    if (clean.empty()) throw bad_request("Illegal address: " + py_repr_str(pair.second) + ".");
    out.push_back(clean);
  }
  return out;
}

std::string domain_of(const std::string& addr) {
  size_t at = addr.rfind('@');
  return lower(at == std::string::npos ? addr : addr.substr(at + 1));
}

bool is_domain(const std::string& text) {
  if (text.empty() || text.size() > 253) return false;
  std::vector<std::string> labels = split(text, '.');
  if (labels.size() < 2) return false;
  for (const std::string& label : labels) {
    if (label.empty() || label.size() > 63 || label.front() == '-' || label.back() == '-') return false;
    for (char c : label)
      if (!(std::isalnum(static_cast<unsigned char>(c)) || c == '-')) return false;
  }
  return true;
}

bool email_re(const std::string& text) {
  size_t at = text.find('@');
  if (at == std::string::npos || text.find('@', at + 1) != std::string::npos) return false;
  std::string local = text.substr(0, at), domain = text.substr(at + 1);
  size_t n = utf8_len(local);
  if (n < 1 || n > 64) return false;
  for (size_t i = 0; i < local.size();) {
    size_t start = i;
    unsigned cp = next_utf8(local, i);
    (void)start;
    if (cp < 0x80 && (std::isspace(static_cast<int>(cp)) || std::strchr("<>()[],;:\"", static_cast<int>(cp))))
      return false;
    if (cp == 0x85 || cp == 0xa0 || cp == 0x1680 || (cp >= 0x2000 && cp <= 0x200a) || cp == 0x2028 ||
        cp == 0x2029 || cp == 0x202f || cp == 0x205f || cp == 0x3000 || (cp >= 0x1c && cp <= 0x1f))
      return false;
  }
  if (domain.empty() || domain.size() > 253) return false;
  for (char c : domain)
    if (!(std::isalnum(static_cast<unsigned char>(c)) || c == '.' || c == '-')) return false;
  return true;
}

bool is_email(const std::string& text) { return email_re(text) && is_domain(domain_of(text)); }

bool name_re(const std::string& text) {
  if (text.empty() || text.size() > 64) return false;
  for (char c : text)
    if (!(std::isalnum(static_cast<unsigned char>(c)) || c == '_' || c == '-')) return false;
  return true;
}

}  // namespace ses
