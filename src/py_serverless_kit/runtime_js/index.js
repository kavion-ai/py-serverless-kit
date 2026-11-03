"use strict";
/**
 * pskit runtime for Node.js (package name `pskit`). Write a handler once and
 * deploy it to any cloud pskit supports:
 *
 *   const { Response } = require("pskit");
 *   exports.hello = async (event, ctx) => ({ message: `Hello, ${event.http.query.name || "world"}!` });
 *
 * Mirrors the Python runtime (`py_serverless_kit.runtime`) with camelCase names.
 */

const errors = require("./errors");
const { Event, EventType, Headers, HttpRequest, Record, eventFromWire, parseTime } = require("./event");
const { Context } = require("./context");
const { Response, toResponse } = require("./response");
const { BatchResult, BatchFailure } = require("./batch");
const { getLogger, Logger } = require("./log");
const { Resource, resources, resource } = require("./resources");
const { invoke, InvokeError } = require("./invoke");
const { submitQueue, submitTopic, putObject, deleteObject } = require("./onprem");
const { PskitClient, PskitClientError } = require("./client");
const { getSecret, getSecrets, putSecret, SecretError, SecretNotFound } = require("./secrets");
const { registerModules } = require("./dispatch");
const { registerManifest } = require("./manifest");

module.exports = {
  Event,
  EventType,
  Headers,
  HttpRequest,
  Record,
  Context,
  Response,
  BatchResult,
  BatchFailure,
  Logger,
  Resource,
  invoke,
  InvokeError,
  resources,
  resource,
  submitQueue,
  submitTopic,
  putObject,
  deleteObject,
  PskitClient,
  PskitClientError,
  getSecret,
  getSecrets,
  putSecret,
  SecretError,
  SecretNotFound,
  getLogger,
  toResponse,
  eventFromWire,
  parseTime,
  registerModules,
  registerManifest,
  PskitError: errors.PskitError,
  HandlerNotFound: errors.HandlerNotFound,
  HttpError: errors.HttpError,
  BadRequest: errors.BadRequest,
  Unauthorized: errors.Unauthorized,
  Forbidden: errors.Forbidden,
  NotFound: errors.NotFound,
  MethodNotAllowed: errors.MethodNotAllowed,
  Conflict: errors.Conflict,
  UnprocessableEntity: errors.UnprocessableEntity,
  TooManyRequests: errors.TooManyRequests,
  version: require("./package.json").version,
};
