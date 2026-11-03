"""Step G: publish Hana to the Hugging Face Hub (two public repos: the model, and its GGUF files).

Run in Colab (Drive mounted, HF_TOKEN set from Colab secrets, see PUBLISH.md):
  HF_REPO=<your-hf-name>/hana-pskit-1.5b python ./training/train/s3_publish_hf.py
Env (optional):
  MERGED    default /content/drive/MyDrive/hana/hana-stage2-merged
  GGUF_DIR  default /content/drive/MyDrive/hana/gguf (its *.gguf go to <HF_REPO>-GGUF; skipped if empty)
  EVAL      default /content/drive/MyDrive/hana/stage2/eval_stage2.md (its scores go into the model card)
  PRIVATE=1 create the repos private (default public)
  DRY=1     only write the two model cards to /content/hf_cards/ to read them first; uploads nothing
Uploads the weights and tokenizer, the model card (README.md), hana_system_prompt.txt and hana_tools.json
(Hana only works well with exactly that system prompt and those tools).
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from task_common import ENV_LINE, SYSTEM_PROMPT, TOOLS  # noqa: E402

REPO = os.environ.get("HF_REPO", "")
MERGED = Path(os.environ.get("MERGED", "/content/drive/MyDrive/hana/hana-stage2-merged"))
GGUF_DIR = Path(os.environ.get("GGUF_DIR", "/content/drive/MyDrive/hana/gguf"))
EVAL = Path(os.environ.get("EVAL", "/content/drive/MyDrive/hana/stage2/eval_stage2.md"))
PRIVATE = os.environ.get("PRIVATE") == "1"
DRY = os.environ.get("DRY") == "1"
BASE = "Qwen/Qwen2.5-1.5B-Instruct"
CREATOR = "Asif Khan (https://www.linkedin.com/in/asif-khan-31b7a8187/)"


def eval_lines():
    if not EVAL.exists():
        return "(not included)"
    lines, on = [], False
    for line in EVAL.read_text(encoding="utf-8").splitlines():
        if line.startswith("## stage 2"):
            on = True
            continue
        if on and line.startswith("## "):
            break
        if on and line.startswith("- "):
            lines.append(line)
    return "\n".join(lines) or "(not included)"


ABOUT = """# Hana: the pskit studio assistant (1.5B)

