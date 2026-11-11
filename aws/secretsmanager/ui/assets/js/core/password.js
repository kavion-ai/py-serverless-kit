// A random password from the server (GetRandomPassword), without quote and backslash characters so it pastes
// cleanly into JSON, shells and connection strings.

import { call } from "./api.js";

export async function generatePassword(length = 32) {
  const out = await call("GetRandomPassword", { PasswordLength: length, ExcludeCharacters: "\"'\`" });
  return out.RandomPassword;
}
