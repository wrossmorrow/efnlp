#![allow(dead_code)]
#![allow(non_snake_case)]

use rand::Rng;
use serde_derive::{Deserialize, Serialize};
use std::collections::HashMap;

use prost::Message;

use crate::compress;
use crate::errors;
use crate::types;

///
/// A simple uniform distribution sampler based on counts and totals.
///
/// Protobuf serialization is preferred.
///

#[derive(Serialize, Deserialize)]
pub struct Sampler {
    pub total: f64,
    pub counts: HashMap<types::TokenType, u32>,
}

impl Sampler {
    // create a new empty sampler
    pub fn new() -> Sampler {
        return Sampler {
            total: 0.0,
            counts: HashMap::new(),
        };
    }

    // create a sampler from proto
    pub fn from_proto(P: &types::pb::Sampler) -> Sampler {
        let mut S = Sampler::new();
        S.total = P.total as f64;
        for stc in P.counts.iter() {
            S.counts
                .insert(stc.token as types::TokenType, stc.count as u32);
        }
        return S;
    }

    // return this sampler as a protobuf Message
    pub fn proto(&self) -> types::pb::Sampler {
        let mut P = types::pb::Sampler {
            total: self.total as u32,
            counts: Vec::with_capacity(self.counts.len()),
        };
        for (&t, &c) in &(self.counts) {
            P.counts.push(types::pb::SamplerTokenCount {
                token: t as u32,
                count: c as u32,
            });
        }
        return P;
    }

    // serialize to protobuf bytes
    //
    // TODO: enable optional compression
    pub fn serialize(
        &self,
        compress: bool,
    ) -> Result<types::ProtoBytes, errors::SerializationError> {
        let P = self.proto();
        let mut buf = vec![]; // is this sizable?
        P.encode(&mut buf)?; // insufficient buffer capacity error only
        if compress {
            return Ok(compress::compress_bytes(&buf)?);
        }
        return Ok(buf);
    }

    // create a sampler from serialized proto
    pub fn deserialize(
        buf: &types::ProtoBytes,
        compressed: bool,
    ) -> Result<Sampler, errors::DeserializationError> {
        if compressed {
            let b = compress::decompress_bytes(buf)?;
            return Sampler::deserialize(&b, false);
        }
        let P: types::pb::Sampler = Message::decode(&buf[..])?;
        return Ok(Sampler::from_proto(&P));
    }

    // return this Sampler as a JSON string
    pub fn json(&self) -> Result<String, serde_json::Error> {
        return Ok(serde_json::to_string(self)?);
    }

    // approximate memory used by this sampler (one double,
    // plus a token and count for each element in the "support"
    // of this sampler's distribution).
    pub fn memory(&self) -> usize {
        if self.total == 0.0 {
            return 0;
        }
        return 8 + 6 * self.counts.len();
    }

    // add an observed element to this sampler
    pub fn add(&mut self, t: types::TokenType) {
        self.total += 1.0;
        match self.counts.get(&t) {
            Some(&count) => self.counts.insert(t, count + 1),
            _ => self.counts.insert(t, 1),
        };
    }

    // add an observed element and it's count to this sampler
    pub fn add_count(&mut self, t: types::TokenType, c: u32) {
        self.total += c as f64;
        let mut cc: u32 = 0;
        if self.counts.contains_key(&t) {
            cc = self.counts[&t];
        }
        self.counts.insert(t, cc + c);
    }

    // remove an observed element and it's count to this sampler; this could
    // in principle make a sampler invalid. We should implement a check that
    // removal is in fact valid.
    pub fn remove_count(&mut self, t: &types::TokenType, c: u32) {
        let cf = c as f64;
        // if self.total < cf {
        //     return Err(
        //         "removing count would make sampler invalid".to_string()
        //     );
        // }
        match self.counts.get(t) {
            Some(&cc) => {
                if cc >= c {
                    self.counts.insert(*t, cc - c);
                    self.total -= cf;
                }
                // TODO: what if cc < c? total < 0?
                // else {
                //     return Err(
                //         "removing count would make sampler invalid".to_string()
                //     );
                // }
            }
            _ => (),
        }
    }

    pub fn verify(&self) -> bool {
        let total = self.counts.iter().map(|(_, c)| *c).sum::<u32>() as f64;
        return total == self.total;
    }

    pub fn clean(&mut self) {
        self.counts.retain(|_, c| *c > 0);
    }

    pub fn is_empty(&self) -> bool {
        self.total == 0.0
    }