Hana is the AI assistant of **pskit studio**, the web UI of
[py-serverless-kit](https://pypi.org/project/py-serverless-kit/) (`pskit`). She answers questions about pskit,
gives how-to steps for studio, the terminal and code, and works as an agent: she reads the project, proposes a
plan, edits `pskit.yml` and handler code, and checks the result with `validate` and a local invoke.

**Created and developed by __CREATOR__.**

| | |
|---|---|
| Base model | [__BASE__](https://huggingface.co/__BASE__) (Apache-2.0) |
| Training | 2 LoRA stages, each merged: 1. pskit knowledge (docs, CLI, studio, config), 2. tool use on real tasks, with 25% stage-1 replay |
| Providers trained for tool use | AWS, Azure, GCP, on-premises (on-premises is 40% of the task data) |
| Context used in training | 4,096 tokens per conversation |
| Tool-call format | Qwen / Hermes `<tool_call>{json}</tool_call>`, from the model's own chat template |

## Evaluation (task validation set, next step of every assistant turn)

__EVAL__

## Use it with the right system prompt and tools

Hana was trained with one system prompt and 10 tools; both are in this repo:
`hana_system_prompt.txt` (add the `Environment:` line at the end) and `hana_tools.json`. The tools are run by
studio (`search_docs`, `get_project`, `read_file`, `get_validation`, `propose_plan`, `ask_user`, `set_config`,
`write_file`, `validate`, `invoke_local`); none of them deploys.
"""

LIMITS = """## Limits

- A 1.5B model: she can be wrong. Studio checks every change with `pskit validate` before it counts; always
  review a plan before approving it.
- Tool use was trained on AWS, Azure, GCP and on-premises only. Questions about the other pskit providers fall
  back to stage-1 knowledge.
- Trained for pskit 2.10. Newer pskit versions may have keys or flags she doesn't know.
- She never deploys or removes anything herself; she points to the Deploy page or the command.

## Licence

Apache-2.0, like the base model. Created and developed by __CREATOR__.
"""

USE_HF = """## Transformers

```python
import json
from huggingface_hub import hf_hub_download
from transformers import AutoModelForCausalLM, AutoTokenizer

repo = "__REPO__"
tok = AutoTokenizer.from_pretrained(repo)
model = AutoModelForCausalLM.from_pretrained(repo, dtype="auto", device_map="auto")
system = open(hf_hub_download(repo, "hana_system_prompt.txt"), encoding="utf-8").read()
system += "\\n__ENV__"
tools = json.load(open(hf_hub_download(repo, "hana_tools.json"), encoding="utf-8"))

messages = [{"role": "system", "content": system}, {"role": "user", "content": "how do I add a schedule in studio?"}]
ids = tok.apply_chat_template(messages, tools=tools, add_generation_prompt=True, return_tensors="pt").to(model.device)
out = model.generate(ids, max_new_tokens=400, do_sample=False)
print(tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True))
```

The answer is either text or a `<tool_call>{...}</tool_call>`: run the tool, add the result as a `tool` message
and generate again. GGUF files for llama.cpp / Ollama / Docker: [__REPO__-GGUF](https://huggingface.co/__REPO__-GGUF).
"""

USE_GGUF = """## llama.cpp server (OpenAI-compatible, tool calls parsed)

```bash
llama-server -m __FILE__ --jinja -c 8192 --host 127.0.0.1 --port 8080
```

`--jinja` is required: it renders the tools with the model's own chat template and returns `tool_calls`.
Then call `http://127.0.0.1:8080/v1/chat/completions` with the system prompt and `tools` from
[__MAIN__](https://huggingface.co/__MAIN__) (`hana_system_prompt.txt`, `hana_tools.json`).

## Files

__FILES__

q8_0 is the closest to the full model and the better choice for tool calls; q4_k_m is smaller and faster on CPU.
"""


def card(kind, files=()):
    env = ENV_LINE.format(provider="onprem", stage="dev", mode="ask", page="Functions")
    if kind == "model":
        head = (f"---\nlicense: apache-2.0\nbase_model: {BASE}\nlanguage:\n- en\npipeline_tag: text-generation\n"
                "library_name: transformers\ntags:\n- pskit\n- py-serverless-kit\n- serverless\n- terraform\n"
                "- tool-calling\n- agent\n- qwen2\n---\n\n")
        body = ABOUT + "\n" + USE_HF + "\n" + LIMITS
    else:
        head = (f"---\nlicense: apache-2.0\nbase_model: {REPO}\nlanguage:\n- en\npipeline_tag: text-generation\n"
                "tags:\n- gguf\n- llama.cpp\n- pskit\n- tool-calling\n---\n\n")
        listing = "\n".join(f"- `{f.name}` ({f.stat().st_size / 2**30:.2f} GiB)" for f in files)
        body = ABOUT.replace("# Hana:", "# Hana GGUF:") + "\n" + USE_GGUF + "\n" + LIMITS
        body = body.replace("__FILES__", listing).replace("__FILE__", files[0].name).replace("__MAIN__", REPO)
    return (head + body).replace("__CREATOR__", CREATOR).replace("__BASE__", BASE).replace("__EVAL__", eval_lines()) \
        .replace("__REPO__", REPO).replace("__ENV__", env)


def main():
    if "/" not in REPO:
        raise SystemExit("set HF_REPO=<your-hf-name>/hana-pskit-1.5b")
    if not (MERGED / "model.safetensors").exists():
        raise SystemExit(f"{MERGED} has no model.safetensors. Mount Drive (cell 1) and check MERGED.")
    ggufs = sorted(GGUF_DIR.glob("*.gguf"), key=lambda p: (not p.name.endswith("q8_0.gguf"), p.name))
    cards = {"model": card("model")}
    if ggufs:
        cards["gguf"] = card("gguf", ggufs)
    extras = {"hana_system_prompt.txt": SYSTEM_PROMPT.encode("utf-8"),
              "hana_tools.json": json.dumps(TOOLS, indent=2, ensure_ascii=False).encode("utf-8")}
    if DRY:
        out = Path("/content/hf_cards")
        out.mkdir(exist_ok=True)
        for k, text in cards.items():
            (out / f"README_{k}.md").write_bytes(text.encode("utf-8"))
        print("wrote", ", ".join(str(p) for p in sorted(out.iterdir())), "(nothing uploaded)")
        return

    from huggingface_hub import HfApi, get_token

    token = os.environ.get("HF_TOKEN") or get_token()  # HF_TOKEN, or the token saved by notebook_login()
    if not token:
        raise SystemExit("not logged in to Hugging Face: run the notebook_login() cell in PUBLISH.md (Write token)")
    api = HfApi(token=token)
    print("logged in as", api.whoami()["name"])

    api.create_repo(REPO, repo_type="model", private=PRIVATE, exist_ok=True)
    api.upload_folder(repo_id=REPO, folder_path=str(MERGED), ignore_patterns=["README.md"],
                      commit_message="Hana stage 2 (final) weights and tokenizer")
    for name, data in {"README.md": cards["model"].encode("utf-8"), **extras}.items():
        api.upload_file(repo_id=REPO, path_or_fileobj=data, path_in_repo=name, commit_message=f"add {name}")
    print(f"model: https://huggingface.co/{REPO}")

    if ggufs:
        gguf_repo = REPO + "-GGUF"
        api.create_repo(gguf_repo, repo_type="model", private=PRIVATE, exist_ok=True)
        for f in ggufs:
            print("uploading", f.name, flush=True)
            api.upload_file(repo_id=gguf_repo, path_or_fileobj=str(f), path_in_repo=f.name,
                            commit_message=f"add {f.name}")
        for name, data in {"README.md": cards["gguf"].encode("utf-8"), **extras}.items():
            api.upload_file(repo_id=gguf_repo, path_or_fileobj=data, path_in_repo=name, commit_message=f"add {name}")
        print(f"gguf:  https://huggingface.co/{gguf_repo}")
    else:
        print(f"no *.gguf in {GGUF_DIR}: run s3_gguf.py first if you want the GGUF repo")


if __name__ == "__main__":
    main()
