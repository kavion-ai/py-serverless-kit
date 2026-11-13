#include "net.hpp"

#include <arpa/inet.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <openssl/err.h>
#include <openssl/ssl.h>
#include <openssl/x509v3.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <cstring>

namespace ses {

void init_openssl() { OPENSSL_init_ssl(0, nullptr); }

static std::string ssl_error() {
  unsigned long e = ERR_get_error();
  if (!e) return "TLS error";
  char buf[256];
  ERR_error_string_n(e, buf, sizeof buf);
  ERR_clear_error();
  return buf;
}

Conn::~Conn() { close(); }

void Conn::close() {
  if (ssl_) {
    SSL_shutdown(ssl_);
    SSL_free(ssl_);
    ssl_ = nullptr;
  }
  if (own_ctx_) {
    SSL_CTX_free(own_ctx_);
    own_ctx_ = nullptr;
  }
  if (fd_ >= 0) {
    ::close(fd_);
    fd_ = -1;
  }
}

void Conn::set_timeout(double seconds) {
  if (fd_ < 0) return;
  timeval tv{static_cast<time_t>(seconds), static_cast<suseconds_t>((seconds - static_cast<long>(seconds)) * 1e6)};
  setsockopt(fd_, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
  setsockopt(fd_, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
}

int Conn::fill() {
  char tmp[16384];
  while (true) {
    int n;
    if (ssl_) {
      n = SSL_read(ssl_, tmp, sizeof tmp);
      if (n <= 0) {
        int err = SSL_get_error(ssl_, n);
        if (err == SSL_ERROR_WANT_READ || err == SSL_ERROR_WANT_WRITE) continue;
        return -1;
      }
    } else {
      ssize_t r = ::recv(fd_, tmp, sizeof tmp, 0);
      if (r < 0 && errno == EINTR) continue;
      if (r <= 0) return -1;
      n = static_cast<int>(r);
    }
    buf_.append(tmp, static_cast<size_t>(n));
    return n;
  }
}

bool Conn::read_line(std::string& out, size_t max) {
  out.clear();
  while (true) {
    size_t nl = buf_.find('\n');
    if (nl != std::string::npos && nl < max) {
      out = buf_.substr(0, nl + 1);
      buf_.erase(0, nl + 1);
      return true;
    }
    if (buf_.size() >= max) {
      out = buf_.substr(0, max);
      buf_.erase(0, max);
      return true;
    }
    if (fd_ < 0 || fill() <= 0) {
      out = buf_;
      buf_.clear();
      return !out.empty();
    }
  }
}

bool Conn::read_exact(size_t n, std::string& out) {
  while (buf_.size() < n)
    if (fd_ < 0 || fill() <= 0) return false;
  out = buf_.substr(0, n);
  buf_.erase(0, n);
  return true;
}

bool Conn::write_all(const std::string& data) {
  size_t off = 0;
  while (off < data.size()) {
    if (ssl_) {
      int n = SSL_write(ssl_, data.data() + off, static_cast<int>(std::min<size_t>(data.size() - off, 1 << 20)));
      if (n <= 0) {
        int err = SSL_get_error(ssl_, n);
        if (err == SSL_ERROR_WANT_READ || err == SSL_ERROR_WANT_WRITE) continue;
        return false;
      }
      off += static_cast<size_t>(n);
    } else {
      ssize_t n = ::send(fd_, data.data() + off, data.size() - off, MSG_NOSIGNAL);
      if (n < 0 && errno == EINTR) continue;
      if (n <= 0) return false;
      off += static_cast<size_t>(n);
    }
  }
  return true;
}

bool Conn::start_tls_server(SSL_CTX* ctx) {
  buf_.clear();
  ssl_ = SSL_new(ctx);
  if (!ssl_) return false;
  SSL_set_fd(ssl_, fd_);
  if (SSL_accept(ssl_) <= 0) {
    ERR_clear_error();
    SSL_free(ssl_);
    ssl_ = nullptr;
    return false;
  }
  return true;
}

bool Conn::start_tls_client(const std::string& host, bool verify, std::string& error) {
  buf_.clear();
  own_ctx_ = SSL_CTX_new(TLS_client_method());
  if (!own_ctx_) {
    error = ssl_error();
    return false;
  }
  SSL_CTX_set_min_proto_version(own_ctx_, TLS1_2_VERSION);
  if (verify) {
    SSL_CTX_set_default_verify_paths(own_ctx_);
    SSL_CTX_set_verify(own_ctx_, SSL_VERIFY_PEER, nullptr);
  } else {
    SSL_CTX_set_verify(own_ctx_, SSL_VERIFY_NONE, nullptr);
  }
  ssl_ = SSL_new(own_ctx_);
  SSL_set_fd(ssl_, fd_);
  in6_addr a6;
  in_addr a4;
  bool is_ip = inet_pton(AF_INET, host.c_str(), &a4) == 1 || inet_pton(AF_INET6, host.c_str(), &a6) == 1;
  if (!is_ip) SSL_set_tlsext_host_name(ssl_, host.c_str());
  if (verify) {
    X509_VERIFY_PARAM* param = SSL_get0_param(ssl_);
    if (is_ip) X509_VERIFY_PARAM_set1_ip_asc(param, host.c_str());
    else X509_VERIFY_PARAM_set1_host(param, host.c_str(), 0);
  }
  if (SSL_connect(ssl_) <= 0) {
    error = ssl_error();
    long vr = SSL_get_verify_result(ssl_);
    if (vr != X509_V_OK) error = std::string("certificate verify failed: ") + X509_verify_cert_error_string(vr);
    SSL_free(ssl_);
    ssl_ = nullptr;
    return false;
  }
  return true;
}

std::string Conn::peer_ip() const {
  sockaddr_storage ss;
  socklen_t len = sizeof ss;
  if (fd_ < 0 || getpeername(fd_, reinterpret_cast<sockaddr*>(&ss), &len) != 0) return "";
  char buf[INET6_ADDRSTRLEN] = {0};
  if (ss.ss_family == AF_INET) {
    inet_ntop(AF_INET, &reinterpret_cast<sockaddr_in*>(&ss)->sin_addr, buf, sizeof buf);
  } else if (ss.ss_family == AF_INET6) {
    auto* a = reinterpret_cast<sockaddr_in6*>(&ss);
    if (IN6_IS_ADDR_V4MAPPED(&a->sin6_addr)) {
      inet_ntop(AF_INET, reinterpret_cast<const char*>(&a->sin6_addr) + 12, buf, sizeof buf);
    } else {
      inet_ntop(AF_INET6, &a->sin6_addr, buf, sizeof buf);
    }
  }
  return buf;
}

int listen_on(const std::string& host, int port, std::string& error) {
  addrinfo hints;
  std::memset(&hints, 0, sizeof hints);
  hints.ai_family = host.find(':') != std::string::npos ? AF_INET6 : AF_INET;
  hints.ai_socktype = SOCK_STREAM;
  hints.ai_flags = AI_PASSIVE;
  addrinfo* res = nullptr;
  std::string svc = std::to_string(port);
  int rc = getaddrinfo(host.empty() ? nullptr : host.c_str(), svc.c_str(), &hints, &res);
  if (rc != 0) {
    error = gai_strerror(rc);
    return -1;
  }
  int fd = -1;
  for (addrinfo* ai = res; ai; ai = ai->ai_next) {
    fd = ::socket(ai->ai_family, ai->ai_socktype | SOCK_CLOEXEC, ai->ai_protocol);
    if (fd < 0) continue;
    int one = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    if (::bind(fd, ai->ai_addr, ai->ai_addrlen) == 0 && ::listen(fd, 128) == 0) break;
    error = std::strerror(errno);
    ::close(fd);
    fd = -1;
  }
  freeaddrinfo(res);
  return fd;
}

int connect_to(const std::string& host, int port, double timeout, std::string& error) {
  addrinfo hints;
  std::memset(&hints, 0, sizeof hints);
  hints.ai_family = AF_UNSPEC;
  hints.ai_socktype = SOCK_STREAM;
  addrinfo* res = nullptr;
  std::string svc = std::to_string(port);
  std::string h = host;
  if (h.size() > 2 && h.front() == '[' && h.back() == ']') h = h.substr(1, h.size() - 2);
  int rc = getaddrinfo(h.c_str(), svc.c_str(), &hints, &res);
  if (rc != 0) {
    error = std::string("[Errno ") + std::to_string(rc) + "] " + gai_strerror(rc);
    return -1;
  }
  int fd = -1;
  error = "no address";
  for (addrinfo* ai = res; ai; ai = ai->ai_next) {
    fd = ::socket(ai->ai_family, ai->ai_socktype | SOCK_CLOEXEC, ai->ai_protocol);
    if (fd < 0) {
      error = std::strerror(errno);
      continue;
    }
    int flags = fcntl(fd, F_GETFL, 0);
    fcntl(fd, F_SETFL, flags | O_NONBLOCK);
    int r = ::connect(fd, ai->ai_addr, ai->ai_addrlen);
    if (r != 0 && errno == EINPROGRESS) {
      pollfd p{fd, POLLOUT, 0};
      int pr;
      do {
        pr = poll(&p, 1, static_cast<int>(timeout * 1000));
      } while (pr < 0 && errno == EINTR);
      if (pr == 1) {
        int err = 0;
        socklen_t len = sizeof err;
        getsockopt(fd, SOL_SOCKET, SO_ERROR, &err, &len);
        r = err ? -1 : 0;
        if (err) errno = err;
      } else {
        r = -1;
        errno = pr == 0 ? ETIMEDOUT : errno;
      }
    }
    if (r == 0) {
      fcntl(fd, F_SETFL, flags);
      int one = 1;
      setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
      break;
    }
    error = std::string("[Errno ") + std::to_string(errno) + "] " + std::strerror(errno);
    ::close(fd);
    fd = -1;
  }
  freeaddrinfo(res);
  return fd;
}

SSL_CTX* server_tls_context(const std::string& cert, const std::string& key, std::string& error) {
  SSL_CTX* ctx = SSL_CTX_new(TLS_server_method());
  if (!ctx) {
    error = ssl_error();
    return nullptr;
  }
  SSL_CTX_set_min_proto_version(ctx, TLS1_2_VERSION);
  if (SSL_CTX_use_certificate_chain_file(ctx, cert.c_str()) != 1 ||
      SSL_CTX_use_PrivateKey_file(ctx, key.c_str(), SSL_FILETYPE_PEM) != 1 || SSL_CTX_check_private_key(ctx) != 1) {
    error = ssl_error();
    SSL_CTX_free(ctx);
    return nullptr;
  }
  return ctx;
}

}  // namespace ses