    // merge another sampler into this one (non-destructive)
    pub fn merge(&mut self, other: &Sampler) {
        for (&t, &c) in &(other.counts) {
            self.add_count(t, c);
        }
    }

    // remove all elements from another sampler; this could
    // in principle make a sampler invalid, but that condition
    // _could_ be dispatched to remove_count if we except that
    // the current sampler might be left in an inconsistent
    // state upon an error. We might be able to recover if we
    // track entries successfully removed up until failure.
    pub fn reduce(&mut self, other: &Sampler) {
        for (t, &c) in &(other.counts) {
            self.remove_count(t, c);
        }
    }

    // Sample from the distribution described by this sampler.
    // The implementation is a naive bin sampler.
    pub fn sample(&self) -> Result<types::TokenType, String> {
        if self.total <= 0.0 {
            return Err("sampler is empty; perhaps tree is sparse (call .densify())".to_string());
        }
        let mut fc: f64;
        let mut r: f64 = rand::thread_rng().gen_range(0.0..self.total);
        for (&t, &c) in &(self.counts) {
            fc = c as f64; // TODO: just store floats in memory?
            if r < fc {
                return Ok(t);
            }
            r -= fc;
        }
        Err("sampler malformed".to_string())
    }

    // return the probability of sampling a particular token
    pub fn probability(&self, t: types::TokenType) -> f64 {
        match self.counts.get(&t) {
            Some(&c) => {
                return (c as f64) / self.total;
            }
            _ => return 0.0,
        };
    }

    // we may want to "sample" using modal (or median?) values
    // pub fn mode(&self) -> types::TokenType {
    //     // determine/cache what the modal token is?
    //     return self.modal_token;
    // }
}

#[cfg(test)]
mod tests {

    use super::*;

    fn draw_arbitrary_token(tok_size: types::TokenType) -> types::TokenType {
        return rand::thread_rng().gen_range(0..tok_size);
    }

    fn create_arbitrary_token_sequence(
        tok_size: types::TokenType,
        size: usize,
    ) -> Vec<types::TokenType> {
        let mut seq = Vec::<types::TokenType>::with_capacity(size);
        for _ in 0..size {
            seq.push(draw_arbitrary_token(tok_size));
        }
        return seq;
    }

    fn assert_samplers_equal(r: &Sampler, s: &Sampler) {
        assert_eq!(r.total, s.total);
        for (t, &c) in &(r.counts) {
            assert!(s.counts.contains_key(t));
            assert!(s.counts[t] == c);
        }
        for (t, &c) in &(s.counts) {
            assert!(r.counts.contains_key(t));
            assert!(r.counts[t] == c);
        }
    }

    #[test]
    fn test_sampler() {
        let mut s = Sampler::new();

        for _ in 0..10 {
            s.add(draw_arbitrary_token(3));
        }

        match s.json() {
            Ok(j) => println!("JSON: {}", j),
            Err(e) => {
                println!("Error: {}", e);
                assert!(false);
            }
        }

        for _ in 1..10 {
            match s.sample() {
                Ok(t) => println!("Sampled: {}", t),
                Err(e) => {
                    println!("Error in sampling: {}", e);
                    assert!(false);
                }
            }
        }

        // serde

        let p = s.proto();
        let q1 = Sampler::from_proto(&p);
        assert_samplers_equal(&s, &q1);

        match s.serialize(false) {
            Ok(b) => match Sampler::deserialize(&b, false) {
                Ok(q2) => {
                    assert_samplers_equal(&s, &q2);
                }
                Err(e) => {
                    println!("Error in deserialize: {}", e);
                    assert!(false);
                }
            },
            Err(e) => {
                println!("Error in serialize: {}", e);
                assert!(false);
            }
        }
    }

    #[test]
    fn test_merge_samplers() {
        let mut s1 = Sampler::new();
        let mut s2 = Sampler::new();
        let mut s = Sampler::new();

        for _ in 0..10 {
            s1.add(draw_arbitrary_token(3));
            s2.add(draw_arbitrary_token(3));
        }

        s.merge(&s1);
        s.merge(&s2);

        assert_eq!(s.total, s1.total + s2.total);
        for (t, &c) in &(s1.counts) {
            assert!(s.counts[t] >= c);
        }
        for (t, &c) in &(s2.counts) {
            assert!(s.counts[t] >= c);
        }

        for _ in 1..10 {
            match s.sample() {
                Ok(t) => println!("Sampled: {}", t),
                Err(e) => println!("Error in sampling: {}", e),
            }
        }
    }
}
