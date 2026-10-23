"""The public profile of the site: what may leave the tailnet, and a lint that enforces it.

The private site is a working space. The public build drops what is internal (the Questions
page, Inspect transcripts, lines marked `<!-- private -->`), replaces people's names with their
roles, and then fails if anything in the output still looks private: a name, an amount of money,
a local path, a hostname, an e-mail address or something shaped like a key.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Final

PRIVATE_MARK: Final = "<!-- private -->"
PUBLIC_NOTES: Final = ("pipeline", "protocol", "findings", "decisions")
ROLES: Final = (
    (re.compile(r"\bCatherine Ge-Wang\b"), "the mentor"),
    (re.compile(r"\bCath\b"), "the mentor"),
    (re.compile(r"\bJosh's\b"), "the author's"),
    (re.compile(r"\bJosh\b"), "the author"),
)
LINT: Final = (
    ("name", re.compile(r"\b(Josh|Cath|Catherine|Ge-Wang|Tuffy|jtuffy|Tom[aá]s)\b", re.IGNORECASE)),
    ("money", re.compile(r"[$€£]\s?\d")),
    ("windows path", re.compile(r"\b[A-Z]:\\\\?Users", re.IGNORECASE)),
    ("home path", re.compile(r"/(home|Users|sessions)/[a-z]")),
    ("hostname", re.compile(r"\.ts\.net\b|\btailnet\b|\blocalhost\b|127\.0\.0\.1")),
    ("e-mail", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")),
    ("key", re.compile(r"\bsk-[A-Za-z0-9_-]{12,}|\b(OPENAI|ANTHROPIC)_API_KEY\s*=")),
    ("third party", re.compile(r"\bRedwood\b")),
)


def scrub_text(text: str) -> str:
    """Drop private lines and swap names for roles."""
    kept = "\n".join(line for line in text.splitlines() if PRIVATE_MARK not in line)
    for pattern, role in ROLES:
        kept = pattern.sub(role, kept)
    return kept


def scrub(value: object) -> object:
    """`scrub_text` over every string in a JSON-like value."""
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    return value


def lint_text(text: str, where: str) -> list[str]:
    """Every private-looking match in `text`, as `where: kind: context`."""
    issues = []
    for kind, pattern in LINT:
        for match in pattern.finditer(text):
            start = max(0, match.start() - 40)
            context = text[start : match.end() + 40].replace("\n", " ")
            issues.append(f"{where}: {kind}: …{context}…")
    return issues


CODE_SUFFIXES: Final = frozenset({".js", ".css"})  # the viewer's own code, not content


def lint_site(out_dir: Path, *, skip: Iterable[str] = ("paper/main.pdf",)) -> list[str]:
    """Lint every content file of a built site (data, pages, figures), not the viewer's code."""
    skipped = set(skip)
    issues: list[str] = []
    for path in sorted(out_dir.rglob("*")):
        rel = path.relative_to(out_dir).as_posix()
        binary = path.suffix in {".pdf", ".png", ".woff2"}
        if not path.is_file() or rel in skipped or binary or path.suffix in CODE_SUFFIXES:
            continue
        issues += lint_text(path.read_text(encoding="utf-8", errors="replace"), rel)
    return issues


def publish(out_dir: Path, repo: str, *, push: bool, work_dir: Path) -> list[str]:
    """Copy a linted public build into a clone of the Pages repo; commit and push if `push`.

    Returns the git commands it ran (or would run, when not pushing). The Pages repo holds only
    the built site, so the research repo can stay private until the paper.
    """
    import base64  # noqa: PLC0415
    import os  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    # A token in GH_TOKEN is sent as a header for this command only, never written to disk.
    token = os.environ.get("GH_TOKEN")
    auth: list[str] = []
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        auth = ["-c", f"http.https://github.com/.extraheader=AUTHORIZATION: basic {basic}"]

    def git(*args: str, cwd: Path | None = None) -> None:
        subprocess.run(["git", *auth, *args], cwd=cwd, check=True)  # noqa: S603, S607

    steps = [
        f"git clone --depth 1 {repo} {work_dir}",
        f"replace {work_dir} contents with {out_dir} (+ .nojekyll)",
        "git add -A && git commit -m 'Publish site' && git push",
    ]
    if not push:
        return steps
    if work_dir.exists():
        shutil.rmtree(work_dir)
    git("clone", "--depth", "1", repo, str(work_dir))
    for child in work_dir.iterdir():
        if child.name != ".git":
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    shutil.copytree(out_dir, work_dir, dirs_exist_ok=True)
    (work_dir / ".nojekyll").write_text("", encoding="utf-8")
    git("add", "-A", cwd=work_dir)
    git("commit", "-m", "Publish site", "--allow-empty", cwd=work_dir)
    git("push", cwd=work_dir)
    return steps


def deploy_firebase(out_dir: Path, project: str, *, push: bool) -> list[str]:
    """Deploy a linted public build to Firebase Hosting (Google); needs `firebase login` once.

    Writes a minimal `firebase.json` beside the build and runs the Firebase CLI through npx, so
    nothing is installed into the repo. A Google Site can then embed the Hosting URL.
    """
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    config = out_dir.parent / "firebase.json"
    command = [
        "npx",
        "--yes",
        "firebase-tools",
        "deploy",
        "--only",
        "hosting",
        "--project",
        project,
    ]
    steps = [f"write {config} (hosting.public = {out_dir.name})", " ".join(command)]
    if not push:
        return steps
    config.write_text(
        json.dumps({"hosting": {"public": out_dir.name, "cleanUrls": True}}, indent=2) + "\n",
        encoding="utf-8",
    )
    npx = shutil.which("npx") or "npx"
    subprocess.run([npx, *command[1:]], cwd=out_dir.parent, check=True)  # noqa: S603
    return steps
