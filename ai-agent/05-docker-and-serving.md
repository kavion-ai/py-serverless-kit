# 5. Docker images, hardware, install on this machine or a server

## 5.1 Images

One repository, published publicly (GHCR and/or Docker Hub), multi-arch where the engine allows it:

| Tag | Engine | Model | Arch | For |
|---|---|---|---|---|
| `pskit-agent:<ver>-small` | Ollama | small, GGUF Q4_K_M | amd64, arm64 | Laptops, CPU, 8 GB GPUs |
| `pskit-agent:<ver>-medium` | Ollama | medium MoE, GGUF Q4_K_M | amd64, arm64 | **Default**: 32 GB RAM CPU or 24 GB GPU |
| `pskit-agent:<ver>-large` | Ollama | large, GGUF Q4_K_M | amd64 | 24–48 GB GPU servers |
| `pskit-agent:<ver>-<size>-vllm` | vLLM | AWQ/FP8 | amd64 (CUDA) | GPU servers serving a team |
| `pskit-agent:<ver>-<size>-rocm` | Ollama ROCm | GGUF | amd64 | AMD GPUs |
| `…-slim` variants | same | **no weights inside**; pulled on first start into a volume | | Smaller pull, resumable downloads |

`<ver>` is the model release (`2.10.0-1`), with moving tags `small`, `medium`, `large`, `latest` = `medium`.

**Weights inside the image or not?** Both. *Bundled* (default) works offline and air-gapped after one `docker pull`,
which matters for on-prem users. *Slim* keeps the image small, downloads from the model hub with a SHA-256 check
into the `pskit-agent-models` volume, and resumes after interruptions. Studio offers bundled by default and slim
when disk is short.

## 5.2 Image contents (Ollama variant)

```text
ai-agent/docker/
  Dockerfile.ollama
  Dockerfile.vllm
  Modelfile.tmpl          # FROM ./model.gguf, TEMPLATE (the base model's chat template with tools), PARAMETER num_ctx 32768, temperature 0.2
  entrypoint.sh           # start server, create model if missing, warm up, write /health
  pskit-agent.json        # {"model": "...", "trained_for": "2.10", "tool_protocol": 1, "context": 32768, "embeddings": "..."}
  compose.example.yml
```

```dockerfile
# Dockerfile.ollama (sketch: pin by digest in the real file)
FROM ollama/ollama:<pinned-version>
COPY model.gguf /opt/pskit/model.gguf          # absent in -slim
COPY embed.gguf /opt/pskit/embed.gguf          # small embedding model (permissive licence)
COPY Modelfile.tmpl pskit-agent.json entrypoint.sh /opt/pskit/
ENV OLLAMA_HOST=0.0.0.0:11434 OLLAMA_KEEP_ALIVE=24h OLLAMA_NUM_PARALLEL=2
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s CMD ["/opt/pskit/entrypoint.sh", "health"]
ENTRYPOINT ["/opt/pskit/entrypoint.sh"]
```

Gotchas to handle in the entrypoint and the tests:
- **Context length:** Ollama's default context is small. `num_ctx` must be set in the Modelfile (32k), otherwise
  long tool traces are silently cut off. The same goes for vLLM's `--max-model-len`.
- **Tool-call template:** the Modelfile `TEMPLATE` must be the base model's tool template. vLLM needs
  `--enable-auto-tool-choice --tool-call-parser <family parser>`. A smoke test sends one tool call on container start.
- **Warm-up:** load the model on start (one short request) so the first chat message isn't slow.
- `/opt/pskit/pskit-agent.json` is served at `GET /pskit-agent.json` (a tiny sidecar route, or read via `docker
  exec`) so studio can check compatibility.

## 5.3 Hardware sizing (estimates; replace with measured numbers in Phase 3)

| Size | RAM/VRAM needed (Q4, 32k ctx) | CPU speed (modern 8-core) | GPU speed |
|---|---|---|---|
| Small 7–8B | ~7–9 GB | ~8–15 tok/s | 60–120 tok/s (8 GB+) |
| Medium MoE ~30B-A3B | ~20–24 GB | ~15–30 tok/s (only ~3B active) | 80–150 tok/s (24 GB) |
| Large 24–32B | ~20–26 GB | too slow (2–5 tok/s) | 30–60 tok/s (24–48 GB) |

Studio's **recommendation logic**: read the target's RAM / CPU / GPU (`nvidia-smi`, `rocm-smi`, `/proc/meminfo`, the
existing server test that already reports OS/CPU/memory/disk) and preselect the largest size that fits with
headroom. On macOS it recommends native Ollama (Metal) over Docker.

## 5.4 Where it runs: the user's choice when the chat opens

