// The HTTP/1.1 server (keep-alive, Content-Length bodies, a thread per connection) and the handler: the SES v1
// Query API (POST /), the SES v2 REST API (/v2/email/...), /health and the console (sesserver/handler.py).
#pragma once

#include <string>

namespace ses {

// The listening socket, or -1 with `error` filled.
int http_listen(const std::string& bind, int port, std::string& error);
// Accepts connections forever, a thread for each.
void http_serve(int fd);
// GET /health on the local server: the exit code of --check.
int http_check();

}  // namespace ses
