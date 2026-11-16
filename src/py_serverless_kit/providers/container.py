"""Deployment size limits and container-image deploys, shared by every provider.

Every serverless platform caps how big a zip deployment may be (AWS Lambda: 50 MB zipped when uploaded
directly, 250 MB unzipped; Cloud Run functions: 100 MB compressed / 500 MB with modules; ...). Most of them
also run functions from a *container image* with a far higher limit (Lambda: 10 GB). This module holds the
provider-neutral pieces:

* :class:`PackageLimits` - what a provider allows, declared as ``Provider.package_limits``.
* :func:`plan_package` - after the build, decide ``zip`` or ``image`` (``package.type: zip | image | auto``)
  and produce the notes ``pskit package`` / ``deploy`` print (size against each limit, how to get past it).
* :class:`ImageBuild` + :func:`image_tag` - the image pskit builds from the bundle (``Dockerfile.pskit`` in
  the build directory, written by :mod:`py_serverless_kit.packaging.image`).
* :func:`docker_registry` / :func:`push_image` - the Terraform that builds the image with the local Docker
  daemon and pushes it (``kreuzwerker/docker``), so a provider only creates its registry (ECR, ACR, ...) and
  points its function at the returned digest-pinned image reference.

A provider supports images by setting ``image_registry`` (e.g. ``"Amazon ECR"``) and implementing
``image_dockerfile`` and the image branch of its render. Providers that will get it later set
``image_soon`` so users get a clear "coming soon" message instead of a silent zip.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .terraform_doc import TerraformDoc, ref

if TYPE_CHECKING:  # pragma: no cover
    from ..config.schema import ServiceConfig
    from .base import Artifact, Provider, RenderContext

MB = 1024 * 1024
GB = 1024 * MB
NEAR_LIMIT = 0.8  # warn from 80 % of a limit

DOCKER_PROVIDER = "docker"
DOCKER_SOURCE = "kreuzwerker/docker"
DOCKER_VERSION = ">= 3.0.2"
DOCKERFILE = "Dockerfile.pskit"
DOCKERIGNORE = ".dockerignore"


@dataclass(frozen=True)
class PackageLimits:
    """Deployment size limits of a platform, in bytes (``None`` = no documented limit)."""

    zip_compressed: Optional[int] = None
    zip_unpacked: Optional[int] = None
    image: Optional[int] = None
    reference: str = ""  # where the numbers come from, shown in notes


@dataclass
class ImageBuild:
    """The container image built from the bundle for this deploy."""

    tag: str
    platform: str
    dockerfile: str = DOCKERFILE  # inside the build context
    context: str = "build"  # relative to the work dir (.pskit/<provider>-<stage>)
    base_image: str = ""


@dataclass
class PackageNote:
    level: str  # "info" | "warning" | "error"
    message: str

    def __str__(self) -> str:
        return f"{'' if self.level == 'info' else self.level.upper() + ': '}{self.message}"


@dataclass
class PackagePlan:
    """How this deploy ships its code.

    ``functions`` maps every function to ``zip`` or ``image`` (``package.type`` / ``functions.<n>.package_type``
    with ``auto`` resolved). ``type`` sums it up: ``zip``, ``image`` or ``mixed``. ``too_big`` lists the zip
    functions that cannot deploy because the bundle is over a zip limit (with the reason).
    """

    type: str
    requested: str
    notes: List[PackageNote] = field(default_factory=list)
    functions: Dict[str, str] = field(default_factory=dict)
    too_big: Dict[str, str] = field(default_factory=dict)

    @property
    def errors(self) -> List[PackageNote]:
        return [n for n in self.notes if n.level == "error"]

    @property
    def needs_image(self) -> bool:
        return "image" in self.functions.values() or (not self.functions and self.type == "image")

    @property
    def needs_zip(self) -> bool:
        return "zip" in self.functions.values() or (not self.functions and self.type == "zip")

    def of(self, function: str) -> str:
        return self.functions.get(function, "image" if self.type == "image" else "zip")


def human(size: int) -> str:
    if size >= GB:
        return f"{size / GB:.1f} GB"
    if size >= MB:
        return f"{size / MB:.1f} MB"
    return f"{size / 1024:.1f} KiB"


def supports_image(provider: Provider) -> bool:
    return bool(provider.image_registry)


def platform_for(architecture: str) -> str:
    return "linux/arm64" if architecture == "arm64" else "linux/amd64"


def _exceeded(provider: Provider, config: ServiceConfig, artifact: Artifact) -> List[tuple]:
    """``(label, size, limit)`` for every zip limit the bundle is over, and those it is near."""
    compressed, unpacked = provider.zip_limits(config)
    found = []
    if compressed:
        found.append(("zipped", artifact.size, compressed))
    if unpacked and artifact.unpacked_size:
        found.append(("unzipped", artifact.unpacked_size, unpacked))
    return found


def package_summary(kinds: Dict[str, str]) -> str:
    found = set(kinds.values())
    return found.pop() if len(found) == 1 else ("mixed" if found else "zip")


def plan_package(provider: Provider, config: ServiceConfig, artifact: Artifact) -> PackagePlan:
    """Pick zip or image for every function and explain the bundle size against the provider's limits."""
    requested = config.package.type
    name = provider.display_name
    checks = _exceeded(provider, config, artifact)
    over = [(label, size, limit) for label, size, limit in checks if size > limit]
    near = [(label, size, limit) for label, size, limit in checks if limit * NEAR_LIMIT < size <= limit]
    can_image = supports_image(provider)
    limits = provider.package_limits

    asked = {fn_name: config.package_type_of(fn) for fn_name, fn in sorted(config.functions.items())}
    kinds = {
        fn_name: "image" if kind == "image" or (kind == "auto" and over and can_image) else "zip"
        for fn_name, kind in asked.items()
    }
    plan = PackagePlan(type=package_summary(kinds), requested=requested, functions=kinds)
    if not checks and not can_image and set(asked.values()) <= {"zip"}:
        return plan  # nothing to check here (e.g. on premises)

    sizes = f"bundle {human(artifact.size)} zipped"
    if artifact.unpacked_size:
        sizes += f", {human(artifact.unpacked_size)} unzipped"
    if checks:
        sizes += " (" + ", ".join(f"{label} limit {human(limit)}" for label, _s, limit in checks) + ")"
    plan.notes.append(PackageNote("info", f"{name}: {sizes}"))
    if artifact.skip_deps:
        plan.notes.append(PackageNote("info", "built with --skip-deps: the real bundle is larger once dependencies are installed"))

    images = sorted(n for n, k in kinds.items() if k == "image")
    zips = sorted(n for n, k in kinds.items() if k == "zip")
    if images:
        cap = f" (images up to {human(limits.image)})" if limits and limits.image else ""
        auto = [n for n in images if asked[n] == "auto"]
        why = f" ({', '.join(auto)}: auto, the bundle is over the zip limit)" if auto else ""
        who = "every function" if not zips else ", ".join(images)
        plan.notes.append(PackageNote("info", f"container image for {who}{why}: pushed to {provider.image_registry}"
                                              f"{cap}; needs a running Docker daemon"))
    if images and zips:
        plan.notes.append(PackageNote("info", f"zip for {', '.join(zips)}"))
    if not zips:
        return plan

    for label, size, limit in over:
        msg = f"the bundle is {human(size)} {label}, over {name}'s {human(limit)} limit{_ref(limits)}"
        for fn_name in zips:
            plan.too_big[fn_name] = f"{msg}; deploy it as an image (functions.{fn_name}.package_type: image)" \
                if can_image else msg
        who = "" if not images else f" for the zip functions ({', '.join(zips)})"
        plan.notes.append(PackageNote("error", f"{msg}{who}. {remedy(provider)}"))
    for label, size, limit in near:
        plan.notes.append(PackageNote("warning", f"the bundle is {human(size)} {label}, {size * 100 // limit}% of "
                                                 f"{name}'s {human(limit)} limit. {remedy(provider)}"))
    auto_zip = [n for n in zips if asked[n] == "auto"]
    if auto_zip and not over and can_image:
        plan.notes.append(PackageNote("info", f"package type auto ({', '.join(auto_zip)}): within the zip limits, "
                                              f"deploying a zip (switches to a {provider.image_registry} image when "
                                              "it is over)"))
    return plan


