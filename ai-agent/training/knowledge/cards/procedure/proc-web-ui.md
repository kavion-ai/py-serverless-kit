## In studio
1. Use the service row Console or the web UI actions.

## In the terminal
1. Run:

```
pskit resources onprem gui orders-db
```

2. Run:

```
pskit resources onprem console orders-db
```

## In code

gui opens the service web UI. console runs the service client such as psql or redis-cli. The catalog says which UI each image has.

## Web UIs Services with a built-in UI (RabbitMQ, LavinMQ, MinIO, RustFS, ElasticMQ, NATS

monitoring, Mailpit, pskit's S3 and Secrets Manager servers) show its URL and login in *How to use* and *Details*. For the others pskit starts a **companion** UI next to the service, on a private Docker network with it, listening on the same interface as the service: | Service | Companion | Default port | Login |

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
