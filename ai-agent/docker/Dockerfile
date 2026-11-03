# Hana, the pskit studio assistant: llama.cpp server with the GGUF model inside (works offline after one pull).
#
# Build (the GGUF is downloaded from the public Hugging Face repo at build time):
#   docker build -t <dockerhub-user>/hana-pskit:1.0 --build-arg HF_REPO=<hf-user>/hana-pskit-1.5b-GGUF ai-agent/docker
# GPU (NVIDIA):  add  --build-arg BASE=ghcr.io/ggml-org/llama.cpp:server-cuda  and run with --gpus all
# Run:
#   docker run -d --name hana -p 127.0.0.1:8080:8080 <dockerhub-user>/hana-pskit:1.0
# API: OpenAI-compatible, http://127.0.0.1:8080/v1/chat/completions (tool calls parsed thanks to --jinja).
# The server has no authentication: publish the port on 127.0.0.1 only (or behind a proxy with a token).

ARG BASE=ghcr.io/ggml-org/llama.cpp:server
FROM ${BASE}

ARG HF_REPO
ARG GGUF=hana-pskit-1.5b-q8_0.gguf
ARG VERSION=1.0

LABEL org.opencontainers.image.title="hana-pskit" \
      org.opencontainers.image.description="Hana, the AI assistant of pskit studio (py-serverless-kit), llama.cpp server" \
      org.opencontainers.image.authors="Asif Khan (https://www.linkedin.com/in/asif-khan-31b7a8187/)" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.source="https://huggingface.co/${HF_REPO}"

ADD --chmod=644 https://huggingface.co/${HF_REPO}/resolve/main/${GGUF} /models/hana.gguf
ADD --chmod=644 https://huggingface.co/${HF_REPO}/resolve/main/hana_system_prompt.txt /models/hana_system_prompt.txt
ADD --chmod=644 https://huggingface.co/${HF_REPO}/resolve/main/hana_tools.json /models/hana_tools.json

# The base image's entrypoint is llama-server and its HEALTHCHECK calls http://localhost:8080/health.
# -c 8192: Hana was trained on conversations up to 4,096 tokens; 8,192 leaves room for long tool results.
# --parallel 1 keeps all 8,192 tokens for one chat (the context is split between parallel slots).
EXPOSE 8080
CMD ["-m", "/models/hana.gguf", "--alias", "hana", "--jinja", "-c", "8192", "--parallel", "1", \
     "--host", "0.0.0.0", "--port", "8080"]
