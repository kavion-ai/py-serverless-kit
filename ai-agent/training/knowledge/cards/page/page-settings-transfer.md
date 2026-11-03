# Studio: Import / export settings

How to open: The top bar button ⇅ Settings opens a drawer titled "Import / export settings and config". The same form is section "Move settings to another machine" on Setup & credentials. The section hint is "export / import .pskit, encrypted".

What it is for: Copy saved servers, clusters, load balancers, on-prem services, and SSH logins to another machine. The section text says .pskit stays out of git, so a fresh clone has none of those. The file holds secrets: SSH passwords and keys (including those in ~/.ssh), service passwords and tokens, admin tokens, and env files named in pskit.yml. It is encrypted with your passphrase. The text says to send the passphrase another way. Terraform state is not included.

What you see: Export has Passphrase, Again, the toggle "Include pskit.yml (functions, resources, providers)", and Export settings (Exporting… while it runs). The passphrase must be at least 8 characters (`MIN_PASSPHRASE` in Setup.tsx). A shorter value shows "at least 8 characters". Again shows "does not match" when it differs. Import has Settings file (accepts .pskit-settings and .json), Passphrase, and Preview (Checking… while the preview runs). The replace toggle label is "Replace: remove saved servers, clusters and services that are not in the file (default: merge, the file's entries win)". After Preview, a table has columns Settings, Added, Replaced, and either Removed or Kept. Import into this project runs the import. The CLI names in the section text are `pskit settings export` and `pskit settings import`.

What you can do: Export downloads the encrypted file after both passphrase fields match. Preview shows what would change and does not write yet. Import into this project writes the planned changes. If one of the written paths is pskit.yml, the page reloads so the imported project replaces the old draft. In `src/py_serverless_kit/cli/main.py`, `pskit settings import` calls `click.confirm` with a prompt that starts "Import into ".

Tips and limits: Merge is the default. Replace removes saved servers, clusters, and services that are not in the file. The section text says the file is always encrypted with the passphrase, and to send the passphrase another way. Do not put the passphrase in pskit.yml.

Sources: `dashboard-ui/src/studio/views/Setup.tsx`, `dashboard-ui/src/studio/App.tsx`, `src/py_serverless_kit/cli/main.py`
