use serde_derive::{Deserialize, Serialize};
use std::cmp;
use std::collections::HashMap;

use crate::types;

///
/// This is a simple implementation of a (UTF-8) character language
/// that may be simpler (and faster) than using other tokenizers.
/// Character only encodings are probably a bad idea, but in the
/// domain of "research" it may be useful to understand how much
/// "leverage" the tokenization strategy alone is supplying. This
/// sort of comparison can probably be done by comparing with the
/// naive character encoding.
///
/// TODO: still incomplete

#[derive(Serialize, Deserialize)]
pub struct CharLanguage {
    size: types::TokenType,
    encoder: HashMap<char, types::TokenType>,
    decoder: HashMap<types::TokenType, char>,
}

impl CharLanguage {
    pub fn new() -> CharLanguage {
        return CharLanguage {
            size: 0,
            encoder: HashMap::new(),
            decoder: HashMap::new(),
        };
    }

    pub fn from_json(j: &String) -> Result<CharLanguage, serde_json::Error> {
        let mut C = CharLanguage {
            size: 0,
            encoder: serde_json::from_str(j)?, // just read in the encoder map
            decoder: HashMap::new(),
        };
        for (&c, &t) in &(C.encoder) {
            C.size = cmp::max(C.size, t); // TODO: assess contiguity?
            C.decoder.insert(t, c);
        }
        Ok(C)
    }

    pub fn json(&self) -> Result<String, serde_json::Error> {
        return Ok(serde_json::to_string(&self.encoder)?);
    }

    pub fn add(&mut self, c: char) {
        if !self.encoder.contains_key(&c) {
            self.size += 1; // adding a new token, increment
            self.encoder.insert(c, self.size);
            self.decoder.insert(self.size, c);
        }
    }

    pub fn add_tok(&mut self, c: char, t: types::TokenType) {
        // TODO: validity checks
        self.size = cmp::max(self.size, t);
        self.encoder.insert(c, t);
        self.decoder.insert(t, c);
    }

    pub fn add_str(&mut self, s: &String) {
        for c in s.chars() {
            self.add(c);
        }
    }

    pub fn encode(&self, s: &String) -> Result<Vec<types::TokenType>, String> {
        let mut encoded = Vec::<types::TokenType>::with_capacity(s.len()); // overestimate
        for c in s.chars() {
            match self.encoder.get(&c) {
                Some(&t) => encoded.push(t),
                _ => return Err("character not encodable".to_string()),
            }
        }
        Ok(encoded)
    }

    pub fn decode(&self, tokens: &Vec<types::TokenType>) -> Result<String, String> {
        let mut decoded = String::new(); // capacity?
        for t in tokens {
            match self.decoder.get(&t) {
                Some(&c) => decoded.push(c),
                _ => return Err("token not decodable".to_string()),
            }
        }
        Ok(decoded)
    }
}
