#!/usr/bin/env python3
"""Generate GitHub Release notes for a frostem release (stdout only).

Sections:
  - Summary (version, pin range, algorithms gate)
  - Snowball upstream commits / algorithms status
  - frostem commits since the previous tag

Not written into the repository; CI pipes this into `gh release create`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

SNOWBALL_COMPARE = "https://github.com/snowballstem/snowball/compare/{old}...{new}"
SNOWBALL_COMMIT = "https://github.com/snowballstem/snowball/commit/{sha}"
SNOWBALL_API_COMPARE = (
    "https://api.github.com/repos/snowballstem/snowball/compare/{old}...{new}"
)


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        text=True,
        capture_output=True,
    )


def short(sha: str | None, n: int = 12) -> str:
    if not sha:
        return "(none)"
    return sha[:n]


def git_log_oneline(
    cwd: Path, rev_range: str, *, max_count: int = 50
) -> list[str]:
    r = run(
        [
            "git",
            "log",
            "--oneline",
            f"--max-count={max_count}",
            "--no-decorate",
            rev_range,
        ],
        cwd=cwd,
        check=False,
    )
    if r.returncode != 0:
        return []
    return [line for line in r.stdout.splitlines() if line.strip()]


def ensure_commit(cwd: Path, commit: str) -> bool:
    if (
        run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=cwd,
            check=False,
        ).returncode
        == 0
    ):
        return True
    r = run(
        ["git", "fetch", "--depth", "1", "origin", commit],
        cwd=cwd,
        check=False,
    )
    return r.returncode == 0


def algorithms_changed(snowball_dir: Path, old: str | None, new: str) -> bool | None:
    """Return True/False, or None if the comparison could not be made."""
    if not old:
        return True
    if old == new:
        return False
    if not ensure_commit(snowball_dir, old) or not ensure_commit(snowball_dir, new):
        return None
    r = run(
        ["git", "diff", "--quiet", old, new, "--", "algorithms/"],
        cwd=snowball_dir,
        check=False,
    )
    if r.returncode == 0:
        return False
    if r.returncode == 1:
        return True
    return None


def algorithms_stat(snowball_dir: Path, old: str, new: str) -> str:
    r = run(
        ["git", "diff", "--stat", old, new, "--", "algorithms/"],
        cwd=snowball_dir,
        check=False,
    )
    return r.stdout.strip()


def snowball_commits_via_api(old: str, new: str, *, max_count: int = 50) -> list[str]:
    """Prefer GitHub compare API so shallow clones still get a full commit list."""
    url = SNOWBALL_API_COMPARE.format(old=old, new=new)
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "frostem-release-notes",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"warning: snowball compare API failed: {e}", file=sys.stderr)
        return []

    commits = data.get("commits") or []
    # API returns oldest→newest; show newest first like git log.
    lines: list[str] = []
    for c in reversed(commits[-max_count:]):
        sha = (c.get("sha") or "")[:12]
        msg = (c.get("commit") or {}).get("message") or ""
        subject = msg.splitlines()[0] if msg else ""
        if sha:
            lines.append(f"{sha} {subject}".rstrip())
    return lines


def snowball_commits(
    snowball_dir: Path, old: str | None, new: str, *, max_count: int = 50
) -> list[str]:
    if not old:
        return git_log_oneline(snowball_dir, new, max_count=max_count)
    if old == new:
        return []
    api_lines = snowball_commits_via_api(old, new, max_count=max_count)
    if api_lines:
        return api_lines
    if ensure_commit(snowball_dir, old) and ensure_commit(snowball_dir, new):
        return git_log_oneline(snowball_dir, f"{old}..{new}", max_count=max_count)
    return []


def frostem_commits(previous_tag: str | None, *, max_count: int = 50) -> list[str]:
    if previous_tag:
        # Inclusive of the release commit on HEAD; exclusive of the previous tag tip.
        return git_log_oneline(Path("."), f"{previous_tag}..HEAD", max_count=max_count)
    return git_log_oneline(Path("."), "HEAD", max_count=max_count)


def bump_kind(alg: bool | None, old_version: str | None, new_version: str) -> str:
    if old_version:
        try:
            om, omi, op = old_version.split(".")
            nm, nmi, np = new_version.split(".")
            if om != nm:
                return "major (frostem public API)"
            if omi != nmi:
                return "minor (upstream `algorithms/` change)"
            if op != np:
                return "patch (no `algorithms/` change, or version collision)"
        except ValueError:
            pass
    if alg is True:
        return "minor (upstream `algorithms/` change)"
    if alg is False:
        return "patch (no `algorithms/` change)"
    return "release"


def format_commit_bullets(lines: list[str], *, repo_commit_url: str | None) -> list[str]:
    out: list[str] = []
    for line in lines:
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            sha, subject = parts
            if repo_commit_url:
                out.append(f"- [`{sha}`]({repo_commit_url.format(sha=sha)}) {subject}")
            else:
                out.append(f"- `{sha}` {subject}")
        else:
            out.append(f"- {line}")
    return out


def build_notes(
    *,
    version: str,
    old_upstream: str | None,
    new_upstream: str,
    snowball_dir: Path,
    previous_tag: str | None,
    previous_version: str | None,
) -> str:
    alg = algorithms_changed(snowball_dir, old_upstream, new_upstream)
    kind = bump_kind(alg, previous_version, version)

    if alg is True:
        alg_label = "changed"
    elif alg is False:
        alg_label = "unchanged"
    else:
        alg_label = "unknown (could not compare)"

    lines: list[str] = [
        f"## frostem {version}",
        "",
        f"- **Bump**: {kind}",
        f"- **Snowball pin**: `{short(old_upstream)}` → `{short(new_upstream)}`",
        f"- **`algorithms/`**: {alg_label}",
        "",
        "## Snowball upstream",
        "",
    ]

    if not old_upstream:
        lines.append(f"Initial pin at [`{short(new_upstream)}`]({SNOWBALL_COMMIT.format(sha=new_upstream)}).")
        lines.append("")
    elif old_upstream == new_upstream:
        lines.append(
            f"No upstream commit movement (re-release of [`{short(new_upstream)}`]({SNOWBALL_COMMIT.format(sha=new_upstream)}))."
        )
        lines.append("")
    else:
        lines.append(
            f"Compare: [{short(old_upstream)}…{short(new_upstream)}]("
            f"{SNOWBALL_COMPARE.format(old=old_upstream, new=new_upstream)})."
        )
        lines.append("")

    sb_commits = snowball_commits(snowball_dir, old_upstream, new_upstream)
    if sb_commits:
        lines.append("### Commits")
        lines.append("")
        lines.extend(
            format_commit_bullets(
                sb_commits,
                repo_commit_url=SNOWBALL_COMMIT,
            )
        )
        lines.append("")
    elif old_upstream and old_upstream != new_upstream:
        lines.append("_No commit list available for this range._")
        lines.append("")

    lines.append("### `algorithms/`")
    lines.append("")
    if alg is False:
        lines.append("No changes under upstream `algorithms/` (stem definitions unchanged).")
    elif alg is True and old_upstream and old_upstream != new_upstream:
        stat = algorithms_stat(snowball_dir, old_upstream, new_upstream)
        if stat:
            lines.append("```")
            lines.append(stat)
            lines.append("```")
        else:
            lines.append("Upstream `algorithms/` changed (stat unavailable).")
    elif alg is True:
        lines.append("Treated as changed (no previous pin).")
    else:
        lines.append("Could not determine whether `algorithms/` changed.")
    lines.append("")

    lines.append("## frostem")
    lines.append("")
    if previous_tag:
        lines.append(f"Changes since `{previous_tag}`:")
    else:
        lines.append("Recent commits:")
    lines.append("")

    fr_commits = frostem_commits(previous_tag)
    if fr_commits:
        # Plain shas; the GitHub Release page is already scoped to this repository.
        lines.extend(format_commit_bullets(fr_commits, repo_commit_url=None))
    else:
        lines.append("_No frostem commits in range (content-only version rewrite)._")
    lines.append("")

    lines.append("## Install")
    lines.append("")
    lines.append("```toml")
    lines.append(f'frostem = "{version}"')
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--version", required=True, help="New frostem version (no v prefix)")
    p.add_argument(
        "--old-upstream",
        default="",
        help="Previous snowball pin commit (empty if none)",
    )
    p.add_argument("--new-upstream", required=True, help="New snowball pin commit")
    p.add_argument(
        "--snowball-dir",
        type=Path,
        default=Path(".snowball-src"),
        help="Path to snowball checkout",
    )
    p.add_argument(
        "--previous-tag",
        default="",
        help="Previous frostem git tag (e.g. v1.20260804.0); empty if none",
    )
    p.add_argument(
        "--previous-version",
        default="",
        help="Previous frostem version without v prefix (optional, for bump label)",
    )
    args = p.parse_args()

    old = args.old_upstream.strip() or None
    prev_tag = args.previous_tag.strip() or None
    prev_ver = args.previous_version.strip() or None
    if prev_tag and prev_tag.startswith("v") and not prev_ver:
        prev_ver = prev_tag[1:]

    if not args.snowball_dir.is_dir():
        print(f"error: snowball dir not found: {args.snowball_dir}", file=sys.stderr)
        return 1

    notes = build_notes(
        version=args.version,
        old_upstream=old,
        new_upstream=args.new_upstream,
        snowball_dir=args.snowball_dir,
        previous_tag=prev_tag,
        previous_version=prev_ver,
    )
    sys.stdout.write(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
