"use strict";
// S3Error (an S3 error code, message, HTTP status and extra XML fields) and the common errors.

class S3Error extends Error {
  constructor(code, message, status = 400, extra = {}) {
    super(message);
    this.code = code;
    this.status = status;
    this.extra = extra;
    this.headers = {};
  }
}

const noBucket = (name) => new S3Error("NoSuchBucket", "The specified bucket does not exist", 404, { BucketName: name });
const noKey = (key) => new S3Error("NoSuchKey", "The specified key does not exist.", 404, { Key: key });

const invalid = (message, name = "", value = "") =>
  new S3Error("InvalidArgument", message, 400, name ? { ArgumentName: name, ArgumentValue: value } : {});

const malformed = () =>
  new S3Error("MalformedXML", "The XML you provided was not well-formed or did not validate against our published schema");

const denied = (message = "Access Denied") => new S3Error("AccessDenied", message, 403);
const notAllowed = () => new S3Error("MethodNotAllowed", "The specified method is not allowed against this resource.", 405);

const preconditionFailed = (condition) =>
  new S3Error("PreconditionFailed", "At least one of the pre-conditions you specified did not hold", 412,
    condition ? { Condition: condition } : {});

module.exports = { invalid, S3Error, noBucket, noKey, malformed, denied, notAllowed, preconditionFailed };
