// The delivery settings in effect: what the console saved (ses.json, key "delivery") over the environment
// (SES_DELIVERY, SES_RELAY_*, SES_HELO_NAME) - sesserver/settings.py. Read again on every delivery attempt.
#pragma once

#include "json.hpp"

namespace ses {

Json delivery_environment();
Json delivery_effective();  // with Source: "console" or "environment"; takes the store lock
Json delivery_public(const Json& values);  // without RelayPassword, with RelayPasswordSet
Json delivery_check(const Json& params);   // validated console settings; throws ApiError
void delivery_save(const Json& values);    // {} = back to the environment

}  // namespace ses
