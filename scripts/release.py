#!/usr/bin/env python3
"""Build and optionally publish the Pixel Flight Simulator PortMaster port.

The default mode is safe: it downloads and builds the selected upstream
version into dist/ without changing tracked files or publishing anything.

Use --publish to update the vendored game files, commit and push those changes,
and create a GitHub release containing the PortMaster ZIP and its checksum.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.error
import urllib.request
import venv
import zipfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_REPO = "game-de-it/pixel-flight-simulator"
DEFAULT_RELEASE_REPO = "marianomd/pixel-flight-simulator-portmaster"
PYXEL_VERSION = "2.9.5"
PORT_NAME = "pixelflightsimulator"
PORT_ZIP = f"{PORT_NAME}.zip"
LAUNCHER = "Pixel Flight Simulator.sh"
USER_AGENT = "pixel-flight-simulator-portmaster-release-builder"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


class ReleaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class Upstream:
    ref: str
    version: str
    commit: str
    archive_url: str


@dataclass(frozen=True)
class BuiltGame:
    pyxapp: Path
    assets: Path
    game_license: Path
    assets_license: Path
    third_party_license: Path


def log(message: str) -> None:
    print(f"==> {message}", flush=True)


def remove_tree(path: Path) -> None:
    """Remove only a directory strictly contained by this repository."""
    resolved = path.resolve()
    root = ROOT.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ReleaseError(f"Refusing to remove path outside the repository: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)


def run(
    args: list[str],
    *,
    cwd: Path = ROOT,
    capture: bool = False,
    env: dict[str, str] | None = None,
) -> str:
    display = subprocess.list2cmdline(args) if os.name == "nt" else " ".join(args)
    log(display)
    result = subprocess.run(
        args,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=capture,
        env=env,
    )
    if result.returncode != 0:
        details = ""
        if capture:
            details = "\n" + (result.stdout or "") + (result.stderr or "")
        raise ReleaseError(f"Command failed ({result.returncode}): {display}{details}")
    return result.stdout.strip() if capture else ""


def api_json(path: str) -> dict | list:
    url = f"https://api.github.com/repos/{path}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def resolve_upstream(requested_ref: str) -> Upstream:
    if requested_ref == "latest":
        release = api_json(f"{UPSTREAM_REPO}/releases/latest")
        assert isinstance(release, dict)
        ref = str(release["tag_name"])
        archive_url = str(release["tarball_url"])
    else:
        ref = requested_ref
        encoded = urllib.parse.quote(ref, safe="")
        archive_url = f"https://api.github.com/repos/{UPSTREAM_REPO}/tarball/{encoded}"

    encoded = urllib.parse.quote(ref, safe="")
    commit_data = api_json(f"{UPSTREAM_REPO}/commits/{encoded}")
    assert isinstance(commit_data, dict)
    commit = str(commit_data["sha"])
    version = ref[1:] if ref.startswith("v") else ref
    return Upstream(ref=ref, version=version, commit=commit, archive_url=archive_url)


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def extract_archive(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    destination_root = destination.resolve()
    with tarfile.open(archive, "r:gz") as tf:
        members = tf.getmembers()
        for member in members:
            target = (destination / member.name).resolve()
            if target != destination_root and not target.is_relative_to(destination_root):
                raise ReleaseError(f"Unsafe path in upstream archive: {member.name}")
            if member.issym() or member.islnk():
                raise ReleaseError(f"Links are not allowed in upstream archive: {member.name}")
        try:
            tf.extractall(destination, members=members, filter="data")
        except TypeError:  # Python versions before extraction filters
            tf.extractall(destination, members=members)

    roots = [path for path in destination.iterdir() if path.is_dir()]
    if len(roots) != 1:
        raise ReleaseError("The upstream archive did not contain one root directory")
    return roots[0]


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def ensure_pyxel_venv() -> Path:
    venv_dir = ROOT / ".build" / f"pyxel-{PYXEL_VERSION}"
    python = venv_python(venv_dir)
    marker = venv_dir / ".pyxel-version"
    if python.is_file() and marker.is_file() and marker.read_text().strip() == PYXEL_VERSION:
        return python

    if venv_dir.exists():
        remove_tree(venv_dir)
    log(f"Creating isolated Pyxel {PYXEL_VERSION} build environment")
    venv.EnvBuilder(with_pip=True).create(venv_dir)
    python = venv_python(venv_dir)
    run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            f"pyxel=={PYXEL_VERSION}",
        ]
    )
    marker.write_text(PYXEL_VERSION + "\n", encoding="utf-8")
    return python


def build_upstream(source: Path, python: Path) -> BuiltGame:
    required = [
        source / "make_pyxapp.py",
        source / "LICENSE",
        source / "LICENSE-assets.md",
        source / "THIRD-PARTY.md",
    ]
    missing = [str(path.name) for path in required if not path.is_file()]
    if missing:
        raise ReleaseError(f"Upstream is missing required files: {', '.join(missing)}")

    build_env = os.environ.copy()
    build_env["PYTHONUTF8"] = "1"
    build_env["PYTHONIOENCODING"] = "utf-8"
    run([str(python), "make_pyxapp.py"], cwd=source, env=build_env)
    built = BuiltGame(
        pyxapp=source / "dist" / "pfs.pyxapp",
        assets=source / "dist" / "pfs_assets",
        game_license=source / "LICENSE",
        assets_license=source / "LICENSE-assets.md",
        third_party_license=source / "THIRD-PARTY.md",
    )
    if not built.pyxapp.is_file() or not built.assets.is_dir():
        raise ReleaseError("Upstream build did not produce pfs.pyxapp and pfs_assets/")
    normalize_pyxapp(built.pyxapp)
    return built


def normalize_pyxapp(path: Path) -> None:
    """Normalize timestamps and ordering so identical source gives identical output."""
    with zipfile.ZipFile(path) as source_zip:
        comment = source_zip.comment
        entries = {
            name: source_zip.read(name)
            for name in source_zip.namelist()
            if not name.endswith("/")
        }

    replacement = path.with_suffix(".normalized.pyxapp")
    with zipfile.ZipFile(
        replacement, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as output_zip:
        output_zip.comment = comment
        for name in sorted(entries, key=str.casefold):
            output_zip.writestr(zip_info(name), entries[name], compresslevel=9)
    replacement.replace(path)


def rendered_readme(upstream: Upstream) -> str:
    readme_path = ROOT / "README.md"
    text = readme_path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"Built from version [^\r\n]+, commit\r?\n`[0-9a-fA-F]{7,40}`\."
    )
    replacement = (
        f"Built from version {upstream.version}, commit\n`{upstream.commit}`."
    )
    updated, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise ReleaseError("Could not update the upstream version in README.md")
    return updated


def sync_worktree(game: BuiltGame, upstream: Upstream) -> None:
    source_snapshot = ROOT / "src" / "pfs"
    if source_snapshot.exists():
        remove_tree(source_snapshot)
    source_snapshot.mkdir(parents=True)
    source_root = source_snapshot.resolve()
    with zipfile.ZipFile(game.pyxapp) as app_zip:
        for name in app_zip.namelist():
            if not name.startswith("pfs/") or name.endswith("/"):
                continue
            relative = name.removeprefix("pfs/")
            if relative == ".pyxapp_startup_script":
                continue
            destination = (source_snapshot / relative).resolve()
            if not destination.is_relative_to(source_root):
                raise ReleaseError(f"Unsafe source path in pfs.pyxapp: {name}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(app_zip.read(name))

    gamedata = ROOT / PORT_NAME / "gamedata"
    if gamedata.exists():
        remove_tree(gamedata)
    gamedata.mkdir(parents=True)
    shutil.copy2(game.pyxapp, gamedata / "pfs.pyxapp")
    shutil.copytree(game.assets, gamedata / "pfs_assets")

    licenses = ROOT / PORT_NAME / "licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    shutil.copy2(game.game_license, licenses / "LICENSE.game.txt")
    shutil.copy2(game.assets_license, licenses / "LICENSE.assets.txt")
    shutil.copy2(game.third_party_license, licenses / "LICENSE.third-party.txt")
    (ROOT / "README.md").write_text(rendered_readme(upstream), encoding="utf-8", newline="\n")


def zip_info(name: str, executable: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    mode = 0o755 if executable else 0o644
    info.external_attr = (mode & 0xFFFF) << 16
    return info


def package_port(game: BuiltGame, upstream: Upstream, output: Path) -> None:
    entries: dict[str, bytes] = {}

    launcher = ROOT / LAUNCHER
    entries[LAUNCHER] = launcher.read_bytes()
    entries[f"{PORT_NAME}/gamedata/pfs.pyxapp"] = game.pyxapp.read_bytes()

    for source_file in sorted(path for path in game.assets.rglob("*") if path.is_file()):
        relative = source_file.relative_to(game.assets).as_posix()
        entries[f"{PORT_NAME}/gamedata/pfs_assets/{relative}"] = source_file.read_bytes()

    licenses = {
        "LICENSE.game.txt": game.game_license,
        "LICENSE.assets.txt": game.assets_license,
        "LICENSE.third-party.txt": game.third_party_license,
        "LICENSE.pyxel.txt": ROOT / PORT_NAME / "licenses" / "LICENSE.pyxel.txt",
    }
    for name, source_file in licenses.items():
        entries[f"{PORT_NAME}/licenses/{name}"] = source_file.read_bytes()

    port_data = json.loads((ROOT / "port.json").read_text(encoding="utf-8"))
    entries[f"{PORT_NAME}/port.json"] = json.dumps(port_data, indent=4).encode("utf-8")
    entries[f"{PORT_NAME}/gameinfo.xml"] = (ROOT / "gameinfo.xml").read_bytes()
    entries[f"{PORT_NAME}/screenshot.png"] = (ROOT / "screenshot.png").read_bytes()
    entries[f"{PORT_NAME}/{PORT_NAME}.md"] = rendered_readme(upstream).encode("utf-8")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in sorted(entries, key=str.casefold):
            executable = name == LAUNCHER
            zf.writestr(zip_info(name, executable), entries[name], compresslevel=9)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_package(package: Path, upstream: Upstream) -> None:
    required = {
        LAUNCHER,
        f"{PORT_NAME}/gamedata/pfs.pyxapp",
        f"{PORT_NAME}/port.json",
        f"{PORT_NAME}/gameinfo.xml",
        f"{PORT_NAME}/screenshot.png",
        f"{PORT_NAME}/{PORT_NAME}.md",
        f"{PORT_NAME}/licenses/LICENSE.game.txt",
        f"{PORT_NAME}/licenses/LICENSE.assets.txt",
        f"{PORT_NAME}/licenses/LICENSE.third-party.txt",
        f"{PORT_NAME}/licenses/LICENSE.pyxel.txt",
    }
    with zipfile.ZipFile(package) as port_zip:
        names = set(port_zip.namelist())
        missing = sorted(required - names)
        if missing:
            raise ReleaseError(f"Package is missing: {', '.join(missing)}")
        launcher = port_zip.read(LAUNCHER)
        if b"\r\n" in launcher:
            raise ReleaseError("The launcher has CRLF line endings")
        packaged_readme = port_zip.read(f"{PORT_NAME}/{PORT_NAME}.md").decode("utf-8")
        if upstream.commit not in packaged_readme:
            raise ReleaseError("The packaged README has the wrong upstream commit")

        app_bytes = port_zip.read(f"{PORT_NAME}/gamedata/pfs.pyxapp")
        with zipfile.ZipFile(io.BytesIO(app_bytes)) as app_zip:
            app_names = set(app_zip.namelist())
            if "pfs/.pyxapp_startup_script" not in app_names:
                raise ReleaseError("pfs.pyxapp has no startup marker")
            startup = app_zip.read("pfs/.pyxapp_startup_script").decode("utf-8")
            if startup.strip() != "main.py" or "pfs/main.py" not in app_names:
                raise ReleaseError("pfs.pyxapp does not start at pfs/main.py")


def write_release_files(dist: Path, upstream: Upstream, digest: str) -> tuple[Path, Path]:
    checksum_file = dist / f"{PORT_ZIP}.sha256"
    checksum_file.write_text(f"{digest}  {PORT_ZIP}\n", encoding="utf-8", newline="\n")

    notes_file = dist / "release-notes.md"
    notes_file.write_text(
        f"""Ready-to-run PortMaster package for Pixel Flight Simulator {upstream.version}.

