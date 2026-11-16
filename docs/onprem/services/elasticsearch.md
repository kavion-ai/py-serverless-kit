# Elasticsearch (search and analytics)

Search terms: Elasticsearch, full-text search, Kibana, logs, analytics, 9200, elastic user

Elasticsearch is a search and analytics engine with a REST API. pskit runs the official image as a single node with
security on: the user is `elastic` and the password is the service password. Kibana is its web UI.

## Elasticsearch at a glance

| | |
|---|---|
| `--service` | `elasticsearch` |
| Studio card | **Identity & search** > **Elasticsearch (search and analytics)** |
| Docker image | `docker.elastic.co/elasticsearch/elasticsearch:8.15.3` |
| Port | `9200` (HTTP REST API) |
| Use as | `database` (resource type `database`) |
| Login | user `elastic`, password = the service password (generated when empty) |
| Data | kept in `/usr/share/elasticsearch/data` (a Docker volume, or `<data_dir>/<container>` on a server) |
| Web UI | Kibana (`docker.elastic.co/kibana/kibana:8.15.3`, port `5601`): *Also start its web UI* or `--gui` |
| Memory | about 2 GB (1 GB Java heap); Kibana about 1 GB more |

## Create it

```bash
pskit resources onprem create search --service elasticsearch --gui --save
```

In studio: **Resources** > **+ On-prem service** > **Identity & search** > **Elasticsearch**, tick *Also start its
web UI* for Kibana, **Create**. The first start takes one to two minutes; Kibana another minute.

## Use it

The env file gets `PSKIT_SEARCH_URL`, `PSKIT_SEARCH_USER` (`elastic`) and `PSKIT_SEARCH_PASSWORD`.

```python
import os

from elasticsearch import Elasticsearch  # pip install "elasticsearch>=8,<9"

es = Elasticsearch(os.environ["PSKIT_SEARCH_URL"],
                   basic_auth=(os.environ["PSKIT_SEARCH_USER"], os.environ["PSKIT_SEARCH_PASSWORD"]))
es.index(index="notes", document={"title": "hello", "body": "first note"})
print(es.search(index="notes", query={"match": {"body": "note"}})["hits"]["hits"])
```

```js
const { Client } = require("@elastic/elasticsearch"); // npm install @elastic/elasticsearch@8
const es = new Client({ node: process.env.PSKIT_SEARCH_URL,
  auth: { username: process.env.PSKIT_SEARCH_USER, password: process.env.PSKIT_SEARCH_PASSWORD } });
```

Kibana: open it from the service row (*Web UI*) and sign in as `elastic` with the service password.

## Notes

- On a Linux server, Elasticsearch may need `sudo sysctl -w vm.max_map_count=262144` (and the same in
  `/etc/sysctl.conf`) if it stops with a `max_map_count` message in its logs.
- Keep the port on a private network: plain HTTP carries the password in each request. Put it behind TLS (a reverse
  proxy) for clients across networks you do not trust.