def _ref(limits: Optional[PackageLimits]) -> str:
    return f" ({limits.reference})" if limits and limits.reference else ""


def remedy(provider: Provider) -> str:
    """What to do about a bundle that is too big, for this provider."""
    if supports_image(provider):
        return (f"Deploy it as a container image in {provider.image_registry}: set `package.type: image` (or `auto`) "
                "in pskit.yml, `package_type: image` on the big functions only, or run with `--package-type image`. "
                "Smaller zips: `package.exclude` unused files.")
    soon = f" ({provider.image_soon})" if provider.image_soon else ""
    return (f"Container-image deploys on {provider.display_name} are coming soon{soon}; until then trim the bundle "
            "with `package.exclude` and fewer dependencies.")


def image_tag(artifact: Artifact, dockerfile: str) -> str:
    """A content tag: the same bundle and Dockerfile always give the same tag (no needless redeploys)."""
    return hashlib.sha256(f"{artifact.sha256}\n{dockerfile}".encode()).hexdigest()[:20]


# ------------------------------------------------------------------ terraform
def docker_registry(doc: TerraformDoc, address: str, username: str, password: str) -> None:
    """Add the Docker provider, logged in to the registry the image is pushed to."""
    doc.required_provider(DOCKER_PROVIDER, DOCKER_SOURCE, DOCKER_VERSION)
    doc.provider(DOCKER_PROVIDER, {"registry_auth": [{"address": address, "username": username, "password": password}]})


def push_image(doc: TerraformDoc, ctx: RenderContext, repository_url: str, label: str = "function") -> Dict[str, str]:
    """Build ``ctx.image`` from the build directory with the local Docker daemon and push it to ``repository_url``.

    Returns ``{"name": "<repo>:<tag>", "uri": "<repo>@sha256:...", "tag": ..., "resource": ...}``; ``uri`` pins the
    pushed digest so a function always runs exactly the image this deploy built.
    """
    image = ctx.image
    if image is None:  # pragma: no cover - providers call this only for image deploys
        raise ValueError("push_image needs ctx.image (package.type image)")
    name = f"{repository_url}:{image.tag}"
    build: Dict[str, Any] = {
        "context": "${abspath(path.module)}/" + image.context,
        "dockerfile": image.dockerfile,
        "platform": image.platform,
    }
    local = doc.resource(
        "docker_image",
        label,
        {"name": name, "keep_locally": False, "build": [build], "triggers": {"tag": image.tag}},
    )
    pushed = doc.resource(
        "docker_registry_image",
        label,
        {"name": ref(local, "name"), "keep_remotely": True, "triggers": {"tag": image.tag}},
    )
    return {
        "name": name,
        "uri": f"{repository_url}@" + ref(pushed, "sha256_digest"),
        "tag": image.tag,
        "resource": pushed,  # for depends_on where the image is referenced by tag
    }
