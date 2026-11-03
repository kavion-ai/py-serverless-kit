# Other Tencent Cloud services (`type: custom`)

`custom` is for any service that isn't a bucket, queue, topic, database or cache: Secrets Manager, a third-party API,
anything else. pskit only passes its connection details to your functions (`external: true` is required).

The recipe is always the same: find the **endpoint** and the **names** in the console, keep the keys in environment
variables, and put the rest in `connection`.

## Secrets Manager (SSM)

**Create:** Console → **Secrets Manager** → **Secret List** → **Create**: name `stripe-key`, the secret value, an
encryption key (the default KMS key is fine) → **OK**.

**Collect:** the secret name, the region, and a CAM sub-user (or `iam.role`) allowed to read it (for example the
`QcloudSSMReadOnlyAccess` preset policy).

Reading secrets at run time keeps them out of Terraform state; only the keys for SSM are passed as environment
variables.

## Test

A resource key follows function-name rules. connection values are scalars. A key ending in _env names a variable, and the handler reads that variable from the environment. database, cache, and custom must set external to true. The Fields table in the resources page lists storage, queue, topic, database, cache, and custom. The schema also allows smtp.

Open the form on its own line:

Resources > + Add resource

Then open the generated guide:

Resources > How to use

```
pskit validate
pskit resources usage orders -p tencent -s dev
```

pskit resources send sends a test message or object for a queue, bucket, or topic. pskit resources send --list shows every resource. pskit invoke and pskit dev inject the same PSKIT_RESOURCE_* variables locally.
