// Ready bucket policies for the policy editor's "Policy examples" list. build({bucket, arn, account}) returns the
// policy object with the bucket ARN filled in.

const V = "2012-10-17";

function isoIn(days) {
  const d = new Date(Date.now() + days * 86400000);
  d.setUTCMinutes(0, 0, 0);
  return d.toISOString().replace(/\.\d{3}Z$/, "Z");
}

export const POLICY_EXAMPLES = [
  {
    id: "public-read",
    title: "Public read for all objects",
    description: "Anyone can download every object without keys (for example a static website). Turn off \"Block public access\" for bucket policies first.",
    build: ({ arn }) => ({
      Version: V,
      Statement: [{ Sid: "PublicReadGetObject", Effect: "Allow", Principal: "*", Action: "s3:GetObject", Resource: `${arn}/*` }],
    }),
  },
  {
    id: "public-read-folder",
    title: "Public read for one folder",
    description: "Anyone can download the objects under public/; everything else stays private. Change the folder name as needed.",
    build: ({ arn }) => ({
      Version: V,
      Statement: [{ Sid: "PublicReadFolder", Effect: "Allow", Principal: "*", Action: "s3:GetObject", Resource: `${arn}/public/*` }],
    }),
  },
  {
    id: "public-list",
    title: "Public read and list",
    description: "Anyone can list the bucket and download its objects.",
    build: ({ arn }) => ({
      Version: V,
      Statement: [
        { Sid: "PublicList", Effect: "Allow", Principal: "*", Action: "s3:ListBucket", Resource: arn },
        { Sid: "PublicRead", Effect: "Allow", Principal: "*", Action: "s3:GetObject", Resource: `${arn}/*` },
      ],
    }),
  },
  {
    id: "deny-insecure-transport",
    title: "Deny requests that do not use HTTPS",
    description: "Refuses every request made over plain HTTP (aws:SecureTransport is false). Only works when the server is behind an HTTPS proxy that sets X-Forwarded-Proto.",
    build: ({ arn }) => ({
      Version: V,
      Statement: [
        {
          Sid: "DenyInsecureTransport",
          Effect: "Deny",
          Principal: "*",
          Action: "s3:*",
          Resource: [arn, `${arn}/*`],
          Condition: { Bool: { "aws:SecureTransport": "false" } },
        },
      ],
    }),
  },
  {
    id: "ip-range",
    title: "Allow access only from an IP range",
    description: "Denies every request that does not come from the listed networks (aws:SourceIp). Replace the example ranges with yours. The console itself is not affected.",
    build: ({ arn }) => ({
      Version: V,
      Statement: [
        {
          Sid: "DenyOutsideIpRange",
          Effect: "Deny",
          Principal: "*",
          Action: "s3:*",
          Resource: [arn, `${arn}/*`],
          Condition: { NotIpAddress: { "aws:SourceIp": ["192.0.2.0/24", "203.0.113.0/24"] } },
        },
      ],
    }),
  },
  {
    id: "deny-delete",
    title: "Deny object deletion for everyone",
    description: "Nobody can delete objects or object versions with the S3 API, whatever their keys allow.",
    build: ({ arn }) => ({
      Version: V,
      Statement: [
        {
          Sid: "DenyDelete",
          Effect: "Deny",
          Principal: "*",
          Action: ["s3:DeleteObject", "s3:DeleteObjectVersion"],
          Resource: `${arn}/*`,
        },
      ],
    }),
  },
  {
    id: "read-only-key",
    title: "Read-only access for one access key",
    description: "The access key can only list and download; every other action is denied. Replace READONLY_ACCESS_KEY_ID with the access key ID.",
    build: ({ arn, account }) => ({
      Version: V,
      Statement: [
        {
          Sid: "ReadOnlyForOneKey",
          Effect: "Deny",
          Principal: { AWS: `arn:aws:iam::${account}:user/READONLY_ACCESS_KEY_ID` },
          NotAction: ["s3:GetObject", "s3:GetObjectVersion", "s3:GetObjectTagging", "s3:ListBucket", "s3:ListBucketVersions", "s3:GetBucketLocation"],
          Resource: [arn, `${arn}/*`],
        },
      ],
    }),
  },
  {
    id: "deny-public-acl",
    title: "Deny uploads that make objects public",
    description: "Refuses uploads and ACL changes that ask for a public-read or public-read-write ACL (s3:x-amz-acl).",
    build: ({ arn }) => ({
      Version: V,
      Statement: [
        {
          Sid: "DenyPublicAcl",
          Effect: "Deny",
          Principal: "*",
          Action: ["s3:PutObject", "s3:PutObjectAcl"],
          Resource: `${arn}/*`,
          Condition: { StringEquals: { "s3:x-amz-acl": ["public-read", "public-read-write"] } },
        },
      ],
    }),
  },
  {
    id: "referer",
    title: "Restrict downloads to your website (Referer)",
    description: "Anyone can download objects when the request comes from a page on your site (aws:Referer). Referer headers are easy to fake: do not use this to protect private data.",
    build: ({ arn }) => ({
      Version: V,
      Statement: [
        {
          Sid: "AllowFromMySite",
          Effect: "Allow",
          Principal: "*",
          Action: "s3:GetObject",
          Resource: `${arn}/*`,
          Condition: { StringLike: { "aws:Referer": ["https://www.example.com/*", "https://example.com/*"] } },
        },
      ],
    }),
  },
  {
    id: "time-limited",
    title: "Time-limited public access",
    description: "Anyone can download objects between two dates (aws:CurrentTime). The example opens now and closes in 7 days.",
    build: ({ arn }) => ({
      Version: V,
      Statement: [
        {
          Sid: "AllowDuringWindow",
          Effect: "Allow",
          Principal: "*",
          Action: "s3:GetObject",
          Resource: `${arn}/*`,
          Condition: { DateGreaterThan: { "aws:CurrentTime": isoIn(0) }, DateLessThan: { "aws:CurrentTime": isoIn(7) } },
        },
      ],
    }),
  },
  {
    id: "deny-unencrypted",
    title: "Deny unencrypted uploads",
    description: "Refuses uploads that do not ask for server-side encryption (x-amz-server-side-encryption AES256 or aws:kms).",
    build: ({ arn }) => ({
      Version: V,
      Statement: [
        {
          Sid: "DenyUnencryptedUploads",
          Effect: "Deny",
          Principal: "*",
          Action: "s3:PutObject",
          Resource: `${arn}/*`,
          Condition: { StringNotEquals: { "s3:x-amz-server-side-encryption": ["AES256", "aws:kms"] } },
        },
      ],
    }),
  },
];

/** Basic structure checks for the editor's live validation ("" when it looks right). */
export function checkPolicy(policy) {
  if (!policy || typeof policy !== "object" || Array.isArray(policy)) return "A policy must be a JSON object.";
  if (policy.Version && !["2012-10-17", "2008-10-17"].includes(policy.Version)) return 'Version must be "2012-10-17".';
  const st = policy.Statement;
  const list = Array.isArray(st) ? st : st ? [st] : [];
  if (!list.length) return "The policy needs a Statement.";
  for (const [i, s] of list.entries()) {
    const n = `Statement ${i + 1}`;
    if (!s || typeof s !== "object") return `${n} must be an object.`;
    if (s.Effect !== "Allow" && s.Effect !== "Deny") return `${n}: Effect must be "Allow" or "Deny".`;
    if (!s.Principal && !s.NotPrincipal) return `${n}: Principal is required.`;
    if (!s.Action && !s.NotAction) return `${n}: Action is required.`;
    if (!s.Resource && !s.NotResource) return `${n}: Resource is required.`;
  }
  return "";
}
