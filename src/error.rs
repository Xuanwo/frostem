use std::fmt;

/// Error returned when an algorithm name cannot be resolved.
///
/// This is produced by [`Algorithm::from_name`](crate::Algorithm::from_name)
/// and [`Stemmer::try_from_name`](crate::Stemmer::try_from_name) when:
///
/// - the name is not a known Snowball algorithm id or alias, or
/// - it names an algorithm whose Cargo feature is **disabled** in this build
///   (so the variant is not compiled in).
///
/// # Example
///
/// ```
/// use frostem::Algorithm;
///
/// let err = Algorithm::from_name("not-a-lang").unwrap_err();
/// assert_eq!(err.name, "not-a-lang");
/// ```
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UnknownAlgorithm {
    /// The name that was requested (after trimming is applied by the lookup
    /// APIs, this is the trimmed form that failed to match).
    pub name: String,
}

impl fmt::Display for UnknownAlgorithm {
    /// Formats as `unknown or disabled snowball algorithm "…"`.
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "unknown or disabled snowball algorithm {:?}", self.name)
    }
}

impl std::error::Error for UnknownAlgorithm {}
