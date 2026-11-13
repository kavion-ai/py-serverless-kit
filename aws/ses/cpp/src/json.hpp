// JSON values with Python semantics: objects keep insertion order, numbers keep int vs float (as Python's json
// module does), and the serializer writes what Python's json.dumps writes (ensure_ascii, float repr, and for the data
// files indent=1 with sorted keys) so both servers produce the same files.
#pragma once

#include <cstddef>
#include <string>
#include <utility>
#include <vector>

namespace ses {

class Json {
 public:
  enum Type { NUL, BOOL, INT, FLOAT, STR, ARR, OBJ };
  using Items = std::vector<std::pair<std::string, Json>>;

  Json() = default;
  Json(std::nullptr_t) {}
  Json(bool v) : t_(BOOL), b_(v) {}
  Json(int v) : t_(INT), i_(v) {}
  Json(long v) : t_(INT), i_(v) {}
  Json(long long v) : t_(INT), i_(v) {}
  Json(unsigned v) : t_(INT), i_(v) {}
  Json(unsigned long v) : t_(INT), i_(static_cast<long long>(v)) {}
  Json(unsigned long long v) : t_(INT), i_(static_cast<long long>(v)) {}
  Json(double v) : t_(FLOAT), d_(v) {}
  Json(const char* v) : t_(STR), s_(v) {}
  Json(std::string v) : t_(STR), s_(std::move(v)) {}
  Json(std::vector<std::string> list);

  static Json array() { Json j; j.t_ = ARR; return j; }
  static Json object() { Json j; j.t_ = OBJ; return j; }
  static Json big_int(const std::string& digits) { Json j; j.t_ = INT; j.s_ = digits; return j; }

  Type type() const { return t_; }
  bool is_null() const { return t_ == NUL; }
  bool is_bool() const { return t_ == BOOL; }
  bool is_int() const { return t_ == INT; }
  bool is_float() const { return t_ == FLOAT; }
  bool is_number() const { return t_ == INT || t_ == FLOAT; }
  bool is_str() const { return t_ == STR; }
  bool is_arr() const { return t_ == ARR; }
  bool is_obj() const { return t_ == OBJ; }

  bool b() const { return b_; }
  long long i() const { return i_; }
  double d() const { return d_; }
  const std::string& s() const { return s_; }
  std::string& s() { return s_; }
  double num() const;  // INT / FLOAT / BOOL as a double

  // objects
  const Json* find(const std::string& key) const;
  Json* find(const std::string& key);
  bool has(const std::string& key) const { return find(key) != nullptr; }
  const Json& get(const std::string& key) const;  // a null value when missing (or not an object)
  Json& operator[](const std::string& key);       // inserts (turns a null into an object)
  void set(const std::string& key, Json value) { (*this)[key] = std::move(value); }
  bool erase(const std::string& key);
  Items& items() { return obj_; }
  const Items& items() const { return obj_; }

  // arrays
  std::vector<Json>& arr() { return arr_; }
  const std::vector<Json>& arr() const { return arr_; }
  void push(Json value);
  Json& operator[](size_t index) { return arr_[index]; }
  const Json& operator[](size_t index) const { return arr_[index]; }

  size_t size() const;
  bool operator==(const Json& other) const;
  bool operator!=(const Json& other) const { return !(*this == other); }

  bool big() const { return t_ == INT && !s_.empty(); }

 private:
  Type t_ = NUL;
  bool b_ = false;
  long long i_ = 0;
  double d_ = 0;
  std::string s_;  // STR; for INT the digits of an integer too large for 64 bits
  std::vector<Json> arr_;
  Items obj_;
};

struct JsonError {
  std::string message;
};

// Python's json.loads (accepts NaN / Infinity, rejects control characters in strings). Throws JsonError.
Json parse_json(const std::string& text);
// json.dumps(value): ", " and ": " separators, ensure_ascii.
std::string dump_json(const Json& value);
// json.dumps(value, indent=1, sort_keys=True): the data files.
std::string dump_json_file(const Json& value);

// Python semantics
bool truthy(const Json& value);            // bool(value)
std::string py_str(const Json& value);     // str(value)
std::string py_float_repr(double value);   // repr(float)
std::string py_int_str(const Json& value); // str(int)

}  // namespace ses
