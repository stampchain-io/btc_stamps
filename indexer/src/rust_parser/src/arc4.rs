use log::debug;

/// A custom implementation of RC4 that exactly matches the behavior of the rust-crypto library
pub struct Rc4 {
    state: [u8; 256],
    i: u8,
    j: u8,
}

impl Rc4 {
    /// Initialize a new RC4 cipher with the given key
    pub fn new(key: &[u8]) -> Self {
        // Standard RC4 key scheduling algorithm (KSA)
        let mut state = [0u8; 256];
        for (i, val) in state.iter_mut().enumerate() {
            *val = i as u8;
        }

        let mut j: u8 = 0;
        for i in 0..256 {
            j = j.wrapping_add(state[i]).wrapping_add(key[i % key.len()]);
            state.swap(i, j as usize);
        }

        Rc4 { state, i: 0, j: 0 }
    }

    /// Process a chunk of data using the RC4 cipher
    pub fn process(&mut self, input: &[u8], output: &mut [u8]) {
        debug_assert_eq!(input.len(), output.len());

        for (src, dst) in input.iter().zip(output.iter_mut()) {
            // Update internal state
            self.i = self.i.wrapping_add(1);
            self.j = self.j.wrapping_add(self.state[self.i as usize]);
            self.state.swap(self.i as usize, self.j as usize);

            // XOR with generated keystream byte
            let k = self.state
                [(self.state[self.i as usize].wrapping_add(self.state[self.j as usize])) as usize];
            *dst = src ^ k;
        }
    }
}

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
