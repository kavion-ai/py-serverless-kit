# Studio: Overview & provider

How to open: Left navigation label Overview & provider. The brand in the top bar links to the same view.

What it is for: The page subtitle says "Service-wide settings. Every function inherits these unless it overrides them." docs/studio.md says this page picks the provider from cards that show what each supports (HTTP, schedule, queue, storage, topic, native workflows). Switching first lists the triggers that would stop working.

What you see: Section Service (Service name, and the button Use the values shown here). Section Provider. Section Defaults for every function: Region, Stage (help "dev, staging, prod… (lowercase, ≤ 16)"), Runtime, Memory (MB) with help "64–32768", Timeout (s), Architecture, Log retention (days). Section Environment variables, hint "available to every function". Section Tags, with Add tag. A section titled with the provider display name plus "options", hint provider.options. Section Packaging, hint package. Section On-premises deployment, hint provider.options.deploy: Saved server (an option "None: use the method below"), and Deploy method. The deploy-method help says local is "This machine.", ssh is "A server reached over SSH (scp + process or systemd).", and docker is "A Docker container, locally or on a server over SSH." Section Built-in services, hint provider.options.services. Section Host tuning, hint "logs, executions, concurrency".

What you can do: Use the values shown here calls `absorbShadows` on the draft. The nearby copy says current provider options move under `providers.<name>` so switching back restores them. Test SSH connection is shown in the on-premises deployment section. Its title is `ssh <user>@<host> echo pskit-ok` when a host is set, and "Set the SSH host first" when it is not. The code default for the user in that title is the string pskit. A missing ssh, scp or Docker note links to Setup & credentials.

Tips and limits: The Stage field on this page is separate from the top-bar stage input. docs/studio.md says the top bar is what validate and deploy use. Memory help text on the form is 64–32768. Timeout help includes the provider's `max_timeout` when a provider is selected.

Sources: `dashboard-ui/src/studio/views/Overview.tsx`, `dashboard-ui/src/studio/App.tsx`, `docs/studio.md#what-you-can-do`
