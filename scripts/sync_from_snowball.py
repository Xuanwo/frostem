#!/usr/bin/env python3
"""Sync frostem sources from snowballstem/snowball main.

Generates:
  - src/among.rs, src/snowball_env.rs (runtime)
  - src/algorithms/*_stemmer.rs (all .sbl algorithms)
  - src/algorithms/mod.rs
  - src/dispatch.rs
  - Cargo.toml feature block (between AUTO-FEATURES markers)
  - upstream-pin.toml (commit provenance for CI; not a Rust API)

Version policy (shared by local runs and daily CI):
  major  — Rust facade API (left unchanged unless --major)
  minor  — UTC YYYYMMDD of the upstream commit when algorithms/ changed
           relative to upstream-pin.toml; otherwise keep previous minor
  patch  — 0 when algorithms/ changed; previous patch + 1 otherwise
  --major / --minor / --patch override the corresponding component when set
           (CI uses this for API breaks and tag/crates.io collisions)

Usage:
  scripts/sync_from_snowball.py [--snowball-dir DIR] [--major N] [--minor YYYYMMDD] [--patch N]
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNOWBALL_REPO = "https://github.com/snowballstem/snowball.git"

# Canonical algorithm names come from algorithms/*.sbl (full set, including curiosities).
# modules.txt supplies aliases for Algorithm::from_name.


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd, check=check, text=True, capture_output=False)


def to_pascal(algo: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in algo.split("_") if part)


def parse_modules_aliases(modules_txt: Path) -> dict[str, list[str]]:
    """Map algorithm name -> list of lookup aliases (lowercase)."""
    aliases: dict[str, list[str]] = {}
    if not modules_txt.is_file():
        return aliases
    for line in modules_txt.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        name = parts[0]
        # Third field is comma-separated names; remaining fields ignored for aliases.
        name_field = parts[2]
        names = [n.strip().lower() for n in name_field.split(",") if n.strip()]
        # Always include the algorithm id itself.
        if name.lower() not in names:
            names.insert(0, name.lower())
        aliases[name] = names
    return aliases


def discover_algorithms(snowball_dir: Path) -> list[str]:
    algos = sorted(p.stem for p in (snowball_dir / "algorithms").glob("*.sbl"))
    if not algos:
        raise SystemExit("no algorithms/*.sbl found in snowball tree")
    return algos


def git_head_metadata(snowball_dir: Path) -> tuple[str, str, str]:
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=snowball_dir, text=True
    ).strip()
    commit_time = subprocess.check_output(
        ["git", "log", "-1", "--format=%cI"], cwd=snowball_dir, text=True
    ).strip()
    # Prefer annotated/describe version when on a tag; otherwise unreleased/main.
    described = subprocess.check_output(
        ["git", "describe", "--tags", "--always", "--dirty"], cwd=snowball_dir, text=True
    ).strip()
    return commit, commit_time, described


def utc_yyyymmdd(commit_time: str) -> str:
    # Handle trailing Z
    ct = commit_time.replace("Z", "+00:00")
    dt = datetime.fromisoformat(ct)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%d")


def ensure_snowball(snowball_dir: Path | None) -> Path:
    if snowball_dir is not None:
        if not (snowball_dir / "algorithms").is_dir():
            raise SystemExit(f"invalid snowball dir: {snowball_dir}")
        run(["git", "fetch", "origin", "main"], cwd=snowball_dir, check=False)
        run(["git", "checkout", "main"], cwd=snowball_dir, check=False)
        run(["git", "pull", "--ff-only", "origin", "main"], cwd=snowball_dir, check=False)
        return snowball_dir

    cache = ROOT / ".snowball-src"
    if (cache / ".git").is_dir():
        run(["git", "fetch", "origin", "main"], cwd=cache)
        run(["git", "checkout", "main"], cwd=cache)
        run(["git", "reset", "--hard", "origin/main"], cwd=cache)
        return cache

    run(["git", "clone", "--depth", "1", SNOWBALL_REPO, str(cache)])
    return cache


def build_and_generate(snowball_dir: Path, algorithms: list[str]) -> None:
    run(["make", "snowball", f"-j{os.cpu_count() or 4}"], cwd=snowball_dir)
    out_dir = snowball_dir / "rust" / "src" / "snowball" / "algorithms"
    out_dir.mkdir(parents=True, exist_ok=True)
    snowball_bin = snowball_dir / "snowball"
    for algo in algorithms:
        sbl = snowball_dir / "algorithms" / f"{algo}.sbl"
        out = out_dir / f"{algo}_stemmer.rs"
        run([str(snowball_bin), str(sbl), "-rust", "-o", str(out)], cwd=snowball_dir)


def write_algorithms_mod(algorithms: list[str], dest: Path) -> None:
    lines = [
        "// @generated by scripts/sync_from_snowball.py — DO NOT EDIT",
        "",
    ]
    for algo in algorithms:
        lines.append(f'#[cfg(feature = "{algo}")]')
        lines.append(f"pub mod {algo}_stemmer;")
        lines.append("")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_dispatch(algorithms: list[str], dest: Path) -> None:
    lines = [
        "// @generated by scripts/sync_from_snowball.py — DO NOT EDIT",
        "",
        "use crate::algorithm::Algorithm;",
        "use crate::algorithms;",
        "use crate::SnowballEnv;",
        "",
        "pub(crate) type StemFn = fn(&mut SnowballEnv<'_>) -> bool;",
        "",
        "pub(crate) fn stem_fn(algorithm: Algorithm) -> StemFn {",
        "    match algorithm {",
    ]
    for algo in algorithms:
        variant = to_pascal(algo)
        lines.append(f'        #[cfg(feature = "{algo}")]')
        lines.append(
            f"        Algorithm::{variant} => algorithms::{algo}_stemmer::stem,"
        )
    lines.append("    }")
    lines.append("}")
    lines.append("")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_algorithm_enum(
    algorithms: list[str], aliases: dict[str, list[str]], dest: Path
) -> None:
    lines = [
        "// @generated by scripts/sync_from_snowball.py — DO NOT EDIT",
        "",
        "/// Snowball stemming algorithm.",
        "///",
        "/// Each variant corresponds to one upstream algorithm id (see",
        "/// [`Self::name`]) and is gated by a Cargo feature of the same",
        "/// snake_case name. With default features (`all`), every variant is",
        "/// available.",
        "///",
        "/// The enum is `#[non_exhaustive]` so newly added upstream algorithms",
        "/// are not a major-version break for downstream `match` expressions",
        "/// that keep a wildcard arm.",
        "///",
        "/// Algorithm behavior and documentation live on the",
        "/// [Snowball website](https://snowballstem.org/).",
        "///",
        "/// # Example",
        "///",
        "/// ```",
        "/// use frostem::{Algorithm, Stemmer};",
        "///",
        '/// let stemmer = Stemmer::new(Algorithm::English);',
        '/// assert_eq!(stemmer.algorithm().name(), "english");',
        "/// ```",
        "#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]",
        "#[non_exhaustive]",
        "pub enum Algorithm {",
    ]
    for algo in algorithms:
        variant = to_pascal(algo)
        lines.append(f"    /// `{algo}` Snowball stemmer.")
        lines.append("    ///")
        lines.append(
            f"    /// Enabled by the `{algo}` Cargo feature. "
            f'Canonical id: `"{algo}"`.'
        )
        lines.append(f'    #[cfg(feature = "{algo}")]')
        lines.append(f"    {variant},")
    lines.append("}")
    lines.append("")
    lines.append("impl Algorithm {")
    lines.append("    /// Returns the canonical Snowball algorithm id.")
    lines.append("    ///")
    lines.append("    /// This string is also the Cargo feature name that gates")
    lines.append("    /// the variant (for example `\"english\"`).")
    lines.append("    ///")
    lines.append("    /// # Example")
    lines.append("    ///")
    lines.append("    /// ```")
    lines.append("    /// use frostem::Algorithm;")
    lines.append("    ///")
    lines.append('    /// assert_eq!(Algorithm::English.name(), "english");')
    lines.append("    /// ```")
    lines.append("    pub const fn name(self) -> &'static str {")
    lines.append("        match self {")
    for algo in algorithms:
        variant = to_pascal(algo)
        lines.append(f'            #[cfg(feature = "{algo}")]')
        lines.append(f'            Self::{variant} => "{algo}",')
    lines.append("        }")
    lines.append("    }")
    lines.append("")
    lines.append("    /// All algorithms enabled in this build.")
    lines.append("    ///")
    lines.append("    /// Order is stable and sorted by canonical algorithm id.")
    lines.append("    /// Variants whose Cargo features are disabled are omitted.")
    lines.append("    ///")
    lines.append("    /// # Example")
    lines.append("    ///")
    lines.append("    /// ```")
    lines.append("    /// use frostem::Algorithm;")
    lines.append("    ///")
    lines.append("    /// assert!(!Algorithm::all().is_empty());")
    lines.append("    /// ```")
    lines.append("    pub fn all() -> &'static [Algorithm] {")
    lines.append("        &[")
    for algo in algorithms:
        variant = to_pascal(algo)
        lines.append(f'            #[cfg(feature = "{algo}")]')
        lines.append(f"            Self::{variant},")
    lines.append("        ]")
    lines.append("    }")
    lines.append("")
    lines.append("    /// Look up an algorithm by name or common alias.")
    lines.append("    ///")
    lines.append("    /// Accepts the canonical id from [`Self::name`] and aliases")
    lines.append("    /// from upstream `libstemmer/modules.txt` (for example")
    lines.append('    /// `"en"` / `"eng"` for English). Comparison is')
    lines.append("    /// case-insensitive after trimming whitespace.")
    lines.append("    ///")
    lines.append("    /// # Errors")
    lines.append("    ///")
    lines.append("    /// Returns [`UnknownAlgorithm`](crate::UnknownAlgorithm) if")
    lines.append("    /// the name is unknown or the matching algorithm's feature")
    lines.append("    /// is disabled in this build.")
    lines.append("    ///")
    lines.append("    /// # Example")
    lines.append("    ///")
    lines.append("    /// ```")
    lines.append("    /// use frostem::Algorithm;")
    lines.append("    ///")
    lines.append(
        '    /// assert_eq!(Algorithm::from_name("en").unwrap(), Algorithm::English);'
    )
    lines.append("    /// ```")
    lines.append(
        "    pub fn from_name(name: &str) -> Result<Self, crate::error::UnknownAlgorithm> {"
    )
    lines.append("        let key = name.trim();")
    lines.append("        let lower = key.to_ascii_lowercase();")
    lines.append("        match lower.as_str() {")

    # Build alias -> algo map; later entries do not override earlier for same alias
    # Prefer exact algorithm id mappings first.
    seen_alias: dict[str, str] = {}
    for algo in algorithms:
        for a in [algo.lower(), *aliases.get(algo, [])]:
            a = a.lower()
            if a not in seen_alias:
                seen_alias[a] = algo

    for alias in sorted(seen_alias.keys()):
        algo = seen_alias[alias]
        variant = to_pascal(algo)
        lines.append(f'            #[cfg(feature = "{algo}")]')
        lines.append(f'            "{alias}" => Ok(Self::{variant}),')

    lines.append(
        "            _ => Err(crate::error::UnknownAlgorithm { name: key.to_string() }),"
    )
    lines.append("        }")
    lines.append("    }")
    lines.append("}")
    lines.append("")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_cargo_toml(algorithms: list[str], version: str) -> None:
    cargo = ROOT / "Cargo.toml"
    text = cargo.read_text(encoding="utf-8")

    # version
    text2, n = re.subn(
        r'(?m)^version\s*=\s*"[^"]*"',
        f'version = "{version}"',
        text,
        count=1,
    )
    if n != 1:
        raise SystemExit("failed to rewrite package.version in Cargo.toml")
    text = text2

    feature_lines = ['default = ["all"]', "all = ["]
    for algo in algorithms:
        feature_lines.append(f'    "{algo}",')
    feature_lines.append("]")
    for algo in algorithms:
        feature_lines.append(f"{algo} = []")
    feature_block = "\n".join(feature_lines) + "\n"

    pattern = re.compile(
        r"(?ms)^# AUTO-FEATURES-BEGIN\n.*?^# AUTO-FEATURES-END\n"
    )
    replacement = f"# AUTO-FEATURES-BEGIN\n{feature_block}# AUTO-FEATURES-END\n"
    if not pattern.search(text):
        raise SystemExit("Cargo.toml missing AUTO-FEATURES markers")
    text = pattern.sub(replacement, text)
    cargo.write_text(text, encoding="utf-8")


def _demote_inner_doc_to_comment(text: str) -> str:
    """Turn leading `//!` lines into `//` so rustdoc ignores generated URLs."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    past_header = False
    for line in lines:
        if not past_header and line.startswith("//!"):
            out.append("//" + line[3:])
            continue
        past_header = True
        out.append(line)
    return "".join(out)


