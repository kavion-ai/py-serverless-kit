# YAML page in studio

Search terms: yaml, pskit.yml, raw yaml, edit yaml, diff, preview, generated config, apply to draft, comments lost, backup

The **YAML** page (title **pskit.yml**) shows what **Save** writes. Sidebar: **YAML** (≡). Comments in the original
file are not preserved; a backup is kept in `.pskit/studio/backups/` on every save. The keys themselves are described
in [Configuration](../configuration.md).

## Preview and diff pskit.yml in studio

The studio YAML page has three modes in the switch at the top right:

| Mode | What it shows |
|---|---|
| **Preview** | The `pskit.yml` the draft produces (read-only, highlighted) |
| **Diff vs disk** | The changes between the file on disk and the draft ("No changes." when they match) |
| **Edit raw YAML** | An editor to change the YAML directly |

Use **Diff vs disk** before **Save** to see exactly what will change.

## Edit raw YAML and apply it to the draft

The **Edit raw YAML** mode of the studio YAML page lets you type YAML and turn it back into forms.

1. Switch to **Edit raw YAML**. The editor starts from the generated YAML.
2. Edit the text. A hint says "Edit the YAML directly, then apply it to the draft. Forms update to match."
3. Click **Apply to draft** (or press Ctrl+S in the editor). Studio parses the text:
   - when it parses, the draft is replaced ("Applied the YAML to the draft (not saved yet)") and the page returns to
     **Preview**;
   - when it does not, the problems are listed under the editor and the draft is unchanged.
4. **Discard** leaves the edit mode without applying.
5. Press **Save** in the top bar to write `pskit.yml`.

`${env:...}`, `${self:...}` and `${opt:...}` stay as written. A file that uses `extends:` shows a notice in the
sidebar footer: only the main file is edited.

From the terminal, edit `pskit.yml` in any editor and check it:

```bash
pskit validate
pskit validate -p gcp -s prod
```

## See also

- [Configuration reference](../configuration.md)
- [Draft, validate and save](README.md#how-studio-drafts-validates-and-saves-pskityml)
- [Concepts](../guide/concepts.md)
