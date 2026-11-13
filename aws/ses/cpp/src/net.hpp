// Sockets: a buffered connection (plain or TLS through OpenSSL), listening and connecting.
#pragma once

#include <string>

typedef struct ssl_st SSL;
typedef struct ssl_ctx_st SSL_CTX;

namespace ses {

class Conn {
 public:
  explicit Conn(int fd = -1) : fd_(fd) {}
  ~Conn();
  Conn(const Conn&) = delete;
  Conn& operator=(const Conn&) = delete;

  void attach(int fd) {
    close();
    fd_ = fd;
  }
  int fd() const { return fd_; }
  bool secure() const { return ssl_ != nullptr; }
  void set_timeout(double seconds);
  // A line with its line ending, at most `max` bytes; false at EOF (or an error) with nothing read.
  bool read_line(std::string& out, size_t max);
  bool read_exact(size_t n, std::string& out);
  bool write_all(const std::string& data);
  bool start_tls_server(SSL_CTX* ctx);
  // verify: check the certificate and the host name. Fills `error` when the handshake fails.
  bool start_tls_client(const std::string& host, bool verify, std::string& error);
  std::string peer_ip() const;
  void close();
  bool has_buffered() const { return !buf_.empty(); }

 private:
  int fill();
  int fd_;
  SSL* ssl_ = nullptr;
  SSL_CTX* own_ctx_ = nullptr;
  std::string buf_;
};

int listen_on(const std::string& host, int port, std::string& error);  // -1 on failure
// Every address of host in turn (like socket.create_connection); -1 with `error` on failure.
int connect_to(const std::string& host, int port, double timeout, std::string& error);
SSL_CTX* server_tls_context(const std::string& cert, const std::string& key, std::string& error);
void init_openssl();

}  // namespace ses
