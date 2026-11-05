# Diagrams

Each diagram in the docs is a PNG with its Mermaid source next to it: `<name>.png` and `<name>.mmd`.

The docs show the PNG, not a Mermaid block. GitHub draws Mermaid blocks in a frame from another site
(`viewscreen.githubusercontent.com`), and an ad blocker, privacy extension or company network filter that blocks that site
leaves readers with a spinner that never ends. Images also show in editors without a Mermaid extension.

## Change a diagram

1. Edit `<name>.mmd`.
2. Render it again from this folder (needs Node.js):

   ```bash
   npx -y @mermaid-js/mermaid-cli -i <name>.mmd -o <name>.png -s 2 -b white
   ```

3. Commit both files.
