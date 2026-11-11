// Application state shared between views. Views keep their own page data; only cross-page handoffs live here.

export const state = {
  session: {
    authenticated: false,
    auth: true,
    user: "",
    csrf: "",
    passwordLogin: false,
    region: "us-east-1",
    version: "",
  },
  /** The bucket list (ListBuckets entries), cached for the side navigation. */
  buckets: null,
  /** Files dropped on the Objects tab, picked up by the Upload page: {bucket, prefix, files}. */
  pendingUpload: null,
  /** Objects chosen for the Delete objects page: {bucket, prefix, items: [{key, versionId?, folder?}], versions}. */
  pendingDelete: null,
  /** Keys chosen for a bulk edit (storage class): {bucket, prefix, keys}. */
  pendingKeys: null,
};

const NAV_KEY = "s3console.navCollapsed";

export function navCollapsed() {
  try {
    return window.localStorage.getItem(NAV_KEY) === "1";
  } catch {
    return false;
  }
}

export function setNavCollapsed(value) {
  try {
    window.localStorage.setItem(NAV_KEY, value ? "1" : "0");
  } catch {
    /* storage can be unavailable (private windows); the nav just forgets */
  }
}
