## In studio
1. The token screen shows the command that opens the link.

## In the terminal
1. Run:

```
pskit studio --open
```

## In code

The studio doc shows a docker run that publishes 127.0.0.1:8770, mounts the Docker socket, and sets PSKIT_STUDIO_HOST_ROOT when code-server must start as a sibling container.

## Full VS Code (code-server in Docker)

**Code → Full VS Code** runs code-server on your project and embeds it: 1. Studio checks for the Docker CLI and a running daemon. If either is missing, it shows how to install Docker. 2. **Pull & start** pulls the image if it isn't present (the log streams in the panel), then starts `pskit-studio-<id>` with your project mounted at `/home/coder/project`, published on `127.0.0.1` Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
