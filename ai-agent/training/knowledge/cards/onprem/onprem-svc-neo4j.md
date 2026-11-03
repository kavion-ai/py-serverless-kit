# On-premises service: Neo4j (graph database)

The catalog id is `neo4j`. Kind is service. Group is Databases. Image is neo4j:5. Published port is 7687. Extra ports are 7474. Roles are database. Backup is no. Persistent data is yes. Auth is yes. Default user is neo4j. Companion UI is none. Web UI names are Neo4j Browser. GUI login choices are none.

Catalog notes: Graph database queried with Cypher over Bolt (the port); Neo4j Browser on 7474. The user is always neo4j.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-neo4j --service neo4j
pskit resources onprem status sample-neo4j
```

pskit resources onprem usage sample-neo4j prints how to connect. pskit resources onprem logs sample-neo4j shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
