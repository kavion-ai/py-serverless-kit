// Sample code that reads a secret from this server (Quick start, the store wizard's review, a secret's Overview).
// Only names and the endpoint go in: never values or keys.

const endpoint = () => window.location.origin;

export const LANGUAGES = [
  { id: "python", label: "Python (boto3)" },
  { id: "javascript", label: "JavaScript (SDK v3)" },
  { id: "cli", label: "AWS CLI" },
  { id: "pskit", label: "pskit function" },
];

export function snippet(lang, name = "prod/db") {
  const id = JSON.stringify(name);
  const url = endpoint();
  switch (lang) {
    case "javascript":
      return [
        'import { SecretsManagerClient, GetSecretValueCommand } from "@aws-sdk/client-secrets-manager";',
        "",
        "const client = new SecretsManagerClient({",
        `  endpoint: "${url}",`,
        '  region: "us-east-1",',
        "  credentials: { accessKeyId: process.env.AWS_ACCESS_KEY_ID, secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY },",
        "});",
        "",
        `const out = await client.send(new GetSecretValueCommand({ SecretId: ${id} }));`,
        "console.log(out.SecretString);",
      ].join("\n");
    case "cli":
      return [
        "export AWS_ACCESS_KEY_ID=<access key id> AWS_SECRET_ACCESS_KEY=<secret access key> AWS_DEFAULT_REGION=us-east-1",
        "",
        `aws --endpoint-url ${url} secretsmanager get-secret-value --secret-id ${shellQuote(name)}`,
        `aws --endpoint-url ${url} secretsmanager list-secrets`,
      ].join("\n");
    case "pskit":
      return [
        "from py_serverless_kit import get_secret",
        "",
        "",
        "def handler(event, ctx):",
        `    value = get_secret(${id})`,
        "    return {\"ok\": bool(value)}",
      ].join("\n");
    default:
      return [
        "import boto3",
        "",
        "client = boto3.client(",
        '    "secretsmanager",',
        `    endpoint_url="${url}",`,
        '    region_name="us-east-1",',
        '    aws_access_key_id="<access key id>",',
        '    aws_secret_access_key="<secret access key>",',
        ")",
        `print(client.get_secret_value(SecretId=${id})["SecretString"])`,
      ].join("\n");
  }
}

function shellQuote(text) {
  return /^[A-Za-z0-9/_+=.@-]+$/.test(text) ? text : `'${String(text).replace(/'/g, "'\\''")}'`;
}
