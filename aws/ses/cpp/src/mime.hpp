// Messages: build one from simple content (subject, text, HTML, headers, attachments), and read a raw one (its
// envelope, its headers, and for the console its text, HTML and attachments) - sesserver/mime.py.
#pragma once

#include <string>
#include <vector>

#include "json.hpp"

namespace ses {

struct BuildArgs {
  std::string source;
  std::vector<std::string> to, cc, reply_to;
  std::string subject;
  bool has_text = false, has_html = false;
  std::string text, html;
  Json headers, attachments;
  std::string message_id;
  double date = 0;
};

std::string mime_build(const BuildArgs& args);
std::string mime_simple(const std::string& source, const std::vector<std::string>& to,
                        const std::vector<std::string>& cc, const std::vector<std::string>& reply_to,
                        const Json& message, const std::string& message_id, double date);
std::string prepare_raw(const std::string& raw, const std::string& message_id, double date);

struct RawRecipients {
  std::string from;
  std::vector<std::string> to, cc, bcc;
};
RawRecipients raw_recipients(const std::string& raw);
Json mime_summary(const std::string& raw);  // {commonHeaders, headers, headersTruncated}
Json mime_read(const std::string& raw);     // {Headers, Text, Html, Attachments}

}  // namespace ses
