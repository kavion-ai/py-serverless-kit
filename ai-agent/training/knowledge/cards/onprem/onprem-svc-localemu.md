# On-premises service: LocalEmu (AWS emulator: SQS, S3, Secrets Manager, ...)

The catalog id is `localemu`. Kind is service. Group is AWS emulators. Image is localemu/localemu:latest. Published port is 4566. Extra ports are none. Roles are queue, storage, secrets. Backup is no. Persistent data is no. Auth is no. Default user is pskit. Companion UI is none. Web UI names are Dashboard. GUI login choices are none.

Catalog notes: An open-source AWS emulator (Apache-2.0 fork of LocalStack, 130+ services) on one port: the sqs / s3 drivers, get_secret(), boto3, the AWS CLI and Terraform work with endpoint_url. Credentials are not checked (test / test). Built-in dashboard with an S3 browser. For development and tests.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-localemu --service localemu
pskit resources onprem status sample-localemu
```

pskit resources onprem usage sample-localemu prints how to connect. pskit resources onprem logs sample-localemu shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
