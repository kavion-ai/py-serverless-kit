## In studio
1. Open this path:
Code > Full VS Code

## In the terminal
1. Run:

```
pskit studio --open
```

## In code

Full VS Code needs Docker. Pull and start runs code-server. The default image is codercom/code-server:4.96.4. The container listens on 127.0.0.1. Stop removes the container and leaves project files.

## Full VS Code (code-server in Docker)

**Code → Full VS Code** runs code-server on your project and embeds it: 1. Studio checks for the Docker CLI and a running daemon. If either is missing, it shows how to install Docker. 2. **Pull & start** pulls the image if it isn't present (the log streams in the panel), then starts `pskit-studio-<id>` with your project mounted at `/home/coder/project`, published on `127.0.0.1` Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
