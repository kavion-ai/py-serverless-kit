"""Where the Hana model runs, chosen when the chat opens:

* ``local``: the ``hana-pskit`` Docker image on this machine (``docker run`` on ``127.0.0.1:<port>``);
* ``server``: the same image on a saved SSH server (``Servers`` in studio), bound to the server's ``127.0.0.1``
  and reached through an SSH tunnel that the studio keeps open;
* ``endpoint``: any OpenAI-compatible URL the user already runs (llama-server, Ollama, vLLM, LM Studio).

The choice is stored in ``.pskit/studio/hana.json`` (no secrets: an API key is read from an environment variable
whose *name* is stored). The model server has no login, so it is never published beyond loopback.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..project import StudioError
from .model import LocalModel, Model, ModelError, check_url

HF_REPO = os.environ.get("PSKIT_HANA_HF_REPO") or "ak2311581/hana-pskit-1.5b-GGUF"
HF_FILES = [
    {"file": "hana-pskit-1.5b-q8_0.gguf", "size_gb": 1.6, "label": "Best answers (1.6 GB, about 2 GB of RAM)"},
    {"file": "hana-pskit-1.5b-q4_k_m.gguf", "size_gb": 1.0, "label": "Smaller and faster (1.0 GB, about 1.4 GB of RAM)"},
]
LLAMA_CPP_INDEX = "https://abetlen.github.io/llama-cpp-python/whl/cpu"  # prebuilt CPU wheels (no compiler needed)
MODELS_DIR = Path.home() / ".cache" / "pskit" / "hana"

DEFAULT_IMAGE = os.environ.get("PSKIT_HANA_IMAGE") or "ak2311581/hana-pskit:1.0"
CONTAINER = "pskit-hana"
CONTAINER_PORT = 8080
DEFAULT_PORT = 8790
CONFIG = Path(".pskit") / "studio" / "hana.json"
_IMAGE_RE = re.compile(r"^[a-z0-9][a-z0-9._/:@-]{0,199}$")
_ENV_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")
Emit = Callable[[str], None]
Runner = Callable[[List[str], float], "subprocess.CompletedProcess[str]"]


def _run(cmd: List[str], timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, never a shell
        cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace"
    )


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


def _free_port(preferred: int = DEFAULT_PORT) -> int:
    if _port_free(preferred):
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_ready(url: str, timeout: float, emit: Optional[Emit] = None) -> bool:
    """llama-server answers ``/health`` with 503 while it loads the model, then 200."""
    deadline = time.time() + timeout
    said = False
    while time.time() < deadline:
        try:
            with urlopen(url + "/health", timeout=3) as resp:  # noqa: S310 - our own loopback URL
                if resp.status == 200:
                    return True
        except HTTPError as exc:
            if exc.code == 503 and emit and not said:
                emit("loading the model...")
                said = True
            elif exc.code == 404:  # not llama-server: fall back to the OpenAI model list
                return Model(url).health()["ok"]
        except (URLError, OSError, ValueError):
            pass
        time.sleep(1)
    return False


def check_image(image: str) -> str:
    image = (image or "").strip()
    if not _IMAGE_RE.match(image):
        raise StudioError(400, "invalid image name")
    return image


class Runtime:
    def __init__(self, root: Path, docker: str = "docker", runner: Optional[Runner] = None) -> None:
        self.root = Path(root).resolve()
        self.docker = docker
        self.runner: Runner = runner or _run
        self._tunnel: Optional[subprocess.Popen] = None
        self._local: Optional[LocalModel] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ config
    @property
    def config_path(self) -> Path:
        return self.root / CONFIG

    def config(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, data: Dict[str, Any]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_bytes((json.dumps(data, indent=2) + "\n").encode("utf-8"))

    def forget(self) -> None:
        try:
            self.config_path.unlink()
        except OSError:
            pass

    def model(self) -> Any:
        cfg = self.config()
        if cfg.get("target") == "huggingface" and cfg.get("path"):
            with self._lock:  # one loaded model per studio (1-2 GB of RAM)
                if self._local is None or self._local.path != cfg["path"]:
                    self._local = LocalModel(str(cfg["path"]))
                return self._local
        if not cfg.get("url"):
            raise StudioError(409, "Hana is not set up yet: choose where she runs", code="hana-setup")
        self.ensure_tunnel(cfg)
        key_env = str(cfg.get("api_key_env") or "")
        return Model(str(cfg["url"]), api_key=os.environ.get(key_env, "") if key_env else "")

    def use_endpoint(self, url: str, api_key_env: str = "") -> Dict[str, Any]:
        try:
            url = check_url(url)
        except ModelError as exc:
            raise StudioError(400, str(exc)) from None
        if api_key_env and not _ENV_RE.match(api_key_env):
            raise StudioError(400, "api_key_env must be an environment variable name such as OPENAI_API_KEY")
        self.save({"target": "endpoint", "url": url, "api_key_env": api_key_env})
        return self.status()

    # ------------------------------------------------------------------ status
    def docker_info(self) -> Dict[str, Any]:
        try:
            proc = self.runner([self.docker, "version", "--format", "{{.Server.Version}}"], 10)
        except FileNotFoundError:
            return {"available": False, "error": "Docker is not installed (the `docker` command was not found)."}
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"available": False, "error": f"Docker did not answer: {exc}"}
        if proc.returncode != 0:
            return {"available": False,
                    "error": "Docker is installed but not running. Start Docker Desktop / the docker service."}
        return {"available": True, "version": proc.stdout.strip()}

    def _container(self) -> Optional[Dict[str, Any]]:
        try:
            proc = self.runner([self.docker, "container", "inspect", CONTAINER], 15)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        try:
            data = json.loads(proc.stdout)
        except ValueError:
            return None
        if not (isinstance(data, list) and data):
            return None
        info = data[0]
        ports = ((info.get("NetworkSettings") or {}).get("Ports") or {}).get(f"{CONTAINER_PORT}/tcp") or []
        port = next((b.get("HostPort") for b in ports if b.get("HostPort")), None)
        return {"running": bool((info.get("State") or {}).get("Running")),
                "image": (info.get("Config") or {}).get("Image"), "port": int(port) if port else None}

    def status(self, deep: bool = True) -> Dict[str, Any]:
        cfg = self.config()
        out: Dict[str, Any] = {"configured": bool(cfg.get("url") or cfg.get("path")), "target": cfg.get("target"),
                               "url": cfg.get("url") or cfg.get("path"), "server": cfg.get("server"),
                               "image": cfg.get("image") or DEFAULT_IMAGE, "default_image": DEFAULT_IMAGE,
                               "hf_repo": cfg.get("repo") or HF_REPO, "hf_files": HF_FILES,
                               "hf_file": cfg.get("file") or HF_FILES[0]["file"],
                               "ready": False, "model": None, "error": None}
        if not deep:
            return out
        out["llama_cpp"] = importlib.util.find_spec("llama_cpp") is not None
        docker = self.docker_info() if cfg.get("target") in (None, "local") else {"available": None}
        out["docker"] = docker
        if docker.get("available"):
            out["container"] = self._container()
        # What to pick when nothing is set up: Docker when it runs here (the tested image), else Hugging Face.
        out["recommended"] = "local" if docker.get("available") else "huggingface"
        if cfg.get("target") == "huggingface":
            health = LocalModel(str(cfg.get("path") or "")).health()
            out.update(ready=health["ok"], model=health["model"], error=health["error"])
            return out
        if cfg.get("url"):
            try:
                self.ensure_tunnel(cfg)
            except StudioError as exc:
                out["error"] = exc.message
                return out
            health = Model(str(cfg["url"])).health()
            out.update(ready=health["ok"], model=health["model"], error=health["error"])
        return out

    # ------------------------------------------------------------------ install / start
    def install_local(self, job: Any, image: str) -> int:
        emit = job.emit
        docker = self.docker_info()
        if not docker.get("available"):
            emit(str(docker["error"]), "stderr")
            return 1
        current = self._container()
        if current and current["running"] and current["image"] == image and current["port"]:
            url = f"http://127.0.0.1:{current['port']}"
            emit(f"Hana is already running on {url}")
        else:
            emit(f"▶ Pulling the image {image} (about 1.8 GB the first time)")
            emit(f"$ docker pull {image}", "system")
            code = self._stream([self.docker, "pull", image], emit)
            if code != 0:
                emit(f"docker pull failed with exit code {code}", "stderr")
                return code
            self.runner([self.docker, "rm", "-f", CONTAINER], 60)
            port = _free_port()
            cmd = [self.docker, "run", "-d", "--name", CONTAINER, "--restart", "unless-stopped",
                   "-p", f"127.0.0.1:{port}:{CONTAINER_PORT}", "--label", "managed-by=pskit-studio", image]
            emit("▶ Starting the container")
            emit("$ " + " ".join(cmd), "system")
            proc = self.runner(cmd, 120)
            if proc.returncode != 0:
                emit((proc.stderr or proc.stdout or "docker run failed").strip(), "stderr")
                return proc.returncode or 1
            url = f"http://127.0.0.1:{port}"
        emit("▶ Loading the model")
        if not wait_ready(url, 300, lambda line: emit(line)):
            emit(f"the model did not answer within 5 minutes; check `docker logs {CONTAINER}`", "stderr")
            return 1
        self.save({"target": "local", "url": url, "image": image})
        emit(f"Hana is ready on {url}")
        return 0

    def install_server(self, job: Any, server: str, image: str) -> int:
        from ...core.onprem_servers import server_target
        from ...core.onprem_services import ServiceError, check_ssh_login, docker_argv

        emit = job.emit
        try:
            target = server_target(self.root, server)
            check_ssh_login(target)
        except (ServiceError, KeyError, ValueError) as exc:
            emit(str(exc), "stderr")
            return 1
        from ...core.onprem_services import _ensure_docker, _Runner

        emit(f"▶ Checking Docker on {server} (installed when missing)")
        try:
            _ensure_docker(target, _Runner(lambda line: emit(line), None), install=True)
        except (ServiceError, OSError) as exc:
            emit(f"Docker could not be installed on {server}: {exc}", "stderr")
            return 1
        remote_port = DEFAULT_PORT
        steps = [
            ("pull", ["pull", image]),
            ("remove the old container", ["rm", "-f", CONTAINER]),
            ("run", ["run", "-d", "--name", CONTAINER, "--restart", "unless-stopped",
                     "-p", f"127.0.0.1:{remote_port}:{CONTAINER_PORT}", "--label", "managed-by=pskit-studio", image]),
        ]
        for label, args in steps:
            emit(f"▶ {label.capitalize()} on {server}")
            emit(f"[{server}] docker {' '.join(args)}", "system")
            code = self._stream(docker_argv(target, args), emit)
            if code != 0 and label != "remove the old container":
                emit(f"docker {label} on {server} failed with exit code {code}", "stderr")
                return code
        cfg = {"target": "server", "server": server, "remote_port": remote_port, "image": image,
               "url": f"http://127.0.0.1:{_free_port(remote_port)}"}
        try:
            self.ensure_tunnel(cfg, restart=True)
        except StudioError as exc:
            emit(exc.message, "stderr")
            return 1
        emit(f"SSH tunnel: {cfg['url']} -> {server}:127.0.0.1:{remote_port}")
        emit("▶ Loading the model")
        if not wait_ready(str(cfg["url"]), 300, lambda line: emit(line)):
            emit(f"the model did not answer within 5 minutes; on {server}: `docker logs {CONTAINER}`", "stderr")
            return 1
        self.save(cfg)
        emit(f"Hana is ready on {server} (through {cfg['url']})")
        return 0

    def install_hf(self, job: Any, file: str, repo: str = HF_REPO) -> int:
        """The "Hugging Face" choice: llama-cpp-python (prebuilt CPU wheel) + the GGUF from the model repo, run in
        the studio process. The file is cached in ~/.cache/pskit/hana/ and a broken download resumes."""
        emit = job.emit
        if file not in [f["file"] for f in HF_FILES] or not re.match(r"^[\w.-]+/[\w.-]+$", repo):
            emit("unknown model file or repo", "stderr")
            return 1
        if importlib.util.find_spec("llama_cpp") is None:
            cmd = [sys.executable, "-m", "pip", "install", "--prefer-binary", "--extra-index-url", LLAMA_CPP_INDEX,
                   "llama-cpp-python"]
            emit("▶ Installing llama-cpp-python (one time)")
            emit("$ " + " ".join(cmd), "system")
            code = self._stream(cmd, emit)
            importlib.invalidate_caches()
            if code != 0 or importlib.util.find_spec("llama_cpp") is None:
                emit("installing llama-cpp-python failed; see the lines above. On Windows without a matching wheel "
                     "it needs a C++ compiler: use the Docker choice instead.", "stderr")
                return code or 1
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        path = MODELS_DIR / file
        if not path.is_file():
            url = f"https://huggingface.co/{repo}/resolve/main/{file}"
            size = next(f["size_gb"] for f in HF_FILES if f["file"] == file)
            emit(f"▶ Downloading {file} ({size} GB)")
            emit(url, "system")
            try:
                self._download(url, path, emit)
            except (OSError, URLError, HTTPError) as exc:
                emit(f"download failed: {exc} (start again to resume)", "stderr")
                return 1
        emit("▶ Loading the model")
        local = LocalModel(str(path))
        try:
            local._load()
        except ModelError as exc:
            emit(str(exc), "stderr")
            return 1
        with self._lock:
            self._local = local
        self.save({"target": "huggingface", "repo": repo, "file": file, "path": str(path)})
        emit(f"Hana is ready (in studio, from {path})")
        return 0

    @staticmethod
    def _download(url: str, path: Path, emit: Callable[..., None]) -> None:
        part = path.with_name(path.name + ".part")
        have = part.stat().st_size if part.exists() else 0
        req = Request(url, headers={"Range": f"bytes={have}-"} if have else {})  # noqa: S310 - fixed https URL
        with urlopen(req, timeout=60) as resp:  # noqa: S310 - fixed https URL
            total = have + int(resp.headers.get("content-length") or 0)
            if have and resp.status != 206:  # the server ignored the range: start over
                have = 0
                total = int(resp.headers.get("content-length") or 0)
            mode = "ab" if have else "wb"
            done, shown = have, -1
            with open(part, mode) as out:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    pct = int(done * 100 / total) if total else 0
                    if pct // 2 != shown:
                        shown = pct // 2
                        emit(f"  {done / 2**30:.2f} / {total / 2**30:.2f} GB ({pct}%)")
        if total and part.stat().st_size != total:
            raise OSError(f"incomplete download ({part.stat().st_size} of {total} bytes)")
        os.replace(part, path)

    def ensure_tunnel(self, cfg: Dict[str, Any], restart: bool = False) -> None:
        """For ``target: server``: keep ``ssh -N -L <local>:127.0.0.1:<remote>`` running while the studio runs."""
        if cfg.get("target") != "server":
            return
        from ...core.onprem_servers import server_target
        from ...core.onprem_services import ServiceError, tunnel_argv

        with self._lock:
            alive = self._tunnel is not None and self._tunnel.poll() is None
            if alive and not restart:
                return
            if self._tunnel is not None and self._tunnel.poll() is None:
                self._tunnel.terminate()
            local = int(str(cfg["url"]).rsplit(":", 1)[1])
            try:
                argv = tunnel_argv(server_target(self.root, str(cfg.get("server"))), local,
                                   int(cfg.get("remote_port") or DEFAULT_PORT))
            except (ServiceError, KeyError, ValueError) as exc:
                raise StudioError(400, f"can't open the SSH tunnel to {cfg.get('server')}: {exc}") from None
            try:
                self._tunnel = subprocess.Popen(  # noqa: S603 - fixed argv
                    argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except OSError as exc:
                raise StudioError(400, f"can't start ssh: {exc}") from None
            deadline = time.time() + 15
            while time.time() < deadline and _port_free(local):
                if self._tunnel.poll() is not None:
                    raise StudioError(400, f"the SSH tunnel to {cfg.get('server')} closed (check the server login)")
                time.sleep(0.3)

    def stop(self, remove_data: bool = False) -> Dict[str, Any]:
        """Stop Hana where she runs and forget the choice. ``remove_data``: also delete the image (Docker, here or
        on the server) or the downloaded model file (Hugging Face), so the space is freed."""
        cfg = self.config()
        image = str(cfg.get("image") or DEFAULT_IMAGE)
        removed: List[str] = []
        if cfg.get("target") == "local":
            self.runner([self.docker, "rm", "-f", CONTAINER], 60)
            removed.append(f"container {CONTAINER}")
            if remove_data and self.runner([self.docker, "image", "rm", image], 120).returncode == 0:
                removed.append(f"image {image}")
        elif cfg.get("target") == "server":
            from ...core.onprem_servers import server_target
            from ...core.onprem_services import ServiceError, docker_argv

            try:
                target = server_target(self.root, str(cfg.get("server")))
                self.runner(docker_argv(target, ["rm", "-f", CONTAINER]), 60)
                removed.append(f"container {CONTAINER} on {cfg.get('server')}")
                if remove_data and self.runner(docker_argv(target, ["image", "rm", image]), 120).returncode == 0:
                    removed.append(f"image {image} on {cfg.get('server')}")
            except (ServiceError, KeyError, ValueError, OSError, subprocess.TimeoutExpired):
                pass
        elif cfg.get("target") == "huggingface" and remove_data and cfg.get("path"):
            path = Path(str(cfg["path"]))
            if path.is_file() and MODELS_DIR in path.parents:  # only our own download
                path.unlink()
                removed.append(f"model file {path.name}")
        with self._lock:
            if self._tunnel is not None and self._tunnel.poll() is None:
                self._tunnel.terminate()
            self._tunnel = None
            self._local = None  # frees the in-studio model
        self.forget()
        return {**self.status(deep=False), "removed": removed}

    def close(self) -> None:
        with self._lock:
            if self._tunnel is not None and self._tunnel.poll() is None:
                self._tunnel.terminate()

    @staticmethod
    def _stream(cmd: List[str], emit: Callable[..., None]) -> int:
        try:
            proc = subprocess.Popen(  # noqa: S603 - fixed argv
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL
            )
        except OSError as exc:
            emit(str(exc), "stderr")
            return 127
        assert proc.stdout is not None
        last = ""
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip()
            if line and line != last:  # docker pull repeats progress lines
                emit(line)
            last = line
        return proc.wait()
