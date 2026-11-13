// The delivery worker: takes queued recipients and sends them on, as SES_DELIVERY says (relay, direct to the MX
// hosts, or capture), answers for the mailbox simulator, retries with delays and turns hard bounces into
// suppression list entries (sesserver/delivery.py).
#pragma once

#include <string>

#include "json.hpp"

namespace ses {

void start_delivery_worker();
void wake_delivery();
void deliver(const std::string& message_id);
// Tries delivery settings without sending anything: {Ok, Message, Steps}.
Json test_connection(const Json& conf, const std::string& domain);

}  // namespace ses
