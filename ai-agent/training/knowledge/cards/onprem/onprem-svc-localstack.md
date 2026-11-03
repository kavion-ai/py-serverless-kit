# On-premises service: LocalStack (SQS, S3, Secrets Manager)

The catalog id is `localstack`. Kind is service. Group is AWS emulators. Image is localstack/localstack:3.8. Published port is 4566. Extra ports are none. Roles are queue, storage, secrets. Backup is yes. Persistent data is yes. Auth is no. Default user is pskit. Companion UI is none. Web UI names are Status (JSON). GUI login choices are none.

Catalog notes: Amazon SQS, S3, Secrets Manager and SSM Parameter Store on one port: the sqs / s3 drivers, get_secret(), boto3 and the AWS CLI work with endpoint_url. Credentials are not checked (test / test). For development and tests.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-localstack --service localstack
pskit resources onprem status sample-localstack
```

pskit resources onprem usage sample-localstack prints how to connect. pskit resources onprem logs sample-localstack shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
