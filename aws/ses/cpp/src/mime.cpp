#include "mime.hpp"

#include <algorithm>
#include <cctype>
#include <set>

#include "dkim.hpp"
#include "errors.hpp"
#include "util.hpp"

namespace ses {

namespace {

const std::set<std::string> RESERVED = {"from",         "to",          "cc",
                                        "bcc",          "subject",     "reply-to",
                                        "return-path",  "date",        "message-id",
                                        "mime-version", "content-type", "content-transfer-encoding",
                                        "dkim-signature", "received",  "sender"};

bool is_ascii(const std::string& s) {
  for (unsigned char c : s)
    if (c >= 0x80) return false;
  return true;
}

// RFC 2047 encoded words (B encoding), each at most 75 characters, split on character boundaries.
std::string encode_words(const std::string& text) {
  std::vector<std::string> words;
  std::string chunk;
  for (size_t i = 0; i < text.size();) {
    size_t start = i;
    next_utf8(text, i);
    std::string ch = text.substr(start, i - start);
    if (chunk.size() + ch.size() > 45) {
      words.push_back("=?utf-8?b?" + b64encode(chunk) + "?=");
      chunk.clear();
    }
    chunk += ch;
  }
  if (!chunk.empty() || words.empty()) words.push_back("=?utf-8?b?" + b64encode(chunk) + "?=");
  return join(words, "\r\n ");
}

std::string header_value(const std::string& value) { return is_ascii(value) ? value : encode_words(value); }

// An address header value: each address re-rendered (quoted display names, non-ASCII names encoded).
std::string address_value(const std::string& value) {
  std::vector<NameAddr> pairs = getaddresses({value});
  std::vector<std::string> out;
  for (auto& p : pairs) {
    if (p.second.empty()) return header_value(value);
    out.push_back(formataddr(p));
  }
  return out.empty() ? header_value(value) : join(out, ", ");
}

std::vector<std::string> bytes_lines(const std::string& s) {  // bytes.splitlines()
  std::vector<std::string> lines;
  std::string cur;
  for (size_t i = 0; i < s.size(); ++i) {
    char c = s[i];
    if (c == '\r' || c == '\n') {
      lines.push_back(cur);
      cur.clear();
      if (c == '\r' && i + 1 < s.size() && s[i + 1] == '\n') ++i;
    } else {
      cur += c;
    }
  }
  if (!cur.empty()) lines.push_back(cur);
  return lines;
}

std::string qp_encode(const std::vector<std::string>& lines) {
  static const char* digits = "0123456789ABCDEF";
  std::string out;
  for (const std::string& line : lines) {
    std::string cur;
    for (size_t i = 0; i < line.size(); ++i) {
      unsigned char c = static_cast<unsigned char>(line[i]);
      std::string enc;
      bool last = i + 1 == line.size();
      if ((c >= 33 && c <= 126 && c != '=') || ((c == ' ' || c == '\t') && !last)) {
        enc = std::string(1, static_cast<char>(c));
      } else {
        enc = "=";
        enc += digits[c >> 4];
        enc += digits[c & 15];
      }
      if (cur.size() + enc.size() > 75) {
        out += cur + "=\r\n";
        cur.clear();
      }
      cur += enc;
    }
    out += cur + "\r\n";
  }
  return out;
}

std::string b64_lines(const std::string& data) {
  std::string enc = b64encode(data), out;
  for (size_t i = 0; i < enc.size(); i += 76) out += enc.substr(i, 76) + "\r\n";
  return out;
}

struct Part {
  std::vector<std::pair<std::string, std::string>> headers;
  std::string body;  // the encoded body, CRLF lines
  std::vector<Part> children;
  std::string boundary;
};

std::string boundary() {
  std::string digits;
  for (unsigned char c : random_bytes(19)) digits += static_cast<char>('0' + c % 10);
  return "===============" + digits + "==";
}

Part text_part(const std::string& content, const std::string& subtype) {
  std::vector<std::string> lines = bytes_lines(content);
  size_t longest = 0;
  for (auto& l : lines) longest = std::max(longest, l.size());
  Part p;
  p.headers.emplace_back("Content-Type", "text/" + subtype + "; charset=\"utf-8\"");
  if (longest <= 78 && is_ascii(content)) {
    p.headers.emplace_back("Content-Transfer-Encoding", "7bit");
    std::string body;
    for (auto& l : lines) body += l + "\r\n";
    p.body = lines.empty() ? "\r\n" : body;
    return p;
  }
  std::string normal;
  for (auto& l : lines) normal += l + "\n";
  std::string qp = qp_encode(lines), b64 = b64_lines(normal);
  if (qp.size() > b64.size()) {
    p.headers.emplace_back("Content-Transfer-Encoding", "base64");
    p.body = b64;
  } else {
    p.headers.emplace_back("Content-Transfer-Encoding", "quoted-printable");
    p.body = qp;
  }
  return p;
}

std::string quote_param(const std::string& value) {
  return "\"" + replace_all(replace_all(value, "\\", "\\\\"), "\"", "\\\"") + "\"";
}

std::string render(const Part& part) {
  std::string out;
  for (auto& h : part.headers) out += h.first + ": " + h.second + "\r\n";
  out += "\r\n";
  if (part.children.empty()) return out + part.body;
  // Each part keeps its final line break; the CRLF before a delimiter belongs to the delimiter (RFC 2046).
  for (size_t i = 0; i < part.children.size(); ++i) {
    out += (i ? "\r\n--" : "--") + part.boundary + "\r\n";
    out += render(part.children[i]);
  }
  out += "\r\n--" + part.boundary + "--\r\n";
  return out;
}

Part multipart(const std::string& subtype, std::vector<Part> children) {
  Part p;
  p.boundary = boundary();
  p.headers.emplace_back("Content-Type", "multipart/" + subtype + "; boundary=\"" + p.boundary + "\"");
  p.children = std::move(children);
  return p;
}

std::string str_of(const Json& v) { return truthy(v) ? py_str(v) : ""; }

}  // namespace

std::string mime_build(const BuildArgs& a) {
  std::vector<std::pair<std::string, std::string>> top;
  top.emplace_back("From", address_value(a.source));
  if (!a.to.empty()) top.emplace_back("To", join(a.to, ", "));
  if (!a.cc.empty()) top.emplace_back("Cc", join(a.cc, ", "));
  if (!a.reply_to.empty()) top.emplace_back("Reply-To", join(a.reply_to, ", "));
  if (a.subject.find_first_of("\r\n") != std::string::npos)
    throw bad_request("Header values may not contain linefeed or carriage return characters");
  top.emplace_back("Subject", header_value(a.subject));
  top.emplace_back("Date", formatdate(a.date));
  if (!a.message_id.empty()) top.emplace_back("Message-ID", a.message_id);
  if (a.headers.is_arr()) {
    for (const Json& h : a.headers.arr()) {
      std::string name = str_of(h.get("Name")), value = str_of(h.get("Value"));
      if (name.empty() || RESERVED.count(lower(name)) || (name + value).find_first_of("\r\n") != std::string::npos)
        throw bad_request("The header " + py_repr_str(name) +
                          " can't be set (it is reserved, empty or has a line break).");
      top.emplace_back(name, header_value(value));
    }
  }
  top.emplace_back("MIME-Version", "1.0");
  Part content;
  if (a.has_text && a.has_html) {
    content = multipart("alternative", {text_part(a.text, "plain"), text_part(a.html, "html")});
  } else if (a.has_html) {
    content = text_part(a.html, "html");
  } else {
    content = text_part(a.text, "plain");
  }
  if (a.attachments.is_arr() && !a.attachments.arr().empty()) {
    std::vector<Part> parts{content};
    for (const Json& att : a.attachments.arr()) {
      std::string data;
      try {
        data = b64decode(str_of(att.get("RawContent")));
      } catch (const std::exception&) {
        throw bad_request("Attachment RawContent must be base64.");
      }
      std::string ctype = str_of(att.get("ContentType"));
      if (ctype.empty()) ctype = "application/octet-stream";
      size_t slash = ctype.find('/');
      std::string maintype = slash == std::string::npos ? ctype : ctype.substr(0, slash);
      std::string subtype = slash == std::string::npos ? "" : ctype.substr(slash + 1);
      if (maintype.empty()) maintype = "application";
      if (subtype.empty()) subtype = "octet-stream";
      std::string disposition = upper(str_of(att.get("ContentDisposition"))) == "INLINE" ? "inline" : "attachment";
      std::string name = str_of(att.get("FileName"));
      if (name.empty()) name = "attachment";
      Part p;
      p.headers.emplace_back("Content-Type", maintype + "/" + subtype);
      p.headers.emplace_back("Content-Transfer-Encoding", "base64");
      std::string disp = disposition + "; ";
      if (is_ascii(name) && name.find_first_of("\r\n") == std::string::npos)
        disp += "filename=" + quote_param(name);
      else
        disp += "filename*=utf-8''" + quote(name, "");
      p.headers.emplace_back("Content-Disposition", disp);
      std::string cid = str_of(att.get("ContentId"));
      if (!cid.empty()) p.headers.emplace_back("Content-ID", "<" + strip(cid, "<>") + ">");
      std::string desc = str_of(att.get("ContentDescription"));
      if (!desc.empty()) p.headers.emplace_back("Content-Description", header_value(desc));
      p.body = b64_lines(data);
      parts.push_back(std::move(p));
    }
    content = multipart("mixed", std::move(parts));
  }
  Part message = content;
  message.headers = top;
  message.headers.insert(message.headers.end(), content.headers.begin(), content.headers.end());
  return crlf(render(message));
}

std::string mime_simple(const std::string& source, const std::vector<std::string>& to,
                        const std::vector<std::string>& cc, const std::vector<std::string>& reply_to,
                        const Json& message, const std::string& message_id, double date) {
  BuildArgs a;
  a.source = source;
  a.to = to;
  a.cc = cc;
  a.reply_to = reply_to;
  const Json& subject = message.get("Subject");
  a.subject = subject.is_obj() ? str_of(subject.get("Data")) : "";
  const Json& body = message.get("Body");
  const Json& text = body.get("Text");
  const Json& html = body.get("Html");
  if (truthy(text)) {
    a.has_text = true;
    a.text = text.is_obj() ? str_of(text.get("Data")) : "";
  }
  if (truthy(html)) {
    a.has_html = true;
    a.html = html.is_obj() ? str_of(html.get("Data")) : "";
  }
  if (!a.has_text && !a.has_html) throw bad_request("Message.Body needs Text or Html.");
  a.headers = message.get("Headers");
  a.attachments = message.get("Attachments");
  a.message_id = message_id;
  a.date = date;
  return mime_build(a);
}

std::string prepare_raw(const std::string& raw_in, const std::string& message_id, double date) {
  std::string raw = crlf(raw_in);
  auto parts = split_message(raw);
  std::vector<Field> fields = header_fields(parts.first);
  if (fields.empty()) throw bad_request("The raw message has no headers.");
  std::vector<std::string> kept;
  std::set<std::string> names;
  for (auto& f : fields) {
    names.insert(f.first);
    if (f.first != "bcc" && f.first != "return-path") kept.push_back(f.second);
  }
  if (!names.count("date")) kept.push_back("Date: " + formatdate(date));
  if (!names.count("message-id") && !message_id.empty()) kept.push_back("Message-ID: " + message_id);
  if (!names.count("mime-version")) kept.push_back("MIME-Version: 1.0");
  return join(kept, "\r\n") + "\r\n\r\n" + parts.second;
}

// ----------------------------------------------------------------------------- reading

namespace {

struct Header {
  std::string name, value;  // value: unfolded, not decoded
};

std::vector<Header> parse_headers(const std::string& head) {
  std::vector<Header> out;
  for (auto& f : header_fields(head)) {
    size_t colon = f.second.find(':');
    if (colon == std::string::npos) continue;
    Header h;
    h.name = f.second.substr(0, colon);
    std::string value = lstrip(f.second.substr(colon + 1), " \t");
    h.value = replace_all(value, "\r\n", "");
    out.push_back(h);
  }
  return out;
}

const Header* find_header(const std::vector<Header>& headers, const std::string& name) {
  for (auto& h : headers)
    if (lower(h.name) == lower(name)) return &h;
  return nullptr;
}

std::string charset_decode(const std::string& data, const std::string& charset) {
  std::string cs = lower(charset);
  if (cs == "iso-8859-1" || cs == "latin-1" || cs == "latin1" || cs == "iso8859-1" || cs == "windows-1252" ||
      cs == "cp1252")
    return latin1_to_utf8(data);
  return sanitize_utf8(data);
}

std::string qp_decode(const std::string& data, bool header) {
  std::string out;
  std::vector<std::string> lines = split(data, '\n');
  for (size_t li = 0; li < lines.size(); ++li) {
    std::string line = lines[li];
    bool had_newline = li + 1 < lines.size();
    bool cr = false;  // binascii.a2b_qp keeps a hard line break as it was (CRLF or LF)
    if (header) {
      line = replace_all(line, "_", " ");
    } else {
      cr = !line.empty() && line.back() == '\r';
      if (cr) line.pop_back();
    }
    std::string trimmed = rstrip(line, " \t");
    bool soft = !header && !trimmed.empty() && trimmed.back() == '=';
    if (soft) line = trimmed.substr(0, trimmed.size() - 1);
    for (size_t i = 0; i < line.size(); ++i) {
      if (line[i] == '=' && i + 2 < line.size() && std::isxdigit(static_cast<unsigned char>(line[i + 1])) &&
          std::isxdigit(static_cast<unsigned char>(line[i + 2]))) {
        out += static_cast<char>(std::stoi(line.substr(i + 1, 2), nullptr, 16));
        i += 2;
      } else {
        out += line[i];
      }
    }
    if (had_newline && !soft) out += cr ? "\r\n" : "\n";
  }
  return out;
}

// RFC 2047: =?charset?B|Q?text?= words, the whitespace between two words dropped.
std::string decode_words(const std::string& value) {
  std::string out, pending_ws;
  bool last_word = false;
  size_t i = 0;
  while (i < value.size()) {
    if (value.compare(i, 2, "=?") == 0) {
      size_t q1 = value.find('?', i + 2);
      size_t q2 = q1 == std::string::npos ? q1 : value.find('?', q1 + 1);
      size_t end = q2 == std::string::npos ? q2 : value.find("?=", q2 + 1);
      if (end != std::string::npos && q2 == q1 + 2) {
        std::string charset = value.substr(i + 2, q1 - i - 2);
        size_t star = charset.find('*');
        if (star != std::string::npos) charset = charset.substr(0, star);
        char enc = static_cast<char>(std::toupper(static_cast<unsigned char>(value[q1 + 1])));
        std::string text = value.substr(q2 + 1, end - q2 - 1);
        std::string bytes;
        bool ok = true;
        if (enc == 'B') {
          try {
            bytes = b64decode(text);
          } catch (...) {
            ok = false;
          }
        } else if (enc == 'Q') {
          bytes = qp_decode(text, true);
        } else {
          ok = false;
        }
        if (ok) {
          if (!last_word) out += pending_ws;
          pending_ws.clear();
          out += charset_decode(bytes, charset);
          last_word = true;
          i = end + 2;
          continue;
        }
      }
    }
    char c = value[i];
    if (c == ' ' || c == '\t') {
      pending_ws += c;
    } else {
      out += pending_ws;
      pending_ws.clear();
      out += c;
      last_word = false;
    }
    ++i;
  }
  return out + pending_ws;
}

bool is_address_header(const std::string& name) {
  static const std::set<std::string> names = {"to",        "from",      "cc",         "bcc",
                                              "sender",    "reply-to",  "resent-to",  "resent-cc",
                                              "resent-bcc", "resent-from", "resent-sender"};
  return names.count(lower(name)) > 0;
}

// str() of a header under policy.default: encoded words decoded; address headers re-rendered.
std::string display(const Header& h) {
  if (lower(h.name) == "date") {  // policy.default re-formats a UTC date with +0000
    std::string v = strip(h.value);
    for (std::string zone : {" GMT", " UT", " UTC", " Z"})
      if (ends_with(v, zone)) return v.substr(0, v.size() - zone.size()) + " +0000";
    return v;
  }
  if (!is_address_header(h.name)) return decode_words(h.value);
  std::vector<NameAddr> pairs = getaddresses({h.value});
  std::vector<std::string> out;
  for (auto& p : pairs) {
    if (p.second.empty() && p.first.empty()) continue;
    std::string name = decode_words(p.first);
    if (name.empty()) {
      out.push_back(p.second);
    } else {
      if (name.find_first_of("()<>@,:;.\"[]\\") != std::string::npos)
        name = "\"" + replace_all(replace_all(name, "\\", "\\\\"), "\"", "\\\"") + "\"";
      out.push_back(name + " <" + p.second + ">");
    }
  }
  return out.empty() ? decode_words(h.value) : join(out, ", ");
}

// "type/subtype; a=b; c=\"d\"" -> lower-case type and its parameters
std::string parse_params(const std::string& value, std::vector<std::pair<std::string, std::string>>& params) {
  std::vector<std::string> pieces;
  std::string cur;
  bool in_quote = false, esc = false;
  for (char c : value) {
    if (esc) {
      cur += c;
      esc = false;
    } else if (in_quote && c == '\\') {
      cur += c;
      esc = true;
    } else if (c == '"') {
      in_quote = !in_quote;
      cur += c;
    } else if (c == ';' && !in_quote) {
      pieces.push_back(cur);
      cur.clear();
    } else {
      cur += c;
    }
  }
  pieces.push_back(cur);
  for (size_t k = 1; k < pieces.size(); ++k) {
    std::string item = strip(pieces[k]);
    size_t eq = item.find('=');
    if (eq == std::string::npos) continue;
    std::string name = lower(strip(item.substr(0, eq)));
    std::string v = strip(item.substr(eq + 1));
    if (v.size() >= 2 && v.front() == '"' && v.back() == '"') {
      v = v.substr(1, v.size() - 2);
      std::string unesc;
      for (size_t i = 0; i < v.size(); ++i) {
        if (v[i] == '\\' && i + 1 < v.size()) ++i;
        unesc += v[i];
      }
      v = unesc;
    }
    params.emplace_back(name, v);
  }
  return lower(strip(pieces[0]));
}

std::string param(const std::vector<std::pair<std::string, std::string>>& params, const std::string& name) {
  for (auto& p : params)
    if (p.first == name) return p.second;
  std::string star = name + "*";
  for (auto& p : params) {
    if (p.first == star) {  // RFC 2231: charset'lang'value
      size_t a = p.second.find('\''), b = a == std::string::npos ? a : p.second.find('\'', a + 1);
      std::string enc = b == std::string::npos ? p.second : p.second.substr(b + 1);
      std::string charset = a == std::string::npos ? "utf-8" : p.second.substr(0, a);
      std::string raw;
      for (size_t i = 0; i < enc.size(); ++i) {
        if (enc[i] == '%' && i + 2 < enc.size() && std::isxdigit(static_cast<unsigned char>(enc[i + 1])) &&
            std::isxdigit(static_cast<unsigned char>(enc[i + 2]))) {
          raw += static_cast<char>(std::stoi(enc.substr(i + 1, 2), nullptr, 16));
          i += 2;
        } else {
          raw += enc[i];
        }
      }
      return charset_decode(raw, charset);
    }
  }
  return "";
}

struct Mime {
  std::vector<Header> headers;
  std::string body;
  std::string ctype;
  std::vector<std::pair<std::string, std::string>> params;
  std::vector<Mime> parts;
  bool multipart = false;
};

Mime parse_mime(const std::string& raw, int depth, const std::string& default_type = "text/plain") {
  Mime m;
  auto parts = split_message(raw);
  m.headers = parse_headers(parts.first);
  m.body = parts.second;
  const Header* ct = find_header(m.headers, "content-type");
  m.ctype = ct ? parse_params(ct->value, m.params) : default_type;
  if (m.ctype.find('/') == std::string::npos) m.ctype = "text/plain";
  std::string bnd = param(m.params, "boundary");
  if (starts_with(m.ctype, "multipart/") && !bnd.empty() && depth < 20) {
    m.multipart = true;
    std::string delim = "--" + bnd;
    std::vector<std::string> chunks;
    std::string cur;
    bool started = false, closed = false;
    size_t pos = 0;
    while (pos <= m.body.size() && !closed) {
      size_t eol = m.body.find("\r\n", pos);
      std::string line = m.body.substr(pos, eol == std::string::npos ? std::string::npos : eol - pos);
      std::string trimmed = rstrip(line, " \t");
      if (trimmed == delim || trimmed == delim + "--") {
        if (started) {
          if (ends_with(cur, "\r\n")) cur.resize(cur.size() - 2);
          chunks.push_back(cur);
        }
        cur.clear();
        started = true;
        if (trimmed == delim + "--") closed = true;
      } else if (started) {
        cur += line + (eol == std::string::npos ? "" : "\r\n");
      }
      if (eol == std::string::npos) break;
      pos = eol + 2;
    }
    if (started && !closed && !cur.empty()) chunks.push_back(cur);
    std::string child_default = m.ctype == "multipart/digest" ? "message/rfc822" : "text/plain";
    for (auto& c : chunks) m.parts.push_back(parse_mime(c, depth + 1, child_default));
  }
  return m;
}

std::string decoded_payload(const Mime& m) {
  const Header* cte = find_header(m.headers, "content-transfer-encoding");
  std::string enc = cte ? lower(strip(cte->value)) : "";
  if (enc == "base64") {
    std::string clean;
    for (char c : m.body)
      if (c != '\r' && c != '\n') clean += c;
    try {
      return b64decode(clean);
    } catch (...) {
      return m.body;
    }
  }
  if (enc == "quoted-printable") return qp_decode(m.body, false);
  return m.body;
}

void walk(const Mime& m, std::vector<const Mime*>& out) {
  out.push_back(&m);
  for (auto& p : m.parts) walk(p, out);
}

Json headers_list(const std::vector<Header>& headers, const char* name_key, const char* value_key, size_t limit) {
  Json list = Json::array();
  for (size_t i = 0; i < headers.size() && i < limit; ++i) {
    Json item = Json::object();
    item[name_key] = headers[i].name;
    item[value_key] = display(headers[i]);
    list.push(item);
  }
  return list;
}

}  // namespace

RawRecipients raw_recipients(const std::string& raw) {
  std::vector<Header> headers = parse_headers(split_message(crlf(raw)).first);
  RawRecipients r;
  std::vector<std::string> to, cc, bcc;
  bool has_from = false;
  for (auto& h : headers) {
    std::string n = lower(h.name);
    if (n == "from" && !has_from) {
      r.from = h.value;
      has_from = true;
    }
    if (n == "to") to.push_back(h.value);
    if (n == "cc") cc.push_back(h.value);
    if (n == "bcc") bcc.push_back(h.value);
  }
  auto addrs = [](const std::vector<std::string>& values) {
    std::vector<std::string> out;
    if (values.empty()) return out;
    for (auto& p : getaddresses(values))
      if (!p.second.empty()) out.push_back(p.second);
    return out;
  };
  r.to = addrs(to);
  r.cc = addrs(cc);
  r.bcc = addrs(bcc);
  return r;
}

Json mime_summary(const std::string& raw) {
  std::vector<Header> headers = parse_headers(split_message(crlf(raw)).first);
  Json common = Json::object();
  const std::pair<const char*, const char*> lists[] = {
      {"from", "From"}, {"replyTo", "Reply-To"}, {"to", "To"}, {"cc", "Cc"}, {"bcc", "Bcc"}};
  for (auto& kv : lists) {
    Json values = Json::array();
    bool any = false;
    for (auto& h : headers) {
      if (lower(h.name) != lower(kv.second)) continue;
      any = true;
      for (auto& p : getaddresses({display(h)}))
        if (!p.second.empty()) values.push(strip(formataddr(p)));
    }
    if (any) common[kv.first] = values;
  }
  const std::pair<const char*, const char*> singles[] = {
      {"date", "Date"}, {"messageId", "Message-ID"}, {"subject", "Subject"}, {"returnPath", "Return-Path"}};
  for (auto& kv : singles) {
    const Header* h = find_header(headers, kv.second);
    if (h) common[kv.first] = display(*h);
  }
  Json out = Json::object();
  out["commonHeaders"] = common;
  out["headers"] = headers_list(headers, "name", "value", 50);
  out["headersTruncated"] = headers.size() > 50;
  return out;
}

Json mime_read(const std::string& raw) {
  const size_t max_text = 2 * 1024 * 1024;
  Mime root = parse_mime(crlf(raw), 0);
  std::vector<const Mime*> all;
  walk(root, all);
  std::string text, html;
  bool have_text = false, have_html = false;
  Json attachments = Json::array();
  for (const Mime* part : all) {
    if (part->multipart) continue;
    const Header* cd = find_header(part->headers, "content-disposition");
    std::vector<std::pair<std::string, std::string>> dparams;
    std::string disposition = cd ? parse_params(cd->value, dparams) : "";
    auto decode_text = [&]() {
      std::string charset = param(part->params, "charset");
      std::string out = charset_decode(decoded_payload(*part), charset.empty() ? "us-ascii" : charset);
      if (out.size() > max_text) {
        size_t cut = max_text;
        while (cut > 0 && (static_cast<unsigned char>(out[cut]) & 0xC0) == 0x80) --cut;
        out.resize(cut);
      }
      return out;
    };
    if (!cd && part->ctype == "text/plain" && !have_text) {
      text = decode_text();
      have_text = !text.empty();
    } else if (!cd && part->ctype == "text/html" && !have_html) {
      html = decode_text();
      have_html = !html.empty();
    } else {
      std::string filename = param(dparams, "filename");
      if (filename.empty()) filename = param(part->params, "name");
      const Header* cid = find_header(part->headers, "content-id");
      Json att = Json::object();
      att["FileName"] = decode_words(filename);
      att["ContentType"] = part->ctype;
      att["Disposition"] = upper(disposition.empty() ? "attachment" : disposition);
      att["Size"] = static_cast<long long>(decoded_payload(*part).size());
      att["ContentId"] = cid ? strip(decode_words(cid->value), "<>") : "";
      attachments.push(att);
    }
  }
  Json out = Json::object();
  out["Headers"] = headers_list(root.headers, "Name", "Value", root.headers.size());
  out["Text"] = text;
  out["Html"] = html;
  out["Attachments"] = attachments;
  return out;
}

}  // namespace ses