def copy_runtime(snowball_dir: Path) -> None:
    src = snowball_dir / "rust" / "src" / "snowball"
    shutil.copy2(src / "among.rs", ROOT / "src" / "among.rs")
    shutil.copy2(src / "snowball_env.rs", ROOT / "src" / "snowball_env.rs")

    alg_src = src / "algorithms"
    alg_dst = ROOT / "src" / "algorithms"
    alg_dst.mkdir(parents=True, exist_ok=True)
    # Remove old generated stemmers
    for old in alg_dst.glob("*_stemmer.rs"):
        old.unlink()
    for f in alg_src.glob("*_stemmer.rs"):
        text = f.read_text(encoding="utf-8")
        (alg_dst / f.name).write_text(_demote_inner_doc_to_comment(text), encoding="utf-8")

    # License from upstream
    copying = snowball_dir / "COPYING"
    if copying.is_file():
        shutil.copy2(copying, ROOT / "LICENSE-SNOWBALL")


def parse_current_version() -> tuple[int, str, int]:
    text = (ROOT / "Cargo.toml").read_text(encoding="utf-8")
    m = re.search(r'(?m)^version\s*=\s*"(\d+)\.(\d+)\.(\d+)"', text)
    if not m:
        return 1, "0", 0
    return int(m.group(1)), m.group(2), int(m.group(3))


