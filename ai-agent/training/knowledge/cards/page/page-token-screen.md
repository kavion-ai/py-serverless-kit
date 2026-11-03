# Studio: session token screen

How to open: This screen replaces the studio when the first project request fails with HTTP 401. `App.tsx` checks `error instanceof ApiError && error.status === 401` and renders `TokenScreen`. It is not a left-navigation item. A different error shows an error banner with retry. While meta or project is still loading, the label is "Loading project…". A folder with no pskit.yml shows the New project screen instead.

What it is for: The studio API refuses calls that do not carry the session token. docs/studio.md#security says every API call needs the session token from the printed URL, a new token is generated each time studio starts, and anyone with that URL has full access. The heading on the screen is "This studio session needs its link".

What you see: The paragraph says pskit studio only answers requests that carry the session token from the link it printed when it started. It tells you to open that link again, or restart. The only command on the screen is:

```
pskit studio --open
```

A smaller line says the token lives only in this browser tab and is never written to disk. There is no passphrase field and no token input on this screen.

What you can do: Open the URL that the `pskit studio` process printed, including the token fragment, in this browser. Or stop the process and start it again so it prints a new URL. `--open` asks the CLI to open the browser. The doc's option table says `--host` defaults to 127.0.0.1, `--port` defaults to 8770, and `--open` defaults to off. Binding to something other than loopback prints a warning, because studio can edit files and deploy.

Tips and limits: Refreshing a tab that never received the token stays on this screen. The token is not in pskit.yml and not in .pskit. docs/studio.md#security also says requests with a foreign Host header or a cross-site Origin are refused, and bodies are capped at 2 MiB. Deploy commands from studio run as `python -m py_serverless_kit` with explicit arguments, never through a shell. Sharing the printed URL shares the session.

Sources: `dashboard-ui/src/studio/App.tsx`, `docs/studio.md#security`
