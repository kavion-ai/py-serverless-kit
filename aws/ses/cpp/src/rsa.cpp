#include "rsa.hpp"

#include <openssl/crypto.h>
#include <openssl/evp.h>
#include <openssl/hmac.h>
#include <openssl/rsa.h>
#include <openssl/x509.h>

#include <stdexcept>
#include <vector>

#include "util.hpp"

namespace ses {

std::string sha256(const std::string& data) {
  unsigned char md[EVP_MAX_MD_SIZE];
  unsigned int len = 0;
  EVP_Digest(data.data(), data.size(), md, &len, EVP_sha256(), nullptr);
  return std::string(reinterpret_cast<char*>(md), len);
}

static std::string hmac(const EVP_MD* md, const std::string& key, const std::string& data) {
  unsigned char out[EVP_MAX_MD_SIZE];
  unsigned int len = 0;
  HMAC(md, key.data(), static_cast<int>(key.size()), reinterpret_cast<const unsigned char*>(data.data()), data.size(),
       out, &len);
  return std::string(reinterpret_cast<char*>(out), len);
}

std::string hmac_sha256(const std::string& key, const std::string& data) { return hmac(EVP_sha256(), key, data); }
std::string hmac_md5(const std::string& key, const std::string& data) { return hmac(EVP_md5(), key, data); }

bool const_eq(const std::string& a, const std::string& b) {
  if (a.size() != b.size()) {
    CRYPTO_memcmp(a.data(), a.data(), a.size());
    return false;
  }
  return a.empty() || CRYPTO_memcmp(a.data(), b.data(), a.size()) == 0;
}

static std::shared_ptr<EVP_PKEY> wrap(EVP_PKEY* p) { return std::shared_ptr<EVP_PKEY>(p, EVP_PKEY_free); }

Key Key::generate(int bits) {
  EVP_PKEY_CTX* ctx = EVP_PKEY_CTX_new_id(EVP_PKEY_RSA, nullptr);
  if (!ctx) throw std::runtime_error("EVP_PKEY_CTX_new_id failed");
  EVP_PKEY* p = nullptr;
  bool ok = EVP_PKEY_keygen_init(ctx) > 0 && EVP_PKEY_CTX_set_rsa_keygen_bits(ctx, bits) > 0 &&
            EVP_PKEY_keygen(ctx, &p) > 0;
  EVP_PKEY_CTX_free(ctx);
  if (!ok || !p) throw std::runtime_error("RSA key generation failed");
  Key key;
  key.pkey_ = wrap(p);
  return key;
}

Key Key::load(const std::string& text) {
  std::string body;
  for (const std::string& raw : split(replace_all(text, "\r", "\n"), '\n')) {
    std::string line = strip(raw);
    if (line.empty() || starts_with(line, "-----")) continue;
    body += line;
  }
  std::string der;
  try {
    der = b64decode(body);
  } catch (const std::invalid_argument& e) {
    throw std::invalid_argument(e.what());
  }
  if (der.empty()) throw std::invalid_argument("truncated DER");
  const unsigned char* p = reinterpret_cast<const unsigned char*>(der.data());
  EVP_PKEY* pkey = d2i_AutoPrivateKey(nullptr, &p, static_cast<long>(der.size()));
  if (!pkey) {
    p = reinterpret_cast<const unsigned char*>(der.data());
    pkey = d2i_PrivateKey(EVP_PKEY_RSA, nullptr, &p, static_cast<long>(der.size()));
  }
  if (!pkey) throw std::invalid_argument("not an RSA private key");
  Key key;
  key.pkey_ = wrap(pkey);
  if (EVP_PKEY_base_id(pkey) != EVP_PKEY_RSA) throw std::invalid_argument("not an RSA private key");
  return key;
}

int Key::bits() const { return EVP_PKEY_bits(pkey_.get()); }

std::string Key::private_b64() const {
  unsigned char* buf = nullptr;
  int len = i2d_PrivateKey(pkey_.get(), &buf);
  if (len <= 0) throw std::runtime_error("cannot encode the private key");
  std::string der(reinterpret_cast<char*>(buf), static_cast<size_t>(len));
  OPENSSL_free(buf);
  return b64encode(der);
}

std::string Key::public_b64() const {
  unsigned char* buf = nullptr;
  int len = i2d_PUBKEY(pkey_.get(), &buf);
  if (len <= 0) throw std::runtime_error("cannot encode the public key");
  std::string der(reinterpret_cast<char*>(buf), static_cast<size_t>(len));
  OPENSSL_free(buf);
  return b64encode(der);
}

std::string Key::sign_sha256(const std::string& data) const {
  EVP_MD_CTX* ctx = EVP_MD_CTX_new();
  size_t len = 0;
  std::vector<unsigned char> sig;
  bool ok = EVP_DigestSignInit(ctx, nullptr, EVP_sha256(), nullptr, pkey_.get()) > 0 &&
            EVP_DigestSign(ctx, nullptr, &len, reinterpret_cast<const unsigned char*>(data.data()), data.size()) > 0;
  if (ok) {
    sig.resize(len);
    ok = EVP_DigestSign(ctx, sig.data(), &len, reinterpret_cast<const unsigned char*>(data.data()), data.size()) > 0;
  }
  EVP_MD_CTX_free(ctx);
  if (!ok) throw std::runtime_error("RSA signature failed");
  return std::string(reinterpret_cast<char*>(sig.data()), len);
}

bool verify_sha256(const std::string& spki_b64, const std::string& data, const std::string& signature) {
  std::string der;
  try {
    der = b64decode(spki_b64);
  } catch (const std::invalid_argument&) {
    return false;
  }
  const unsigned char* p = reinterpret_cast<const unsigned char*>(der.data());
  EVP_PKEY* pkey = d2i_PUBKEY(nullptr, &p, static_cast<long>(der.size()));
  if (!pkey) return false;
  EVP_MD_CTX* ctx = EVP_MD_CTX_new();
  bool ok = EVP_DigestVerifyInit(ctx, nullptr, EVP_sha256(), nullptr, pkey) > 0 &&
            EVP_DigestVerify(ctx, reinterpret_cast<const unsigned char*>(signature.data()), signature.size(),
                             reinterpret_cast<const unsigned char*>(data.data()), data.size()) == 1;
  EVP_MD_CTX_free(ctx);
  EVP_PKEY_free(pkey);
  return ok;
}

}  // namespace ses
