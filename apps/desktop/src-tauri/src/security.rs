use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use rand::{rngs::OsRng, RngCore};
use std::path::{Path, PathBuf};
use thiserror::Error;

#[cfg_attr(not(test), allow(dead_code))]
#[derive(Debug, Error, PartialEq, Eq)]
pub enum PathValidationError {
    #[error("the requested path does not exist")]
    Missing,
    #[error("the requested path is outside the allowed root")]
    OutsideAllowedRoot,
}

pub fn generate_session_token() -> String {
    let mut bytes = [0_u8; 32];
    OsRng.fill_bytes(&mut bytes);
    URL_SAFE_NO_PAD.encode(bytes)
}

#[cfg_attr(not(test), allow(dead_code))]
pub fn canonicalize_within(
    requested: impl AsRef<Path>,
    allowed_root: impl AsRef<Path>,
) -> Result<PathBuf, PathValidationError> {
    let root = allowed_root
        .as_ref()
        .canonicalize()
        .map_err(|_| PathValidationError::Missing)?;
    let path = requested
        .as_ref()
        .canonicalize()
        .map_err(|_| PathValidationError::Missing)?;

    if path.starts_with(&root) {
        Ok(path)
    } else {
        Err(PathValidationError::OutsideAllowedRoot)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn token_has_at_least_128_bits_of_entropy() {
        let first = generate_session_token();
        let second = generate_session_token();
        assert_ne!(first, second);
        assert!(first.len() >= 22);
    }

    #[test]
    fn rejects_paths_outside_the_allowed_root() {
        let allowed = tempfile::tempdir().expect("allowed tempdir");
        let outside = tempfile::tempdir().expect("outside tempdir");
        assert_eq!(
            canonicalize_within(outside.path(), allowed.path()),
            Err(PathValidationError::OutsideAllowedRoot)
        );
    }

    #[test]
    fn accepts_paths_inside_the_allowed_root() {
        let allowed = tempfile::tempdir().expect("allowed tempdir");
        let nested = allowed.path().join("course");
        std::fs::create_dir(&nested).expect("nested dir");
        assert_eq!(
            canonicalize_within(&nested, allowed.path()),
            Ok(nested.canonicalize().expect("canonical nested path"))
        );
    }
}
