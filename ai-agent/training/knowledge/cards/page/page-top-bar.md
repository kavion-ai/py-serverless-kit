# Studio: top bar

How to open: The top bar is part of the studio shell in `App.tsx`. It is shown after a project exists. It is not a left-navigation item.

What it is for: Choose the provider and stage that validation and deploy use, save pskit.yml, undo edits, and open settings. docs/studio.md says every edit goes into an in-memory draft and is validated as you type, with the same checks as `pskit validate`, for the provider and stage picked in the top bar. Nothing touches disk until Save.

What you see:
- The brand shows the service name and the subtitle pskit studio. The brand link goes to Overview & provider.
- The label "validate & deploy as" is a provider select (aria-label Target provider). Options are `meta.providers` display names.
- The stage input (aria-label Stage) lowercases the text, keeps only `[a-z0-9-]`, and slices it to 16 characters.
- Undo (title "Undo (Ctrl+Z)"), Redo (title "Redo (Ctrl+Shift+Z)").
- A Problems button (title Problems) shows the error count and the warning count.
- Validate (title Validate now) calls `studio.validateNow`.
- The save button title is "Save pskit.yml (Ctrl+S)". Its label is Saving…, Save, or Saved.
- ⇅ Settings opens a drawer titled "Import / export settings and config".
- Theme toggle, aria-label Toggle theme.
- On a narrow window, Menu (aria-label Menu) opens the navigation.

What you can do: Ctrl or Cmd+S saves, except when the current page is Code. Ctrl or Cmd+Z undoes, and with Shift it redoes. Ctrl or Cmd+Y also redoes. Those undo and redo keys are ignored while focus is in an editable field (`isEditable`). The Problems panel can be closed with Close problems. A conflict modal titled "pskit.yml changed on disk" offers Cancel, Reload (discard my changes), and Overwrite. Overwrite calls save with force. The modal text says a backup of the file on disk is kept in `.pskit/studio/backups/`.

Tips and limits: If the HTTP API returns 401, the shell is replaced by a screen titled "This studio session needs its link". That screen shows:

```
pskit studio --open
```

The screen says the token lives only in this browser tab and is never written to disk. docs/studio.md#security says studio binds to 127.0.0.1 by default and that every API call needs the session token from the printed URL.

Sources: `dashboard-ui/src/studio/App.tsx`, `docs/studio.md#what-you-can-do`, `docs/studio.md#saving-what-changes-in-pskityml`, `docs/studio.md#security`
