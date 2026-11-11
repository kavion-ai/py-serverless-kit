"use strict";
// ApiError (an AWS error code, message and HTTP status) and the common errors.

class ApiError extends Error {
  constructor(code, message, status = 400) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

const notFound = () => new ApiError("ResourceNotFoundException", "Secrets Manager can't find the specified secret.");
const invalid = (message) => new ApiError("InvalidParameterException", message);
const badRequest = (message) => new ApiError("InvalidRequestException", message);

module.exports = { ApiError, notFound, invalid, badRequest };
