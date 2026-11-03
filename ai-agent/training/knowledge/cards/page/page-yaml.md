# Studio: YAML

How to open: Left navigation label YAML.

What it is for: The generated pskit.yml, a diff against the file on disk, and a raw edit mode. The page subtitle says "What Save writes. Comments in the original file are not preserved; a backup is kept in .pskit/studio/backups/."

What you see: A segmented control labeled YAML mode with Preview, Diff vs disk, and Edit raw YAML. Preview is a read-only editor, aria-label "Generated pskit.yml". Diff vs disk uses a before/after view of the file on disk and the generated text. Edit raw YAML shows the hint "Edit the YAML directly, then apply it to the draft. Forms update to match." The buttons are Apply to draft (Parsing… while busy) and Discard. Parse issues render in an IssueList. While validation has not yet produced YAML, the page shows Rendering….

What you can do: Preview and diff do not write the file. Apply to draft parses the text and replaces the in-memory draft, so the other pages match. Discard leaves edit mode and drops the edit buffer. The top-bar Save is what writes pskit.yml. docs/studio.md#saving-what-changes-in-pskityml says values keep their written form (`${env:API_KEY}`, `${self:custom.x}`, `${opt:...}` are saved as written), comments are not kept, and key order follows the studio layout. Before every save the previous file is copied to `.pskit/studio/backups/pskit.<timestamp>.yml` and the last 20 are kept. A file that uses `extends:` is shown with a notice: only the main file is edited. A config that fails validation can still be saved.

Tips and limits: Apply to draft is not Save. You can apply a draft that still has problems, then save it, which matches the doc sentence that a failing config can still be saved. If the file on disk changed after load, the top-bar conflict modal (Cancel, Reload, Overwrite) is the one that decides, as described in that same section of the doc.

Sources: `dashboard-ui/src/studio/views/Yaml.tsx`, `docs/studio.md#what-you-can-do`, `docs/studio.md#saving-what-changes-in-pskityml`
