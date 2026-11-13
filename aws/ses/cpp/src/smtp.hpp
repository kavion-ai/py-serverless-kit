// The SMTP endpoint, like email-smtp.<region>.amazonaws.com: AUTH PLAIN / LOGIN with the access key ID and its SES
// SMTP password (or the secret key), STARTTLS with SES_TLS_CERT / SES_TLS_KEY; each message goes through the same
// checks as SendRawEmail (sesserver/smtp.py).
#pragma once

#include <string>

namespace ses {

// Listens and serves in a background thread. False when it cannot listen or load the TLS files.
bool serve_smtp(const std::string& bind, int port, std::string& error);

}  // namespace ses