def parse_pin_commit() -> str | None:
    pin = ROOT / "upstream-pin.toml"
    if not pin.is_file():
        return None
    m = re.search(r'(?m)^commit\s*=\s*"([^"]+)"', pin.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def git_commit_exists(snowball_dir: Path, commit: str) -> bool:
    r = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=snowball_dir,
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def ensure_commit_available(snowball_dir: Path, commit: str) -> bool:
    """Make sure `commit` is available in snowball_dir (shallow clones often lack it)."""
    if git_commit_exists(snowball_dir, commit):
        return True
    r = subprocess.run(
        ["git", "fetch", "--depth", "1", "origin", commit],
        cwd=snowball_dir,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print(
            f"warning: could not fetch {commit} for algorithms/ diff: {r.stderr.strip()}",
            flush=True,
        )
        return False
    return git_commit_exists(snowball_dir, commit)


def algorithms_changed(
    snowball_dir: Path, old_commit: str | None, new_commit: str
) -> bool:
    """True when upstream algorithms/ differs between pin and HEAD (or cannot tell)."""
    if not old_commit:
        print("No previous upstream pin; treating algorithms/ as changed", flush=True)
        return True
    if old_commit == new_commit:
        print(
            f"Upstream pin already at {new_commit}; algorithms/ unchanged for versioning",
            flush=True,
        )
        return False
    if not ensure_commit_available(snowball_dir, old_commit):
        print(
            "warning: treating algorithms/ as changed (conservative)",
            flush=True,
        )
        return True
    r = subprocess.run(
        ["git", "diff", "--quiet", old_commit, new_commit, "--", "algorithms/"],
        cwd=snowball_dir,
        capture_output=True,
        text=True,
    )
    if r.returncode == 0:
        print(
            f"Upstream algorithms/ unchanged ({old_commit[:12]} -> {new_commit[:12]})",
            flush=True,
        )
        return False
    if r.returncode == 1:
        print(
            f"Upstream algorithms/ changed ({old_commit[:12]} -> {new_commit[:12]})",
            flush=True,
        )
        stat = subprocess.run(
            ["git", "diff", "--stat", old_commit, new_commit, "--", "algorithms/"],
            cwd=snowball_dir,
            capture_output=True,
            text=True,
        )
        if stat.stdout.strip():
            print(stat.stdout.rstrip(), flush=True)
        return True
    print(
        f"warning: git diff failed ({r.stderr.strip()}); treating algorithms/ as changed",
        flush=True,
    )
    return True


def resolve_version(
    *,
    snowball_dir: Path,
    commit: str,
    commit_time: str,
    pin_commit: str | None,
    prev_major: int,
    prev_minor: str,
    prev_patch: int,
    major_override: int | None,
    minor_override: str | None,
    patch_override: int | None,
) -> tuple[int, str, int, bool]:
    """Return (major, minor, patch, algorithms_changed).

    Default bump uses the algorithms/ gate against the pre-sync pin. Explicit
    --major/--minor/--patch overrides replace only that component.
    """
    changed = algorithms_changed(snowball_dir, pin_commit, commit)
    commit_minor = utc_yyyymmdd(commit_time)

    major = major_override if major_override is not None else prev_major

    if minor_override is not None:
        if not re.fullmatch(r"\d{8}", minor_override):
            raise SystemExit(f"--minor must be YYYYMMDD, got {minor_override!r}")
        minor = minor_override
    elif changed:
        minor = commit_minor
    else:
        minor = prev_minor

    if patch_override is not None:
        patch = patch_override
    elif changed:
        patch = 0
    else:
        patch = prev_patch + 1

    return major, minor, patch, changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snowball-dir",
        type=Path,
        default=None,
        help="Existing snowball checkout (default: clone/update .snowball-src)",
    )
    parser.add_argument(
        "--major",
        type=int,
        default=None,
        help="Override major version (default: keep current Cargo.toml major)",
    )
    parser.add_argument(
        "--minor",
        type=str,
        default=None,
        help=(
            "Override minor version (default: algorithms/ gate — commit YYYYMMDD "
            "when algorithms changed, else previous minor)"
        ),
    )
    parser.add_argument(
        "--patch",
        type=int,
        default=None,
        help=(
            "Override patch number (default: algorithms/ gate — 0 when algorithms "
            "changed, else previous patch + 1)"
        ),
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip make/snowball generation; reuse existing generated files in tree",
    )
    args = parser.parse_args()

    # Capture pin + version before any rewrite so local and CI share one gate.
    pin_commit = parse_pin_commit()
    prev_major, prev_minor, prev_patch = parse_current_version()

    snowball_dir = ensure_snowball(args.snowball_dir)
    algorithms = discover_algorithms(snowball_dir)
    print(f"algorithms ({len(algorithms)}): {', '.join(algorithms)}")

    if not args.skip_build:
        build_and_generate(snowball_dir, algorithms)

    copy_runtime(snowball_dir)

    commit, commit_time, described = git_head_metadata(snowball_dir)
    major, minor, patch, alg_changed = resolve_version(
        snowball_dir=snowball_dir,
        commit=commit,
        commit_time=commit_time,
        pin_commit=pin_commit,
        prev_major=prev_major,
        prev_minor=prev_minor,
        prev_patch=prev_patch,
        major_override=args.major,
        minor_override=args.minor,
        patch_override=args.patch,
    )
    version = f"{major}.{minor}.{patch}"
    print(
        f"upstream {commit} @ {commit_time} -> version {version} "
        f"(algorithms_changed={alg_changed})",
        flush=True,
    )

    aliases = parse_modules_aliases(snowball_dir / "libstemmer" / "modules.txt")
    # Ensure lovins and any algo missing from modules still have self-alias.
    for algo in algorithms:
        aliases.setdefault(algo, [algo.lower()])

    write_algorithms_mod(algorithms, ROOT / "src" / "algorithms" / "mod.rs")
    write_dispatch(algorithms, ROOT / "src" / "dispatch.rs")
    write_algorithm_enum(algorithms, aliases, ROOT / "src" / "algorithm.rs")
    # Provenance is only in upstream-pin.toml (not a public Rust API).
    metadata_rs = ROOT / "src" / "metadata.rs"
    if metadata_rs.is_file():
        metadata_rs.unlink()
    update_cargo_toml(algorithms, version)

    # Pin file for CI / humans
    pin = ROOT / "upstream-pin.toml"
    pin.write_text(
        f'''# @generated by scripts/sync_from_snowball.py
commit = "{commit}"
commit_time = "{commit_time}"
describe = "{described}"
version = "{version}"
''',
        encoding="utf-8",
    )

    print("sync complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
