# New project page in studio

Search terms: new project, create project, scaffold, pskit init, template, service name, starter, empty folder, language, TypeScript, JavaScript

The **Create a pskit project** page appears instead of the sidebar when the studio folder has no `pskit.yml`. It does
the same as `pskit init`.

## Create a new project in studio

The studio New project page creates `pskit.yml` and starter handler code in an empty folder.

1. Start studio in an empty folder:

   ```bash
   mkdir my-service && cd my-service
   pskit studio --open
   ```

2. The page **Create a pskit project** opens ("No pskit.yml in this folder yet").
3. **Service name** (required): 2 to 32 characters, lowercase letters, digits and dashes, starting with a letter. It
   names every cloud resource. The default is `my-service`.
4. **Provider**: click one of the provider cards. Each card shows the provider's name, its id (`aws`, `onprem`, ...),
   a badge for `beta` or `experimental` tiers, and chips for what it supports: HTTP, Schedule, Queue, Storage, Topic,
   SMTP and Native workflows. Grey chips are not supported.
5. **Language**: **Python** (handlers in `app/*.py`), **JavaScript** (`src/*.js`, needs Node.js) or **TypeScript**
   (`src/*.ts`, compiled with `tsc` when packaging). JavaScript and TypeScript are disabled for providers that run
   Python only in pskit.
6. **Template**:

   | Template | What you get |
   |---|---|
   | **HTTP API** | One HTTP function. The smallest start |
   | **Events** | HTTP plus schedule, queue, storage and topic examples |
   | **Workflow** | HTTP plus a small step-function workflow |
   | **Everything** | All of the above |

7. Click **Create project**. Studio writes the files and opens the [Overview](overview.md) page.

If scaffold files already exist (for example `app/handlers.py`), studio asks **Files already exist** with
**Overwrite**. Cancel keeps your files.

## Create the same project from the terminal

`pskit init` takes the same choices as the studio New project page:

```bash
pskit init my-service -p aws -t http                 # Python, HTTP API template
pskit init . -p gcp -t workflow                      # in the current folder
pskit init svc -p onprem -t full --name orders       # Everything, service name "orders"
pskit init api -p aws --typescript                   # TypeScript handlers
pskit init api -p gcp --runtime nodejs22             # JavaScript handlers
```

| Studio field | `pskit init` option |
|---|---|
| Service name | `--name` (default: the folder name) |
| Provider | `-p, --provider` |
| Language | `-l, --language python|javascript|typescript` (or `--typescript`) |
| Template | `-t, --template http|events|workflow|full` |
| Overwrite | `--force` |

Then open the project in studio with `pskit studio --open`.

## See also

- [Studio guide](README.md)
- [Overview & provider page](overview.md)
- [Concepts: project, service, provider](../guide/concepts.md)
- [Providers](../providers/README.md)
