# Studio: Resources

How to open: Left navigation label Resources.

What it is for: The page subtitle says "Buckets, queues, topics, databases and any other service your functions use, once for every cloud." docs/studio.md says the page covers managed or external buckets, queues, topics, databases, caches and custom services, connection values with secrets written as `${env:VAR}`, which functions get the binding, and Browse account.

What you see: Buttons Guides, + SMTP server, + On-prem service, and + Add resource. + SMTP server and + On-prem service are disabled when the provider is not onprem. The SMTP button title says it is an SMTP server (Node.js) that receives mail for your domain and runs functions with it. The on-prem service title says "Start Redis, Kafka, PostgreSQL, MinIO, OpenBao, ... with Docker and add it here". A row has How to use, and DNS guide for an smtp resource that matches an on-prem service. The How to use drawer title is "How to use <key>".

What you can do: + Add resource opens the resource form. Guides opens the in-studio resource guides. docs/studio.md says deleting a managed resource from the Resources table only removes it from pskit.yml, and the next deploy then deletes it in the cloud. The same chapter says Resources, then In the cloud, lists buckets, queues and topics pskit created for the top-bar provider and stage, and that deleting them there runs `pskit resources delete` behind a typed confirmation. How to use opens the end-to-end guide: library, pskit.yml, handler, local tests and deployed tests. See docs/resource-usage.md from that chapter.

Tips and limits: SMTP and one-click services are on-prem controls. The buttons stay on the page and are disabled for other providers. Connection secrets in the form are written as `${env:VAR}` and are not resolved when saved (docs/studio.md#saving-what-changes-in-pskityml). Services that exist on a host but are not in pskit.yml are listed with an Add control, as that chapter describes.

Sources: `dashboard-ui/src/studio/views/Resources.tsx`, `docs/studio.md#what-you-can-do`, `docs/studio.md#project-environment-trigger-resources-and-remove`
