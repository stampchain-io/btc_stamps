use crypto::rc4::Rc4;
use crypto::symmetriccipher::SynchronousStreamCipher;
use log::debug;

/// Initialize an ARC4 cipher with the given seed
pub fn init_arc4(seed: &[u8]) -> Rc4 {
    debug!(
        "Initializing ARC4 cipher with seed of length {}",
        seed.len()
    );
    Rc4::new(seed)
}

/// Decrypt a chunk of ciphertext using the provided key
pub fn arc4_decrypt_chunk(ciphertext: &[u8], key: &mut Rc4) -> Vec<u8> {
    debug!("Decrypting chunk of length {}", ciphertext.len());
    let mut result = vec![0; ciphertext.len()];
    key.process(ciphertext, &mut result);
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_arc4_decryption() {
        // Simple test case
        let seed = b"test_seed";
        let ciphertext = hex::decode("deadbeef").unwrap();

        let mut cipher = init_arc4(seed);
        let decrypted = arc4_decrypt_chunk(&ciphertext, &mut cipher);

        // Just verify we get some output of the right length
        assert_eq!(decrypted.len(), ciphertext.len());
    }
}
