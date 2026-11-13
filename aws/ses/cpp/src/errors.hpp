// ApiError: one error, answered in the shape of the API that was called. `code` is the SES v2 name
// (NotFoundException, BadRequestException, ...); the v1 Query API answers with `v1` for the same error.
#pragma once

#include <string>
#include <utility>

namespace ses {

struct ApiError {
  std::string code, message;
  int status = 400;
  std::string v1;

  ApiError(std::string c, std::string m, int s = 400, std::string v = "")
      : code(std::move(c)), message(std::move(m)), status(s), v1(std::move(v)) {
    if (v1.empty()) {
      if (code == "BadRequestException") v1 = "InvalidParameterValue";
      else if (code == "NotFoundException") v1 = "NotFound";
      else if (code == "AlreadyExistsException") v1 = "AlreadyExists";
      else if (code == "TooManyRequestsException") v1 = "Throttling";
      else if (code == "LimitExceededException") v1 = "LimitExceeded";
      else if (code == "SendingPausedException") v1 = "AccountSendingPausedException";
      else v1 = code;
    }
  }
};

inline ApiError bad_request(const std::string& message) { return ApiError("BadRequestException", message); }
inline ApiError not_found(const std::string& message, const std::string& v1 = "") {
  return ApiError("NotFoundException", message, 404, v1);
}
inline ApiError exists(const std::string& message, const std::string& v1 = "") {
  return ApiError("AlreadyExistsException", message, 400, v1);
}
inline ApiError rejected(const std::string& message) { return ApiError("MessageRejected", message); }

}  // namespace ses
