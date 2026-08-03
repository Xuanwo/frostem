use std::fmt;

/// The requested stemming algorithm name was not recognized or is not enabled
/// in this build (Cargo feature disabled).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UnknownAlgorithm {
    pub name: String,
}

impl fmt::Display for UnknownAlgorithm {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "unknown or disabled snowball algorithm {:?}", self.name)
    }
}

impl std::error::Error for UnknownAlgorithm {}