Built from upstream tag `{upstream.ref}` at commit `{upstream.commit}`.

Installation:
1. Download `{PORT_ZIP}`.
2. Copy the ZIP **without extracting it** to PortMaster's `autoinstall` directory. On ArchR this is normally `/storage/roms/ports/PortMaster/autoinstall/`.
3. Start PortMaster and wait for the automatic installation to finish.
4. Restart or refresh EmulationStation, then open **Ports > Pixel Flight Simulator**.

The source code and game assets remain subject to their separate upstream licenses, both included in the package. Published with permission from game-de-it.

SHA-256: `{digest.upper()}`
""",
        encoding="utf-8",
        newline="\n",
    )
    return checksum_file, notes_file


def git_is_clean() -> bool:
    return not run(["git", "status", "--porcelain"], capture=True)


def infer_release_repo(explicit: str | None) -> str:
    if explicit:
        return explicit
    try:
        remote = run(["git", "remote", "get-url", "origin"], capture=True)
    except ReleaseError:
        return DEFAULT_RELEASE_REPO
    match = re.search(r"github\.com[/:]([^/]+/[^/]+?)(?:\.git)?$", remote)
    return match.group(1) if match else DEFAULT_RELEASE_REPO


def existing_release_tags(repo: str) -> list[str]:
    raw = run(
        ["gh", "release", "list", "--repo", repo, "--limit", "100", "--json", "tagName"],
        capture=True,
    )
    return [str(item["tagName"]) for item in json.loads(raw)]


def choose_release_tag(upstream: Upstream, tags: list[str], explicit: str | None) -> str:
    if explicit:
        if explicit in tags:
            raise ReleaseError(f"Release already exists: {explicit}")
        return explicit
    prefix = f"{upstream.ref}-portmaster."
    revisions = [
        int(tag[len(prefix) :])
        for tag in tags
        if tag.startswith(prefix) and tag[len(prefix) :].isdigit()
    ]
    return f"{prefix}{max(revisions, default=0) + 1}"


def publish(
    upstream: Upstream,
    game: BuiltGame,
    package: Path,
    checksum_file: Path,
    notes_file: Path,
    repo: str,
    explicit_tag: str | None,
) -> str:
    tags = existing_release_tags(repo)
    release_tag = choose_release_tag(upstream, tags, explicit_tag)
    existing_for_upstream = [tag for tag in tags if tag.startswith(f"{upstream.ref}-portmaster.")]

    sync_worktree(game, upstream)
    changed = not git_is_clean()
    if not changed and existing_for_upstream and explicit_tag is None:
        raise ReleaseError(
            f"{upstream.ref} is already published as {existing_for_upstream[0]}; "
            "use --release-tag only when intentionally republishing"
        )

    if changed:
        run(
            [
                "git",
                "add",
                "README.md",
                "src/pfs",
                f"{PORT_NAME}/gamedata",
                f"{PORT_NAME}/licenses",
            ]
        )
        run(["git", "commit", "-m", f"Update upstream to {upstream.ref}"])

    branch = run(["git", "branch", "--show-current"], capture=True)
    if not branch:
        raise ReleaseError("Cannot publish from a detached HEAD")
    run(["git", "push", "origin", branch])
    run(
        [
            "gh",
            "release",
            "create",
            release_tag,
            str(package),
            str(checksum_file),
            "--repo",
            repo,
            "--target",
            branch,
            "--title",
            f"Pixel Flight Simulator {upstream.version} - PortMaster",
            "--notes-file",
            str(notes_file),
        ]
    )
    return release_tag


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--upstream-ref",
        default="latest",
        help="Upstream tag, branch or commit (default: latest GitHub release)",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Update tracked game files, commit, push and create a GitHub release",
    )
    parser.add_argument(
        "--repo",
        help=f"Destination GitHub repository (default: infer origin or {DEFAULT_RELEASE_REPO})",
    )
    parser.add_argument(
        "--release-tag",
        help="Explicit destination release tag; normally generated automatically",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.chdir(ROOT)

    if args.release_tag and not args.publish:
        raise ReleaseError("--release-tag requires --publish")
    if args.publish and not git_is_clean():
        raise ReleaseError("Publishing requires a clean Git working tree")
    if args.publish:
        branch = run(["git", "branch", "--show-current"], capture=True)
        if branch != "main":
            raise ReleaseError(f"Publishing requires the main branch, currently on {branch!r}")

    upstream = resolve_upstream(args.upstream_ref)
    log(f"Upstream {upstream.ref} ({upstream.commit})")

    build_root = ROOT / ".build"
    build_root.mkdir(exist_ok=True)
    python = ensure_pyxel_venv()

    with tempfile.TemporaryDirectory(prefix="pfs-release-", dir=build_root) as temp_name:
        temp = Path(temp_name)
        archive = temp / "upstream.tar.gz"
        source_parent = temp / "source"
        log("Downloading upstream source archive")
        download(upstream.archive_url, archive)
        source = extract_archive(archive, source_parent)
        log("Building upstream pfs.pyxapp and external assets")
        game = build_upstream(source, python)

        dist = ROOT / "dist"
        if dist.exists():
            remove_tree(dist)
        dist.mkdir()
        package = dist / PORT_ZIP
        log("Building deterministic PortMaster package")
        package_port(game, upstream, package)
        validate_package(package, upstream)
        digest = sha256(package)
        checksum_file, notes_file = write_release_files(dist, upstream, digest)

        log(f"Created {package.relative_to(ROOT)}")
        print(f"SHA-256: {digest.upper()}")

        if args.publish:
            repo = infer_release_repo(args.repo)
            release_tag = publish(
                upstream,
                game,
                package,
                checksum_file,
                notes_file,
                repo,
                args.release_tag,
            )
            log(f"Published https://github.com/{repo}/releases/tag/{release_tag}")
        else:
            log("Preview build complete; nothing was committed or published")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReleaseError, OSError, urllib.error.URLError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
