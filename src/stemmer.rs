use std::borrow::Cow;

use crate::algorithm::Algorithm;
use crate::dispatch::{stem_fn, StemFn};
use crate::SnowballEnv;

/// A stemmer bound to a single Snowball [`Algorithm`].
///
/// Construct with [`Stemmer::new`] or [`Stemmer::try_from_name`], then call
/// [`Stemmer::stem`] for each token. The stemmer is cheap to copy (`Copy`) and
/// may be shared across threads.
///
/// # Input normalization
///
/// Callers are responsible for any preprocessing the chosen algorithm expects.
/// For most Latin-script languages this means **already lowercased** Unicode
/// text; frostem does not case-fold for you.
///
/// # Example
///
/// ```
/// use frostem::{Algorithm, Stemmer};
///
/// let stemmer = Stemmer::new(Algorithm::English);
/// assert_eq!(stemmer.stem("fruitlessly"), "fruitless");
/// ```
#[derive(Clone, Copy)]
pub struct Stemmer {
    algorithm: Algorithm,
    stemmer: StemFn,
}

impl Stemmer {
    /// Create a stemmer that applies `algorithm`.
    ///
    /// The algorithm variant must be enabled in this build (its Cargo feature
    /// is on). With default features every algorithm is available.
    #[inline]
    pub fn new(algorithm: Algorithm) -> Self {
        Self {
            algorithm,
            stemmer: stem_fn(algorithm),
        }
    }

    /// Create a stemmer from a language or algorithm name.
    ///
    /// Accepts the canonical Snowball algorithm id (for example `"english"`)
    /// and the aliases listed in upstream `libstemmer/modules.txt` (for
    /// example `"en"`, `"eng"`). Matching is case-insensitive after trimming
    /// surrounding whitespace.
    ///
    /// # Errors
    ///
    /// Returns [`UnknownAlgorithm`](crate::UnknownAlgorithm) when the name is
    /// not recognized, or when it names an algorithm whose Cargo feature is
    /// disabled in this build.
    ///
    /// # Example
    ///
    /// ```
    /// use frostem::Stemmer;
    ///
    /// let stemmer = Stemmer::try_from_name("en").unwrap();
    /// assert_eq!(stemmer.stem("running"), "run");
    /// ```
    #[inline]
    pub fn try_from_name(name: &str) -> Result<Self, crate::error::UnknownAlgorithm> {
        Ok(Self::new(Algorithm::from_name(name)?))
    }

    /// Returns the [`Algorithm`] this stemmer applies.
    #[inline]
    pub fn algorithm(self) -> Algorithm {
        self.algorithm
    }

    /// Stem a single word.
    ///
    /// Returns [`Cow::Borrowed`] when the stem is identical to `input` (no
    /// allocation), otherwise [`Cow::Owned`] with the stemmed form.
    ///
    /// Empty strings and short tokens are accepted; behavior matches the
    /// upstream Snowball algorithm for the same input.
    #[inline]
    pub fn stem<'a>(&self, input: &'a str) -> Cow<'a, str> {
        let mut env = SnowballEnv::create(input);
        (self.stemmer)(&mut env);
        env.get_current()
    }
}

impl From<Algorithm> for Stemmer {
    /// Equivalent to [`Stemmer::new`].
    #[inline]
    fn from(algorithm: Algorithm) -> Self {
        Self::new(algorithm)
    }
}
