# frostem

Pre-built [Snowball](https://snowballstem.org/) stemmers for Rust.

frostem tracks upstream [`snowballstem/snowball`](https://github.com/snowballstem/snowball) **`main`** and publishes the generated Rust stemmers behind a small, stable facade. You do not need the Snowball compiler at build time.

## Install

```toml
[dependencies]
frostem = "1"
```

All algorithms are enabled by default. To shrink the dependency, disable defaults and pick languages:

```toml
[dependencies]
frostem = { version = "1", default-features = false, features = ["english", "german"] }
```

## Usage

```rust
use frostem::{Algorithm, Stemmer};

fn main() {
    let stemmer = Stemmer::new(Algorithm::English);
    assert_eq!(stemmer.stem("fruitlessly"), "fruitless");

    // Names and aliases from Snowball modules.txt (case-insensitive)
    let de = Stemmer::try_from_name("de").unwrap();
    assert_eq!(de.stem("automaten"), "automat");
}
```

Inputs should already be lowercased when that is meaningful for the language.

Upstream provenance (git commit / time) is recorded in `upstream-pin.toml` in
this repository, not exposed as Rust API. Consumers should rely on the crate
**version** (`major.YYYYMMDD.patch`).

## Versioning

| Component | Meaning |
|-----------|---------|
| **major** | frostem public Rust API |
| **minor** | UTC date (`YYYYMMDD`) of the upstream commit used for generation |
| **patch** | frostem-only changes, or a same-day re-release |

Example: `1.20260729.0` — facade API v1, generated from an upstream commit on 2026-07-29 UTC.

- API breaks are detected with [`cargo-semver-checks`](https://github.com/obi1kenobi/cargo-semver-checks) and bump **major**.
- Upstream `main` movement bumps **minor** to that commit’s UTC date (daily automation; always publishes when HEAD advanced).
- Same calendar day re-releases use **patch** (strategy A).

`Algorithm` is `#[non_exhaustive]`: new upstream languages are a minor change, not a major break.

## Algorithms

Every Snowball algorithm under `algorithms/*.sbl` is included (including curiosities such as `lovins`). Feature names match the algorithm ids (e.g. `english`, `dutch_porter`, `earlymodernenglish`).

Use `Algorithm::all()` for the set enabled in a given build.

## Maintenance

Regenerate from upstream (requires a C toolchain and `make`):

```bash
python3 scripts/sync_from_snowball.py
cargo test
```

Options:

```text
--snowball-dir DIR   use an existing checkout instead of .snowball-src
--major N            set major (default: keep current)
--patch N            set patch (default: 0)
```

CI runs a daily sync against `main`, and publishes to crates.io when the upstream commit changes, using [Trusted Publishing](https://crates.io/docs/trusted-publishing) (OIDC; no long-lived API token secret).

### Trusted Publishing

Bootstrap (one-time, on a maintainer machine):

1. Publish the first version manually (Trusted Publishing only applies after the crate exists):

   ```bash
   cargo publish
   ```

2. On crates.io → crate **frostem** → **Settings** → **Trusted Publishing** → **Add** → **GitHub**:

   | Field | Value |
   |-------|--------|
   | Repository owner | `Xuanwo` |
   | Repository name | `frostem` |
   | Workflow filename | `daily.yml` |
   | Environment | *(leave empty — this repo does not use a GitHub Environment)* |

3. Optionally enable “Require trusted publishing for all new versions” after the first CI publish succeeds.

The daily workflow requests a short-lived token with `rust-lang/crates-io-auth-action` (`permissions.id-token: write`). Do **not** set a `CARGO_REGISTRY_TOKEN` repository secret for routine releases.

If you rename the workflow file or add a GitHub Environment, update the Trusted Publisher entry on crates.io to match exactly.

## License

BSD-3-Clause. Stemming algorithms and the Snowball runtime are from the
[Snowball project](https://github.com/snowballstem/snowball); see `LICENSE` and
`LICENSE-SNOWBALL`.
