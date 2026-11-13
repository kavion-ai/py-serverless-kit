// RSA for DKIM through OpenSSL: key generation, DER (PKCS#1 private keys, SubjectPublicKeyInfo public keys),
// RSASSA-PKCS1-v1_5 SHA-256 signatures; plus the hashes the server needs (SHA-256, HMAC).
//
// Keys are stored as base64 DER of the PKCS#1 RSAPrivateKey, like the Python server's rsa.py. Bring-your-own keys
// may be PKCS#1 or PKCS#8, PEM or bare base64.
#pragma once

#include <memory>
#include <string>

typedef struct evp_pkey_st EVP_PKEY;

namespace ses {

std::string sha256(const std::string& data);
std::string hmac_sha256(const std::string& key, const std::string& data);
std::string hmac_md5(const std::string& key, const std::string& data);
bool const_eq(const std::string& a, const std::string& b);  // hmac.compare_digest

class Key {
 public:
  static Key generate(int bits);
  static Key load(const std::string& text);  // throws std::invalid_argument
  int bits() const;
  std::string private_b64() const;
  std::string public_b64() const;
  std::string sign_sha256(const std::string& data) const;

 private:
  std::shared_ptr<EVP_PKEY> pkey_;
};

bool verify_sha256(const std::string& spki_b64, const std::string& data, const std::string& signature);

}  // namespace ses
