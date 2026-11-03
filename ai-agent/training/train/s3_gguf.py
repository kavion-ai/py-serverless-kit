"""Step F: export the final Hana model to GGUF (the file llama.cpp, Ollama and the Docker image run).

Run in Colab (Drive mounted, see PUBLISH.md):
  MERGED=/content/drive/MyDrive/hana/hana-stage2-merged OUT=/content/drive/MyDrive/hana/gguf python ./training/train/s3_gguf.py
Env (optional):
  QUANTS    comma list, default "q8_0,q4_k_m". q8_0 (about 1.6 GB, best quality) comes straight from the converter;
            q4_k_m (about 1.0 GB, a bit weaker at tool calls) needs llama-quantize, which this script builds.
  NAME      file name prefix, default hana-pskit-1.5b
  LLAMA     llama.cpp checkout, default /content/llama.cpp (cloned if missing)
  BUILD     1 (default) builds llama-quantize and llama-server (CPU, about 5 to 10 min); 0 skips the build
Writes OUT/<NAME>-<quant>.gguf and checks that each file carries the Qwen chat template with the tool section,
because without it the server can't render tools and Hana never calls them.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

MERGED = Path(os.environ.get("MERGED", "/content/drive/MyDrive/hana/hana-stage2-merged"))
OUT = Path(os.environ.get("OUT", "/content/drive/MyDrive/hana/gguf"))
QUANTS = [q.strip().lower() for q in os.environ.get("QUANTS", "q8_0,q4_k_m").split(",") if q.strip()]
NAME = os.environ.get("NAME", "hana-pskit-1.5b")
LLAMA = Path(os.environ.get("LLAMA", "/content/llama.cpp"))
BUILD = os.environ.get("BUILD", "1") == "1"
SRC = Path("/content/hana-gguf-src")  # staging copy: tokenizer files + a link to the weights
F16 = Path("/content/hana-f16.gguf")  # temporary, only for llama-quantize


def run(cmd):
    print("$", " ".join(map(str, cmd)), flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def stage_source():
    """Copy the small files and link the weights, and put the chat template into tokenizer_config.json.

    Recent transformers saves the template as chat_template.jinja; older llama.cpp converters only read it from
    tokenizer_config.json. The Drive folder itself is not changed."""
    if not (MERGED / "config.json").exists():
        raise SystemExit(f"{MERGED} is not a model folder (no config.json). Mount Drive (cell 1) and check MERGED.")
    if SRC.exists():
        shutil.rmtree(SRC)
    SRC.mkdir(parents=True)
    for f in MERGED.iterdir():
        if f.suffix == ".safetensors":
            (SRC / f.name).symlink_to(f)
        elif f.is_file():
            shutil.copy2(f, SRC / f.name)
    cfg_path = SRC / "tokenizer_config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    jinja = SRC / "chat_template.jinja"
    if not cfg.get("chat_template") and jinja.exists():
        cfg["chat_template"] = jinja.read_text(encoding="utf-8")
        cfg_path.write_bytes(json.dumps(cfg, indent=2, ensure_ascii=False).encode("utf-8"))
    if "<tool_call>" not in (cfg.get("chat_template") or ""):
        raise SystemExit("the merged model's chat template has no <tool_call> section; it is not the Qwen template")


def build():
    binaries = [LLAMA / "build" / "bin" / b for b in ("llama-quantize", "llama-server")]
    if all(b.exists() for b in binaries):
        return
    run(["cmake", "-S", LLAMA, "-B", LLAMA / "build", "-DGGML_CUDA=OFF", "-DLLAMA_CURL=OFF",
         "-DCMAKE_BUILD_TYPE=Release"])
    run(["cmake", "--build", LLAMA / "build", "--config", "Release", "-j", str(os.cpu_count() or 2),
         "--target", "llama-quantize", "llama-server"])


def check(path):
    sys.path.insert(0, str(LLAMA / "gguf-py"))
    from gguf import GGUFReader  # the checkout's own gguf-py, matching the converter

    reader = GGUFReader(str(path))
    field = reader.fields.get("tokenizer.chat_template")
    template = bytes(field.parts[field.data[0]]).decode("utf-8") if field else ""
    arch = reader.fields.get("general.architecture")
    arch = bytes(arch.parts[arch.data[0]]).decode("utf-8") if arch else "?"
    ok = "<tool_call>" in template
    print(f"{path.name}: {path.stat().st_size / 2**30:.2f} GiB, arch {arch}, chat template "
          f"{'with tools OK' if ok else 'MISSING or without tools'}")
    if not ok:
        raise SystemExit(f"{path} has no tool chat template; paste this output")


def main():
    if not LLAMA.exists():
        run(["git", "clone", "--depth", "1", "https://github.com/ggml-org/llama.cpp", LLAMA])
    stage_source()
    OUT.mkdir(parents=True, exist_ok=True)
    convert = [sys.executable, LLAMA / "convert_hf_to_gguf.py", SRC]
    done = []
    if "q8_0" in QUANTS:
        out = OUT / f"{NAME}-q8_0.gguf"
        run(convert + ["--outtype", "q8_0", "--outfile", out])
        done.append(out)
    others = [q for q in QUANTS if q != "q8_0"]
    if BUILD:
        build()
    if others:
        quantize = LLAMA / "build" / "bin" / "llama-quantize"
        if not quantize.exists():
            raise SystemExit(f"{quantize} is missing: run with BUILD=1 or set QUANTS=q8_0")
        run(convert + ["--outtype", "f16", "--outfile", F16])
        for q in others:
            out = OUT / f"{NAME}-{q}.gguf"
            run([quantize, F16, out, q.upper()])
            done.append(out)
        F16.unlink()
    print("\n== GGUF files ==")
    for path in done:
        check(path)
    print(f"\nwritten to {OUT}")


if __name__ == "__main__":
    main()
