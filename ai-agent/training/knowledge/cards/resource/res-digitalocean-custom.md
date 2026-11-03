# Other DigitalOcean services (`type: custom`)

`custom` is for any service that isn't a bucket, queue, topic, database or cache: Managed MongoDB, Managed OpenSearch,
the DigitalOcean API, a third-party API. pskit only passes its connection details to your functions (`external: true` is
required).

The recipe is always the same: find the **endpoint** and a **password or token** in the control panel, keep the secret
in an environment variable, and put the rest in `connection`.

## Managed MongoDB

**Create:** Control panel → **Databases** → **Create Database Cluster** → engine **MongoDB** → region, plan, name →
**Create Database Cluster**.

**Collect:** cluster → **Overview** → **Connection details** → *Public network*: host (an `mongodb+srv` host), user
`doadmin`, password, database `admin`; **Download CA certificate** if your client needs it.

## Managed OpenSearch

**Create:** **Databases** → **Create Database Cluster** → engine **OpenSearch**.

**Collect:** **Connection details** → *Public network*: the URL (`https://...:25060`), user, password.

Use it with `opensearch-py` or plain HTTPS requests with basic auth, reading `resource("search").url`. (Add
`SEARCH_PASSWORD: ${env:SEARCH_PASSWORD}` under `provider.environment`.)

## DigitalOcean API

**Collect:** Control panel → **API** → **Tokens** → **Generate New Token** (scopes as narrow as possible).

```text
service: catalog

provider:
  name: digitalocean
  region: nyc1
  options:
    namespace: fn-00000000-0000-0000-0000-000000000000
  environment:
    MONGO_PASSWORD: ${env:MONGO_PASSWORD}

resources:
  catalog-db:
    type: custom
    external: true
    connection:
      host: acme-mongo-0000.mongo.ondigitalocean.com
      user: doadmin
      database: catalog
      password_env: MONGO_PASSWORD

functions:
  product:
    handler: app.handlers.product
    events:
      - http: GET /products/{id}
```
