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
| **minor** | UTC date (`YYYYMMDD`) of the upstream commit that last changed `algorithms/` |
| **patch** | Releases with no `algorithms/` change (codegen/runtime-only upstream sync, frostem-only fixes, collisions) |

Example: `1.20260729.0` — facade API v1; last upstream **algorithm** change on 2026-07-29 UTC.

- API breaks are detected with [`cargo-semver-checks`](https://github.com/obi1kenobi/cargo-semver-checks) and bump **major**.
- Daily automation publishes whenever upstream `main` HEAD advances.
- **minor** advances only when upstream `algorithms/` differs from the previous pin (stem definitions / new or removed `.sbl` files). The minor number is that commit’s UTC `YYYYMMDD`.
- Upstream movement that does **not** touch `algorithms/` (compiler, runtime, docs, other backends, …) keeps the previous minor and bumps **patch**.
- Tag or crates.io version collisions also bump **patch**.

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
--major N            override major (default: keep current)
--minor YYYYMMDD     override minor (default: algorithms/ gate)
--patch N            override patch (default: algorithms/ gate)
```

`scripts/sync_from_snowball.py` applies the algorithms gate locally and in CI:
if upstream `algorithms/` changed vs `upstream-pin.toml`, minor becomes the
commit’s UTC `YYYYMMDD` and patch is `0`; otherwise minor is kept and patch
increments. Daily CI only adds major bumps from `cargo-semver-checks` and
extra patch bumps for tag/crates.io collisions.

CI runs a daily sync against `main`, and publishes to crates.io when the upstream commit changes, using [Trusted Publishing](https://crates.io/docs/trusted-publishing) (OIDC; no long-lived API token secret).

### Trusted Publishing

Publishing from CI uses [Trusted Publishing](https://crates.io/docs/trusted-publishing) (OIDC via `rust-lang/crates-io-auth-action`). No `CARGO_REGISTRY_TOKEN` secret is required for routine releases.

Configured for this repo as:

```bash
cargo install cargo-trustpub
cargo trustpub add --publisher github --owner Xuanwo --repo frostem --pipeline daily.yml
cargo trustpub status
```

(`daily.yml` must match `.github/workflows/daily.yml`. No GitHub Environment is used.)

After a successful CI publish, you may optionally require Trusted Publishing for all future versions:

```bash
cargo trustpub set --trustpub-only true
```

If you rename the workflow file or add a GitHub Environment, update the config with `cargo trustpub` (or the crates.io UI) so it matches exactly.

## License

BSD-3-Clause. Stemming algorithms and the Snowball runtime are from the
[Snowball project](https://github.com/snowballstem/snowball); see `LICENSE` and
`LICENSE-SNOWBALL`.
