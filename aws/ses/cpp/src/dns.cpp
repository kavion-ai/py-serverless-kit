#include "dns.hpp"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <cstring>

#include "config.hpp"
#include "util.hpp"

namespace ses {

namespace {

const int MX = 15, TXT = 16;

std::pair<std::string, int> server() {
  std::string text = cfg.dns_server;
  if (text.empty()) {
    std::string conf;
    if (read_file("/etc/resolv.conf", conf)) {
      for (const std::string& line : split(conf, '\n')) {
        std::vector<std::string> parts = split_ws(line);
        if (parts.size() >= 2 && parts[0] == "nameserver") {
          text = parts[1];
          break;
        }
      }
    }
  }
  if (text.empty()) text = "1.1.1.1";
  if (text[0] == '[' && text.find("]:") != std::string::npos) {
    size_t at = text.find("]:");
    return {text.substr(1, at - 1), std::atoi(text.c_str() + at + 2)};
  }
  if (std::count(text.begin(), text.end(), ':') == 1) {
    size_t at = text.find(':');
    return {text.substr(0, at), std::atoi(text.c_str() + at + 1)};
  }
  return {text, 53};
}

std::string encode_name(const std::string& name) {
  std::string out;
  std::string n = name;
  while (!n.empty() && n.back() == '.') n.pop_back();
  for (const std::string& label : split(n, '.')) {
    out += static_cast<char>(label.size() & 0x3f);
    out += label.substr(0, 63);
  }
  out += '\0';
  return out;
}

unsigned u8(const std::string& m, size_t off) {
  if (off >= m.size()) throw DnsError{"DNS_SERVER_ERROR", "truncated DNS answer"};
  return static_cast<unsigned char>(m[off]);
}

unsigned u16(const std::string& m, size_t off) { return (u8(m, off) << 8) | u8(m, off + 1); }

std::pair<std::string, size_t> read_name(const std::string& msg, size_t off) {
  std::vector<std::string> labels;
  long end = -1;
  for (int k = 0; k < 128; ++k) {
    unsigned length = u8(msg, off);
    if ((length & 0xC0) == 0xC0) {
      if (end < 0) end = static_cast<long>(off + 2);
      off = ((length & 0x3F) << 8) | u8(msg, off + 1);
      continue;
    }
    if (length == 0) {
      ++off;
      break;
    }
    labels.push_back(msg.substr(off + 1, length));
    off += 1 + length;
  }
  return {join(labels, "."), end >= 0 ? static_cast<size_t>(end) : off};
}

bool make_addr(const std::string& host, int port, sockaddr_storage& ss, socklen_t& len, int& family) {
  std::memset(&ss, 0, sizeof ss);
  if (host.find(':') != std::string::npos) {
    auto* a = reinterpret_cast<sockaddr_in6*>(&ss);
    a->sin6_family = AF_INET6;
    a->sin6_port = htons(static_cast<uint16_t>(port));
    if (inet_pton(AF_INET6, host.c_str(), &a->sin6_addr) != 1) return false;
    len = sizeof *a;
    family = AF_INET6;
  } else {
    auto* a = reinterpret_cast<sockaddr_in*>(&ss);
    a->sin_family = AF_INET;
    a->sin_port = htons(static_cast<uint16_t>(port));
    if (inet_pton(AF_INET, host.c_str(), &a->sin_addr) != 1) return false;
    len = sizeof *a;
    family = AF_INET;
  }
  return true;
}

bool wait_fd(int fd, short events, double timeout) {
  pollfd p{fd, events, 0};
  int ms = static_cast<int>(timeout * 1000);
  while (true) {
    int r = poll(&p, 1, ms);
    if (r < 0 && errno == EINTR) continue;
    return r > 0;
  }
}

struct Fd {
  int fd;
  ~Fd() {
    if (fd >= 0) ::close(fd);
  }
};

std::string ask_tcp(const std::string& query, const sockaddr_storage& ss, socklen_t len, int family, double timeout) {
  Fd s{::socket(family, SOCK_STREAM | SOCK_CLOEXEC, 0)};
  if (s.fd < 0) throw DnsError{"DNS_SERVER_ERROR", std::strerror(errno)};
  timeval tv{static_cast<time_t>(timeout), static_cast<suseconds_t>((timeout - static_cast<long>(timeout)) * 1e6)};
  setsockopt(s.fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
  setsockopt(s.fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
  if (::connect(s.fd, reinterpret_cast<const sockaddr*>(&ss), len) != 0)
    throw DnsError{"DNS_SERVER_ERROR", std::strerror(errno)};
  std::string out;
  out += static_cast<char>((query.size() >> 8) & 0xff);
  out += static_cast<char>(query.size() & 0xff);
  out += query;
  if (::send(s.fd, out.data(), out.size(), MSG_NOSIGNAL) != static_cast<ssize_t>(out.size()))
    throw DnsError{"DNS_SERVER_ERROR", "send failed"};
  unsigned char head[2];
  if (::recv(s.fd, head, 2, MSG_WAITALL) != 2) throw DnsError{"DNS_SERVER_ERROR", "no TCP answer"};
  size_t size = (static_cast<size_t>(head[0]) << 8) | head[1];
  std::string data;
  char buf[4096];
  while (data.size() < size) {
    ssize_t n = ::recv(s.fd, buf, std::min(sizeof buf, size - data.size()), 0);
    if (n <= 0) break;
    data.append(buf, static_cast<size_t>(n));
  }
  return data;
}

std::string ask(const std::string& qname, int qtype, double timeout) {
  std::string id = random_bytes(2);
  std::string query = id + std::string("\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00", 10) + encode_name(qname);
  query += static_cast<char>(0);
  query += static_cast<char>(qtype);
  query += static_cast<char>(0);
  query += static_cast<char>(1);
  auto srv = server();
  sockaddr_storage ss;
  socklen_t len;
  int family;
  if (!make_addr(srv.first, srv.second, ss, len, family))
    throw DnsError{"DNS_SERVER_ERROR", "DNS lookup of " + qname + " failed: bad DNS server " + srv.first};
  Fd s{::socket(family, SOCK_DGRAM | SOCK_CLOEXEC, 0)};
  if (s.fd < 0) throw DnsError{"DNS_SERVER_ERROR", "DNS lookup of " + qname + " failed: " + std::strerror(errno)};
  for (int attempt = 0; attempt < 2; ++attempt) {
    if (::sendto(s.fd, query.data(), query.size(), 0, reinterpret_cast<const sockaddr*>(&ss), len) < 0)
      throw DnsError{"DNS_SERVER_ERROR", "DNS lookup of " + qname + " failed: " + std::strerror(errno)};
    double deadline = time_now() + timeout;
    while (true) {
      double left = deadline - time_now();
      if (left <= 0 || !wait_fd(s.fd, POLLIN, left)) break;
      char buf[4096];
      ssize_t n = ::recv(s.fd, buf, sizeof buf, 0);
      if (n < 0) {
        if (errno == EINTR) continue;
        throw DnsError{"DNS_SERVER_ERROR", "DNS lookup of " + qname + " failed: " + std::strerror(errno)};
      }
      std::string data(buf, static_cast<size_t>(n));
      if (data.size() >= 12 && data.compare(0, 2, id) == 0) {
        if (static_cast<unsigned char>(data[2]) & 0x02) return ask_tcp(query, ss, len, family, timeout);
        return data;
      }
    }
  }
  throw DnsError{"DNS_SERVER_ERROR",
                 "the DNS server " + srv.first + ":" + std::to_string(srv.second) + " did not answer"};
}

// (offset of the rdata, its length) of each answer of qtype, and the message they point into
std::vector<std::pair<size_t, size_t>> query(const std::string& qname, int qtype, double timeout, std::string& msg) {
  msg = ask(qname, qtype, timeout);
  if (msg.size() < 12) throw DnsError{"DNS_SERVER_ERROR", "truncated DNS answer"};
  unsigned rcode = u8(msg, 3) & 0x0F;
  if (rcode == 3) throw DnsError{"HOST_NOT_FOUND", qname + " does not exist (NXDOMAIN)"};
  if (rcode != 0)
    throw DnsError{"DNS_SERVER_ERROR", "the DNS server answered rcode " + std::to_string(rcode) + " for " + qname};
  unsigned qd = u16(msg, 4), an = u16(msg, 6);
  size_t off = 12;
  for (unsigned k = 0; k < qd; ++k) off = read_name(msg, off).second + 4;
  std::vector<std::pair<size_t, size_t>> out;
  for (unsigned k = 0; k < an; ++k) {
    off = read_name(msg, off).second;
    unsigned rtype = u16(msg, off), rdlen = u16(msg, off + 8);
    off += 10;
    if (static_cast<int>(rtype) == qtype) {
      if (off + rdlen > msg.size()) throw DnsError{"DNS_SERVER_ERROR", "truncated DNS answer"};
      out.emplace_back(off, rdlen);
    }
    off += rdlen;
  }
  return out;
}

}  // namespace

std::vector<std::pair<int, std::string>> dns_mx(const std::string& domain, double timeout) {
  std::string msg;
  std::vector<std::pair<int, std::string>> out;
  for (auto& rd : query(domain, MX, timeout, msg)) {
    int pref = static_cast<int>(u16(msg, rd.first));
    std::string host = read_name(msg, rd.first + 2).first;
    while (!host.empty() && host.back() == '.') host.pop_back();
    out.emplace_back(pref, lower(host));
  }
  if (out.empty()) return {{0, domain}};
  std::sort(out.begin(), out.end());
  if (out.size() == 1 && out[0].first == 0 && out[0].second.empty())
    throw DnsError{"TYPE_NOT_FOUND", domain + " accepts no mail (null MX)"};
  return out;
}

std::vector<std::string> dns_txt(const std::string& name, double timeout) {
  std::string msg;
  std::vector<std::string> out;
  for (auto& rd : query(name, TXT, timeout, msg)) {
    std::string data = msg.substr(rd.first, rd.second);
    std::string joined;
    size_t i = 0;
    while (i < data.size()) {
      size_t n = static_cast<unsigned char>(data[i]);
      joined += data.substr(i + 1, n);
      i += 1 + n;
    }
    out.push_back(sanitize_utf8(joined));
  }
  return out;
}

}  // namespace ses
