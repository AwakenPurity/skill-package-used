"""Import the four pinned upstream snapshots without running their code."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.request

ROOT = Path.cwd().resolve()

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

def download(url, destination):
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "skill-package-used-source-import"})
            with urllib.request.urlopen(request, timeout=120) as response:
                with destination.open("wb") as out:
                    shutil.copyfileobj(response, out)
            return
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)

def safe_extract(archive, destination):
    count = 0
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        prefixes = {PurePosixPath(m.name).parts[0] for m in members if m.name}
        if len(prefixes) != 1:
            raise RuntimeError("Archive must have one root")
        for member in members:
            parts = PurePosixPath(member.name).parts[1:]
            if not parts:
                continue
            if any(p in ("", ".", "..", ".git") for p in parts):
                raise RuntimeError("Unsafe archive path")
            relative = Path(*parts)
            target = destination / relative
            if not target.resolve().is_relative_to(destination.resolve()):
                raise RuntimeError("Path escaped destination")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if member.isfile():
                stream = tar.extractfile(member)
                if stream is None:
                    raise RuntimeError("Missing file data")
                with stream, target.open("wb") as out:
                    shutil.copyfileobj(stream, out)
                target.chmod(0o755 if member.mode & 0o111 else 0o644)
            elif member.issym():
                link = PurePosixPath(member.linkname)
                if link.is_absolute() or not (target.parent / member.linkname).resolve().is_relative_to(destination.resolve()):
                    raise RuntimeError("Unsafe symlink")
                target.symlink_to(member.linkname)
            else:
                raise RuntimeError("Unsupported archive entry: " + member.name)
            count += 1
    return count

def tree_hash(directory, mode_override=None):
    entries = []
    for item in directory.iterdir():
        if item.is_symlink():
            payload = os.readlink(item).encode()
            digest = hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).digest()
            mode = b"120000"
            sort_name = item.name.encode()
        elif item.is_dir():
            digest = bytes.fromhex(tree_hash(item, mode_override))
            mode = b"40000"
            sort_name = item.name.encode() + b"/"
        else:
            payload = item.read_bytes()
            digest = hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).digest()
            bits = mode_override(item) if mode_override else item.stat().st_mode
            mode = b"100755" if bits & stat.S_IXUSR else b"100644"
            sort_name = item.name.encode()
        entries.append((sort_name, mode + b" " + item.name.encode() + b"\0" + digest))
    payload = b"".join(data for _, data in sorted(entries))
    return hashlib.sha1(b"tree " + str(len(payload)).encode() + b"\0" + payload).hexdigest()

manifest = json.loads((ROOT / "skills.lock.json").read_text())
if manifest["strategy"] != "vendored-source-snapshots":
    raise RuntimeError("Expected snapshot manifest")

with tempfile.TemporaryDirectory(prefix="skill-import-") as temporary:
    temp = Path(temporary)
    for project in manifest["projects"]:
        name = project["name"]
        relative = project["path"]
        if relative != "skills/" + name or "/" in name or name.startswith("."):
            raise RuntimeError("Unexpected target")
        destination = ROOT / relative
        if not destination.resolve().is_relative_to(ROOT / "skills"):
            raise RuntimeError("Unsafe destination")
        old = git("ls-files", "--stage", "--", relative)
        if not old.startswith("160000 "):
            raise RuntimeError("Expected existing submodule: " + relative)
        source = project["url"].removeprefix("https://github.com/").removesuffix(".git")
        archive = temp / (name + ".tar.gz")
        download("https://codeload.github.com/" + source + "/tar.gz/" + project["commit"], archive)
        staging = temp / name
        staging.mkdir()
        count = safe_extract(archive, staging)
        actual_tree = tree_hash(staging)
        if actual_tree != project["source_tree"]:
            raise RuntimeError("Archive does not match upstream tree for " + name)
        git("rm", "--cached", "--", relative)
        if destination.exists():
            if destination.is_symlink() or any(destination.iterdir()):
                raise RuntimeError("Destination is not empty: " + relative)
            destination.rmdir()
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staging, destination, symlinks=True)
        git("add", "-f", "--", relative)
        indexed_tree = git("write-tree", "--prefix=" + relative + "/")
        if indexed_tree != project["source_tree"]:
            raise RuntimeError("Staged files differ from upstream tree for " + name)
        print(json.dumps({"project":name,"files":count,"tree":indexed_tree,"verified":True}))

git("rm", "--", ".gitmodules")
# Remove the one-time import machinery from the final repository.
git("rm", "--", ".github/workflows/vendor-skills.yml", ".github/vendor_import.py")
git("add", "--", "README.md", "skills.lock.json", "THIRD_PARTY_NOTICES.md", "docs/MAINTENANCE.md")
print("All four source snapshots verified; ready to commit.")
