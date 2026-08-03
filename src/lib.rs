//! Pre-built [Snowball](https://snowballstem.org/) stemmers for Rust.
//!
//! frostem tracks upstream `snowballstem/snowball` `main` and publishes
//! generated Rust stemmers behind a small, stable facade.
//!
//! # Versioning
//!
//! - **major** — frostem public Rust API
//! - **minor** — UTC date (`YYYYMMDD`) of the upstream commit this release
//!   was generated from
//! - **patch** — frostem-only fixes, or a same-day re-release
//!
//! Upstream provenance is exposed as [`SNOWBALL_COMMIT`] and related constants.
//!
//! # Features
//!
//! Every algorithm is an individual Cargo feature (same name as the Snowball
//! algorithm id). The default feature set is `all` (every algorithm).
//!
//! ```toml
//! # Only English + German:
//! frostem = { version = "1", default-features = false, features = ["english", "german"] }
//! ```
//!
//! # Example
//!
//! ```
//! use frostem::{Algorithm, Stemmer};
//!
//! let stemmer = Stemmer::new(Algorithm::English);
//! assert_eq!(stemmer.stem("fruitlessly"), "fruitless");
//! ```
//!
//! Inputs should already be lowercased when that is meaningful for the language.

// Generated stemmers and the upstream runtime refer to `snowball::…` paths.
// Map that name to this crate so we can keep generated sources unpatched.
extern crate self as snowball;

#[allow(dead_code)]
mod among;
#[allow(dead_code)]
mod snowball_env;

// Re-exports required by generated stemmers via `snowball::SnowballEnv` /
// `snowball::Among` and by the private dispatch layer.
pub(crate) use among::Among;
pub(crate) use snowball_env::SnowballEnv;

#[allow(
    dead_code,
    non_snake_case,
    non_upper_case_globals,
    unused_assignments,
    unused_mut,
    unused_parens,
    unused_variables
)]
pub(crate) mod algorithms;

mod algorithm;
mod dispatch;
mod error;
mod metadata;
mod stemmer;

pub use algorithm::Algorithm;
pub use error::UnknownAlgorithm;
pub use metadata::{SNOWBALL_ALGORITHMS, SNOWBALL_COMMIT, SNOWBALL_COMMIT_TIME, SNOWBALL_DESCRIBE};
pub use stemmer::Stemmer;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[cfg(feature = "english")]
    fn english_stem_basic() {
        let s = Stemmer::new(Algorithm::English);
        assert_eq!(s.stem("fruitlessly"), "fruitless");
        assert_eq!(s.stem("connections"), "connect");
        assert_eq!(s.stem("consign"), "consign");
    }

    #[test]
    #[cfg(feature = "english")]
    fn from_name_aliases() {
        assert_eq!(Algorithm::from_name("en").unwrap(), Algorithm::English);
        assert_eq!(Algorithm::from_name("ENG").unwrap(), Algorithm::English);
        assert_eq!(Algorithm::from_name("english").unwrap(), Algorithm::English);
        let s = Stemmer::try_from_name("en").unwrap();
        assert_eq!(s.algorithm(), Algorithm::English);
        assert_eq!(s.stem("running"), "run");
    }

    #[test]
    fn unknown_algorithm() {
        let err = Algorithm::from_name("not-a-lang").unwrap_err();
        assert_eq!(err.name, "not-a-lang");
    }

    #[test]
    fn metadata_is_populated() {
        assert_eq!(SNOWBALL_COMMIT.len(), 40);
        assert!(!SNOWBALL_COMMIT_TIME.is_empty());
        assert!(!SNOWBALL_DESCRIBE.is_empty());
        assert!(!SNOWBALL_ALGORITHMS.is_empty());
        assert!(SNOWBALL_ALGORITHMS.contains(&"english") || !cfg!(feature = "english"));
        // algorithms list always includes every generated id, independent of features
        assert!(SNOWBALL_ALGORITHMS.iter().any(|a| *a == "english"));
    }

    #[test]
    fn all_algorithms_non_empty_with_defaults() {
        // default features enable all
        assert!(!Algorithm::all().is_empty());
        for algo in Algorithm::all() {
            let stemmer = Stemmer::new(*algo);
            // smoke: stemming empty / short string must not panic
            let _ = stemmer.stem("");
            let _ = stemmer.stem("a");
            assert_eq!(stemmer.algorithm(), *algo);
            assert_eq!(Algorithm::from_name(algo.name()).unwrap(), *algo);
        }
    }

    #[test]
    #[cfg(feature = "german")]
    fn german_smoke() {
        let s = Stemmer::new(Algorithm::German);
        assert_eq!(s.stem("automaten"), "automat");
    }

    #[test]
    #[cfg(feature = "porter")]
    fn porter_distinct_from_english() {
        // Both exist; just ensure porter is selectable.
        let p = Stemmer::new(Algorithm::Porter);
        assert_eq!(p.algorithm().name(), "porter");
        let _ = p.stem("connection");
    }
}
