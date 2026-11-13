// Message events: kept in the message record (Events) and, when SES_EVENTS_URL is set, POSTed there as JSON in the
// SES event publishing format (sesserver/events.py). Types: Send, Reject, Delivery, Bounce, Complaint, DeliveryDelay.
#pragma once

#include <string>
#include <vector>

#include "json.hpp"

namespace ses {

// Append an event to the message record (the caller holds the store lock and saves it); queue it for the webhook.
// `detail` is an object whose fields are added to the event, in order.
void add_event(Json& rec, const std::string& kind, const std::vector<std::string>& recipients,
               const Json& detail = Json::object());
Json publish_format(const Json& rec, const Json& event);
// An HTTP(S) POST; the status, or -1 with `error` filled.
int http_post(const std::string& url, const std::string& body, const std::vector<std::string>& headers,
              std::string& error, double timeout = 10);

}  // namespace ses