```text
┌ Choose where the assistant runs ───────────────────────────────────────────┐
│ ● This machine (Docker)        16 GB RAM, no GPU → small recommended       │
│ ○ Saved server: gpu-box-1      64 GB, RTX 4090 → large recommended         │
│ ○ Saved server: build-01       32 GB, no GPU → medium                       │
│ ○ Native Ollama on this Mac    (faster than Docker on Apple Silicon)       │
│ ○ Existing endpoint…           URL + key (vLLM, LM Studio, company proxy)  │
│ ○ Claude API…                  your API key; best quality, needs internet  │
│ Model size: [small ▾]  Image: [bundled ▾]  GPU: [auto ▾]                    │
│                                         [ Install & start ]  [ Cancel ]    │
└────────────────────────────────────────────────────────────────────────────┘
```

### Install flow (reuses existing studio code)

| Step | This machine | Saved server | Reused code |
|---|---|---|---|
| 1. Check Docker | `docker version` / daemon running; show install guide if missing | same over SSH; offer *Install Docker* (studio can already install Docker on a server) | `vscode.py::docker_info`, `onprem_services` install runtime |
| 2. Check resources | RAM/disk/GPU | same via SSH | server test in `onprem_servers.py` |
| 3. GPU runtime | NVIDIA Container Toolkit present? Otherwise CPU, with a note | same; can offer to install the toolkit (tier 3, asks) | new small script in the services catalog |
| 4. Pull | streamed `docker pull` log in the panel, progress bar | same over SSH | `onprem_services._stream_run` |
| 5. Run | `docker run -d --name pskit-agent -p 127.0.0.1:11434:11434 -v pskit-agent-models:/root/.ollama [--gpus all] image` | same, **bound to the server's 127.0.0.1** | `docker_argv(target, ...)` |
| 6. Connect | `http://127.0.0.1:11434/v1` | **SSH tunnel** `ssh -N -L <local>:127.0.0.1:11434 server`, kept alive by studio | ssh helpers in `onprem_services` / `onprem_terminal` |
| 7. Verify | health, `pskit-agent.json` compatibility, one tool-call smoke test, embeddings build | same | new |
| 8. Remember | `.pskit/studio/agent/runtime.json` (+ global default in `~/.pskit/agent.json`) | same | — |

Implementation choice: add **`pskit-agent` as an entry in the on-prem services catalog** (`core/onprem_services.py`
`_svc(...)`) with its image, port, health command, volume and GPU flag. It then gets Details, logs, Console, Remove
and the server picker for free, and the CLI can drive it the same way (`pskit agent up --server gpu-box-1`).

### Team / shared server mode (optional)

For a team sharing one GPU server: the vLLM image behind a reverse proxy (Caddy) with TLS and a bearer token per
user. Studio connects with *Existing endpoint…*. Never publish the raw Ollama/vLLM port to a network, because they have
no authentication. Studio refuses to save an `http://` endpoint that isn't loopback without an explicit
"I understand" checkbox.

## 5.5 Lifecycle

| Action | Where in UI | CLI |
|---|---|---|
| Status (running, model, RAM used, tok/s of the last answer) | Chat header chip | `pskit agent status` |
| Stop / Start | chip menu | `pskit agent down` / `up` |
| Update to the image matching this pskit version | banner when a newer compatible model exists | `pskit agent up --pull` |
| Switch size / location | chip menu → the dialog above | `pskit agent up --size large --server gpu-box-1` |
| Remove (container + volume) | Settings → Assistant → Remove | `pskit agent remove [--keep-models]` |
| Logs | chip menu → Logs | `pskit agent logs` |

Idle handling: Ollama unloads the model after `OLLAMA_KEEP_ALIVE`. Studio can stop the container when studio exits
(setting: *keep running* / *stop with studio*).

## 5.6 Publishing pipeline (CI)

```text
train (manual trigger) -> eval gate (07) -> export GGUF/AWQ -> build images (buildx, multi-arch)
  -> smoke test each image (start, health, tool call, 5 bench tasks)
  -> scan (Trivy/Grype), SBOM (syft), sign (cosign, keyless)
  -> push to GHCR / Docker Hub with immutable <ver> tag, then move size tags
  -> publish model card + weights to the model hub
  -> update the compatibility table read by studio
```

- Image size check: bundled small ≈ 5–6 GB, medium ≈ 18–20 GB, large ≈ 20+ GB. Registries accept these sizes, but
  pulls are slow, which is another reason for the *slim* option and resumable downloads.
- Public images must carry: base model licence file, our model licence (Apache-2.0 if the base allows it), third-party
  notices for the engine (Ollama MIT, vLLM Apache-2.0), and an acceptable-use note.
