// A small DNS client (MX, TXT): one question over UDP, again over TCP when the answer is truncated. The server is
// SES_DNS_SERVER (host or host:port), else the first nameserver of /etc/resolv.conf, else 1.1.1.1 (sesserver/dns.py).
#pragma once

#include <string>
#include <utility>
#include <vector>

namespace ses {

struct DnsError {
  std::string kind;  // HOST_NOT_FOUND, TYPE_NOT_FOUND or DNS_SERVER_ERROR
  std::string message;
};

std::vector<std::pair<int, std::string>> dns_mx(const std::string& domain, double timeout = 3.0);
std::vector<std::string> dns_txt(const std::string& name, double timeout = 3.0);

}  // namespace ses
