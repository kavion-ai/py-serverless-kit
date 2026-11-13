#include "templates.hpp"

#include <cmath>
#include <cstdio>
#include <memory>
#include <vector>

#include "errors.hpp"
#include "util.hpp"

namespace ses {

namespace {

ApiError template_error(const std::string& message) {
  return ApiError("BadRequestException", message, 400, "InvalidTemplate");
}

struct Node {
  enum Kind { TEXT, VAR, BLOCK } kind = TEXT;
  std::string text;               // TEXT
  std::vector<std::string> path;  // VAR / BLOCK
  bool escape = false;            // VAR
  std::string block;              // BLOCK: if, unless, each, with
  std::vector<Node> body, else_body;
};

const char* const WS = " \t\n\r\f\v\x1c\x1d\x1e\x1f";

bool ident_start(char c) { return std::isalpha(static_cast<unsigned char>(c)) || c == '_' || c == '$'; }
bool ident_char(char c) {
  return std::isalnum(static_cast<unsigned char>(c)) || c == '_' || c == '$' || c == '-' ||
         static_cast<unsigned char>(c) >= 0x80;
}
bool is_ident(const std::string& s) {
  if (s.empty() || !ident_start(s[0])) return false;
  for (size_t i = 1; i < s.size(); ++i)
    if (!ident_char(s[i])) return false;
  return true;
}
bool is_digits(const std::string& s) {
  if (s.empty()) return false;
  for (char c : s)
    if (!std::isdigit(static_cast<unsigned char>(c))) return false;
  return true;
}

std::vector<std::string> make_path(const std::string& expr) {
  if (expr == ".") return {"this"};
  std::vector<std::string> parts = split(expr, '.');
  bool ok = !expr.empty();
  if (ok) {
    const std::string& head = parts[0];
    ok = head == "@index" || head == "@first" || head == "@last" || head == "@key" || is_ident(head);
    for (size_t i = 1; ok && i < parts.size(); ++i) ok = is_ident(parts[i]) || is_digits(parts[i]);
  }
  if (!ok) throw template_error("Invalid expression {{" + expr + "}}.");
  return parts;
}

struct Frame {
  std::string kind;
  std::vector<std::string> path;
  std::vector<Node> body;
  std::vector<Node> else_body;
  bool in_else = false;
};

std::vector<Node> parse(const std::string& text) {
  std::vector<Node> root;
  std::vector<Frame> stack;
  auto current = [&]() -> std::vector<Node>& {
    if (stack.empty()) return root;
    return stack.back().in_else ? stack.back().else_body : stack.back().body;
  };
  size_t pos = 0, scan = 0;
  while (true) {
    size_t p = text.find("{{", scan);
    if (p == std::string::npos) break;
    // the regex alternatives, in order: {{{ raw }}}, {{!-- comment --}}, {{ inner }}
    size_t end = std::string::npos;
    int alt = 0;
    std::string group;
    if (p + 2 < text.size() && text[p + 2] == '{') {
      size_t close = text.find("}}}", p + 3);
      if (close != std::string::npos) {
        alt = 1;
        group = strip(text.substr(p + 3, close - p - 3), WS);
        end = close + 3;
      }
    }
    if (!alt && text.compare(p, 5, "{{!--") == 0) {
      size_t close = text.find("--}}", p + 5);
      if (close != std::string::npos) {
        alt = 2;
        end = close + 4;
      }
    }
    if (!alt) {
      size_t close = text.find("}}", p + 2);
      if (close != std::string::npos) {
        alt = 3;
        group = text.substr(p + 2, close - p - 2);
        end = close + 2;
      }
    }
    if (!alt) {
      scan = p + 1;
      continue;
    }
    if (p > pos) {
      Node t;
      t.text = text.substr(pos, p - pos);
      current().push_back(std::move(t));
    }
    pos = scan = end;
    if (alt == 1) {
      Node v;
      v.kind = Node::VAR;
      v.path = make_path(group);
      v.escape = false;
      current().push_back(std::move(v));
      continue;
    }
    if (alt == 2) continue;
    std::string inner = strip(group, WS);
    if (starts_with(inner, "!")) continue;
    if (starts_with(inner, "#")) {
      std::string rest = strip(inner.substr(1), WS);
      size_t sp = rest.find(' ');
      std::string kind = sp == std::string::npos ? rest : rest.substr(0, sp);
      std::string arg = sp == std::string::npos ? "" : rest.substr(sp + 1);
      if (kind != "if" && kind != "unless" && kind != "each" && kind != "with")
        throw template_error("Unsupported block helper {{#" + kind + "}}.");
      Frame f;
      f.kind = kind;
      f.path = make_path(strip(arg, WS));
      stack.push_back(std::move(f));
    } else if (inner == "else") {
      if (stack.empty() || stack.back().in_else) throw template_error("{{else}} outside a block.");
      stack.back().in_else = true;
    } else if (starts_with(inner, "/")) {
      std::string kind = strip(inner.substr(1), WS);
      if (stack.empty() || stack.back().kind != kind)
        throw template_error("{{/" + kind + "}} does not close an open block.");
      Frame f = std::move(stack.back());
      stack.pop_back();
      Node b;
      b.kind = Node::BLOCK;
      b.block = f.kind;
      b.path = std::move(f.path);
      b.body = std::move(f.body);
      b.else_body = std::move(f.else_body);
      current().push_back(std::move(b));
    } else {
      Node v;
      v.kind = Node::VAR;
      v.path = make_path(inner);
      v.escape = true;
      current().push_back(std::move(v));
    }
  }
  if (!stack.empty()) throw template_error("{{#" + stack.back().kind + "}} is not closed.");
  if (pos < text.size()) {
    Node t;
    t.text = text.substr(pos);
    current().push_back(std::move(t));
  }
  return root;
}

struct Scope {
  const Json* self = nullptr;
  bool meta = false;
  Json index, first, last, key;
};

const Json kNone;

const Json* lookup(const std::vector<Scope>& scopes, const std::vector<std::string>& path) {
  const std::string& head = path[0];
  const Json* value = &kNone;
  const Scope& top = scopes.back();
  if (head == "this") {
    value = top.self;
  } else if (head[0] == '@') {
    if (top.meta) {
      if (head == "@index") value = &top.index;
      else if (head == "@first") value = &top.first;
      else if (head == "@last") value = &top.last;
      else if (head == "@key") value = &top.key;
    }
  } else {
    for (auto it = scopes.rbegin(); it != scopes.rend(); ++it) {
      const Json* ctx = it->self;
      if (ctx && ctx->is_obj()) {
        if (const Json* found = ctx->find(head)) {
          value = found;
          break;
        }
      }
    }
  }
  for (size_t i = 1; i < path.size(); ++i) {
    const std::string& part = path[i];
    if (value->is_obj()) {
      const Json* found = value->find(part);
      value = found ? found : &kNone;
    } else if (value->is_arr() && is_digits(part) && part.size() < 10 &&
               static_cast<size_t>(std::stoul(part)) < value->arr().size()) {
      value = &value->arr()[std::stoul(part)];
    } else {
      return &kNone;
    }
  }
  return value;
}

bool tpl_truthy(const Json& v) {
  if (v.is_arr()) return !v.arr().empty();
  if (v.is_null()) return false;
  if (v.is_bool()) return v.b();
  if (v.is_number()) return v.num() != 0 || std::isnan(v.num());
  if (v.is_str()) return !v.s().empty();
  return true;
}

std::string escape_html(const std::string& s) {
  std::string out;
  for (char c : s) {
    switch (c) {
      case '&': out += "&amp;"; break;
      case '<': out += "&lt;"; break;
      case '>': out += "&gt;"; break;
      case '"': out += "&quot;"; break;
      case '\'': out += "&#x27;"; break;
      case '`': out += "&#x60;"; break;
      case '=': out += "&#x3D;"; break;
      default: out += c;
    }
  }
  return out;
}

void render(const std::vector<Node>& nodes, std::vector<Scope>& scopes, bool html, std::string& out) {
  for (const Node& node : nodes) {
    if (node.kind == Node::TEXT) {
      out += node.text;
    } else if (node.kind == Node::VAR) {
      std::string text = to_text(*lookup(scopes, node.path));
      out += (node.escape && html) ? escape_html(text) : text;
    } else {
      const Json* value = lookup(scopes, node.path);
      if (node.block == "if") {
        render(tpl_truthy(*value) ? node.body : node.else_body, scopes, html, out);
      } else if (node.block == "unless") {
        render(tpl_truthy(*value) ? node.else_body : node.body, scopes, html, out);
      } else if (node.block == "with") {
        if (tpl_truthy(*value)) {
          Scope s;
          s.self = value;
          scopes.push_back(s);
          render(node.body, scopes, html, out);
          scopes.pop_back();
        } else {
          render(node.else_body, scopes, html, out);
        }
      } else {  // each
        std::vector<std::pair<Json, const Json*>> items;
        if (value->is_arr()) {
          for (size_t i = 0; i < value->arr().size(); ++i)
            items.emplace_back(Json(static_cast<long long>(i)), &value->arr()[i]);
        } else if (value->is_obj()) {
          for (auto& kv : value->items()) items.emplace_back(Json(kv.first), &kv.second);
        }
        if (items.empty()) render(node.else_body, scopes, html, out);
        for (size_t i = 0; i < items.size(); ++i) {
          Scope s;
          s.self = items[i].second;
          s.meta = true;
          s.index = Json(static_cast<long long>(i));
          s.first = Json(i == 0);
          s.last = Json(i == items.size() - 1);
          s.key = items[i].first;
          scopes.push_back(s);
          render(node.body, scopes, html, out);
          scopes.pop_back();
        }
      }
    }
  }
}

}  // namespace

std::string to_text(const Json& value) {
  switch (value.type()) {
    case Json::NUL: return "";
    case Json::BOOL: return value.b() ? "true" : "false";
    case Json::INT: return py_int_str(value);
    case Json::FLOAT: {
      double d = value.d();
      if (std::isnan(d)) return "NaN";
      if (std::isfinite(d) && d == std::floor(d) && std::fabs(d) < 1e21) {
        char buf[64];
        std::snprintf(buf, sizeof buf, "%.0f", d);
        std::string s = buf;
        return s == "-0" ? "0" : s;
      }
      return py_float_repr(d);
    }
    case Json::STR: return value.s();
    case Json::ARR: {
      std::string out;
      for (size_t i = 0; i < value.arr().size(); ++i) {
        if (i) out += ",";
        out += to_text(value.arr()[i]);
      }
      return out;
    }
    case Json::OBJ: return "[object Object]";
  }
  return "";
}

std::string render_template(const std::string& text, const Json& data, bool html) {
  if (text.empty()) return "";
  std::vector<Node> nodes = parse(text);
  std::vector<Scope> scopes(1);
  scopes[0].self = &data;
  std::string out;
  render(nodes, scopes, html, out);
  return out;
}

Json template_data_of(const Json& text) {
  if (text.is_obj()) return text;
  Json data;
  bool ok = true;
  if (!truthy(text)) {
    data = Json::object();
  } else if (!text.is_str()) {
    ok = false;
  } else {
    try {
      data = parse_json(text.s());
    } catch (const JsonError&) {
      ok = false;
    }
  }
  if (!ok) throw ApiError("BadRequestException", "TemplateData is not valid JSON.", 400, "InvalidRenderingParameter");
  if (!data.is_obj())
    throw ApiError("BadRequestException", "TemplateData must be a JSON object.", 400, "InvalidRenderingParameter");
  return data;
}

void check_templates(const std::string& subject, const std::string& text, const std::string& html) {
  parse(subject);
  parse(text);
  parse(html);
}

}  // namespace ses
