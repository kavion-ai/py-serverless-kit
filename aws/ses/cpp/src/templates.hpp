// The template language: the part of Handlebars that SES templates use (sesserver/templates.py). Both servers must
// render byte-identical text: the same escaping, scope lookup and JavaScript-style number formatting.
#pragma once

#include <string>

#include "json.hpp"

namespace ses {

std::string render_template(const std::string& text, const Json& data, bool html = false);
Json template_data_of(const Json& text);  // the TemplateData object (a JSON object in a string); throws ApiError
void check_templates(const std::string& subject, const std::string& text, const std::string& html);
std::string to_text(const Json& value);

}  // namespace ses
