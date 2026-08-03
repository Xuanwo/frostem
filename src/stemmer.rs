use std::borrow::Cow;

use crate::algorithm::Algorithm;
use crate::dispatch::{stem_fn, StemFn};
use crate::SnowballEnv;

/// A stemmer for a single Snowball algorithm.
///
/// Input is expected to already be normalized the way the chosen algorithm
/// expects (for most European languages this means lowercase).
#[derive(Clone, Copy)]
pub struct Stemmer {
    algorithm: Algorithm,
    stemmer: StemFn,
}

impl Stemmer {
    /// Create a stemmer for `algorithm`.
    pub fn new(algorithm: Algorithm) -> Self {
        Self {
            algorithm,
            stemmer: stem_fn(algorithm),
        }
    }

    /// Create a stemmer from a language / algorithm name or alias.
    ///
    /// Accepts Snowball algorithm ids (`"english"`), ISO-ish aliases from
    /// upstream `modules.txt` (`"en"`, `"eng"`), case-insensitively.
    pub fn try_from_name(name: &str) -> Result<Self, crate::error::UnknownAlgorithm> {
        Ok(Self::new(Algorithm::from_name(name)?))
    }

    /// The algorithm this stemmer applies.
    pub fn algorithm(self) -> Algorithm {
        self.algorithm
    }

    /// Stem a single word.
    ///
    /// Returns [`Cow::Borrowed`] when the stem equals the input, otherwise an
    /// owned stemmed string.
    pub fn stem<'a>(&self, input: &'a str) -> Cow<'a, str> {
        let mut env = SnowballEnv::create(input);
        (self.stemmer)(&mut env);
        env.get_current()
    }
}

impl From<Algorithm> for Stemmer {
    fn from(algorithm: Algorithm) -> Self {
        Self::new(algorithm)
    }
}
