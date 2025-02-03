use lazy_static::lazy_static;
use std::collections::HashSet;

// Define the PREFIX constant to match the Python implementation
pub const PREFIX: &[u8] = b"stamp:";

// Define the BURNKEYS list to match the Python implementation
lazy_static! {
    pub static ref BURNKEYS: HashSet<&'static str> = {
        let mut keys = HashSet::new();
        keys.insert("022222222222222222222222222222222222222222222222222222222222222222");
        keys.insert("033333333333333333333333333333333333333333333333333333333333333333");
        keys.insert("020202020202020202020202020202020202020202020202020202020202020202");
        keys.insert("030303030303030303030303030303030303030303030303030303030303030302");
        keys.insert("030303030303030303030303030303030303030303030303030303030303030303");
        keys
    };
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_burnkeys_contains_expected_keys() {
        assert!(
            BURNKEYS.contains("022222222222222222222222222222222222222222222222222222222222222222")
        );
        assert!(
            BURNKEYS.contains("033333333333333333333333333333333333333333333333333333333333333333")
        );
        assert!(
            BURNKEYS.contains("020202020202020202020202020202020202020202020202020202020202020202")
        );
        assert!(
            BURNKEYS.contains("030303030303030303030303030303030303030303030303030303030303030302")
        );
        assert!(
            BURNKEYS.contains("030303030303030303030303030303030303030303030303030303030303030303")
        );
    }

    #[test]
    fn test_prefix_matches_expected() {
        assert_eq!(PREFIX, b"stamp:");
    }
}
