# Publish Hana: GGUF, Hugging Face (public), Docker Hub (public)

Starting point: `/content/drive/MyDrive/hana/hana-stage2-merged/` (stage 2 done, COLAB_STAGE2.md step D).

| Step | Where | Time | Result |
|---|---|---|---|
| F. GGUF export + test | Colab (CPU is enough) | 15 to 20 min | `MyDrive/hana/gguf/hana-pskit-1.5b-q8_0.gguf` (1.6 GB) and `-q4_k_m.gguf` (1.0 GB) |
| G. Hugging Face | Colab | 10 to 20 min | `huggingface.co/<hf-user>/hana-pskit-1.5b` and `...-GGUF`, public |
| H. Docker Hub | your PC (Docker Desktop) | 10 min + upload | `docker.io/<dockerhub-user>/hana-pskit:1.0`, public |

Accounts you need: a Hugging Face account with a **Write** token (huggingface.co > Settings > Access Tokens >
Create new token > Write), and a Docker Hub account. Replace `<hf-user>` and `<dockerhub-user>` below.

## 0. Once: new zip on Drive

The stage-2 zip now also holds `s3_gguf.py`, `s3_test_endpoint.py`, `s3_publish_hf.py` and this file. On your PC:

```
python ai-agent/training/train/make_colab_zip_stage2.py
```

Upload `ai-agent/hana_stage2_colab.zip` to My Drive again (replace the old one).

## 1. Start of the session

**Cell 1**

```python
from google.colab import drive
drive.mount("/content/drive")
```

**Cell 2**

```
%cd /content
!unzip -o -q /content/drive/MyDrive/hana_stage2_colab.zip -d /content/
!ls /content/drive/MyDrive/hana/hana-stage2-merged/
```

## 2. Step F: GGUF

```
!MERGED=/content/drive/MyDrive/hana/hana-stage2-merged OUT=/content/drive/MyDrive/hana/gguf python ./training/train/s3_gguf.py
```

It clones llama.cpp, builds `llama-quantize` and `llama-server` (CPU), writes q8_0 and q4_k_m, and ends with one
line per file. Both must say `chat template with tools OK`.

**Test the GGUF like studio will use it** (OpenAI API with tools):

```
!nohup /content/llama.cpp/build/bin/llama-server -m /content/drive/MyDrive/hana/gguf/hana-pskit-1.5b-q8_0.gguf --jinja -c 8192 --port 8080 > /content/server.log 2>&1 &
!URL=http://127.0.0.1:8080 python ./training/train/s3_test_endpoint.py
```

Four questions; 3 or 4 PASS is good. It is slow on Colab's 2 CPUs (about 1 min per question). To test q4_k_m,
stop the server and start it again with the other file:

```
!pkill -f llama-server; sleep 2
!nohup /content/llama.cpp/build/bin/llama-server -m /content/drive/MyDrive/hana/gguf/hana-pskit-1.5b-q4_k_m.gguf --jinja -c 8192 --port 8080 > /content/server.log 2>&1 &
!URL=http://127.0.0.1:8080 python ./training/train/s3_test_endpoint.py
!pkill -f llama-server
```

If q4_k_m fails where q8_0 passes, publish only q8_0: delete the q4 file from `MyDrive/hana/gguf/` first.

## 3. Step G: Hugging Face

Log in (paste your **Write** token in the box, then Login):

```python
from huggingface_hub import notebook_login
notebook_login()
```

The token is saved in the Colab machine, and the `!python` commands below pick it up. A new runtime needs this
cell again. (Alternative: a Colab Secret named `HF_TOKEN` with `os.environ["HF_TOKEN"] = userdata.get("HF_TOKEN")`.)

Read the two model cards first (uploads nothing):

```
!DRY=1 HF_REPO=<hf-user>/hana-pskit-1.5b python ./training/train/s3_publish_hf.py
!cat /content/hf_cards/README_model.md
```

Publish (public):

```
!HF_REPO=<hf-user>/hana-pskit-1.5b python ./training/train/s3_publish_hf.py
```

It prints both links. The model repo has the safetensors weights, tokenizer, `README.md` (model card with the
eval scores and the Asif Khan credit), `hana_system_prompt.txt` and `hana_tools.json`. The `-GGUF` repo has the
GGUF files and the same two extra files. Rerunning it is safe: it updates the repos.

Anyone can now run it with Ollama too: `ollama run hf.co/<hf-user>/hana-pskit-1.5b-GGUF:Q8_0` (Ollama uses its own
copy of the chat template; for studio, the llama.cpp image below is the tested path).

## 4. Step H: Docker Hub (on your PC, PowerShell, from the repo root)

Start **Docker Desktop** first (`docker version` must show a Server section).

```
docker login
docker build -t <dockerhub-user>/hana-pskit:1.0 --build-arg HF_REPO=<hf-user>/hana-pskit-1.5b-GGUF ai-agent/docker
docker run -d --name hana -p 127.0.0.1:8080:8080 <dockerhub-user>/hana-pskit:1.0
python ai-agent/training/train/s3_test_endpoint.py
```

The build downloads the q8_0 GGUF from your public HF repo (that is why step G comes first). The test talks to
`http://127.0.0.1:8080`; on a modern 8-core CPU expect 10 to 25 s per answer.

Push (Docker Hub creates the repo; check it is **Public** under Repository > Settings > Visibility):

```
docker tag <dockerhub-user>/hana-pskit:1.0 <dockerhub-user>/hana-pskit:latest
docker push <dockerhub-user>/hana-pskit:1.0
docker push <dockerhub-user>/hana-pskit:latest
docker rm -f hana
```

Options:
- **Smaller image:** `--build-arg GGUF=hana-pskit-1.5b-q4_k_m.gguf`, tag it `1.0-q4`.
- **NVIDIA GPU:** `--build-arg BASE=ghcr.io/ggml-org/llama.cpp:server-cuda`, tag it `1.0-cuda`, run with
  `--gpus all`.
- **ARM (Apple Silicon, Graviton):** `docker buildx build --platform linux/amd64,linux/arm64 -t
  <dockerhub-user>/hana-pskit:1.0 --build-arg HF_REPO=<hf-user>/hana-pskit-1.5b-GGUF --push ai-agent/docker`

What anyone can run after this:

```
docker run -d --name hana -p 127.0.0.1:8080:8080 <dockerhub-user>/hana-pskit:1.0
```

Keep the port on `127.0.0.1`: llama-server has no login.

## Errors and fixes

| Error | Fix |
|---|---|
| `is not a model folder (no config.json)` | Run cell 1 (mount), check `MERGED` |
| `chat template MISSING or without tools` | Paste the output; the GGUF can't do tool calls |
| cmake / build error in step F | `!QUANTS=q8_0 BUILD=0 MERGED=... OUT=... python ./training/train/s3_gguf.py` (q8_0 only, no build); test on your PC with Docker instead |
| `raw <tool_call> in the text` | The server was started without `--jinja` |
| `not logged in to Hugging Face` | Run the `notebook_login()` cell; the token needs the **Write** role |
| `403 Forbidden` on upload | Token is read-only, or `<hf-user>` is not your user/org name |
| Docker build `404` on the ADD lines | The GGUF repo is private or the name is wrong; open the URL in a browser |
| `failed to connect to the docker API` | Start Docker Desktop |
