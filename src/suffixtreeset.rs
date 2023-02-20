#![allow(dead_code)]
#![allow(non_snake_case)]

use serde_derive::{Deserialize, Serialize};
use std::collections::HashMap;

use prost::Message;

use crate::compress;
use crate::errors;
use crate::sampler;
use crate::suffixtree;
use crate::types;

#[derive(Serialize, Deserialize)]
pub struct SuffixTreeSet {
    pub size: u32,
    pub depth: u16, // O(65k); u8 would be enough really
    pub sampler: sampler::Sampler,
    pub prefixes: HashMap<types::TokenType, suffixtree::SuffixTree>,
}

impl SuffixTreeSet {
    // new empty SuffixTree
    pub fn new() -> SuffixTreeSet {
        return SuffixTreeSet {
            size: 0,
            depth: 0,
            sampler: sampler::Sampler::new(),
            prefixes: HashMap::new(),
        };
    }

    // create a sampler from proto
    pub fn from_proto(P: &types::pb::SuffixTreeSet) -> SuffixTreeSet {
        let mut S = SuffixTreeSet::new();
        S.size = P.size as u32; // is it u32?
        S.depth = P.depth as u16;
        match &P.sampler {
            Some(s) => S.sampler = sampler::Sampler::from_proto(&s),
            _ => (),
        }
        for subtree_pb in P.prefixes.iter() {
            let subtree = suffixtree::SuffixTree::from_proto(subtree_pb);
            S.prefixes.insert(subtree.token, subtree);
        }
        return S;
    }

    // return this sampler as a protobuf Message
    pub fn proto(&self) -> types::pb::SuffixTreeSet {
        let mut P = types::pb::SuffixTreeSet {
            size: self.size as u32,
            depth: self.depth as u32,
            sampler: Some(self.sampler.proto()),
            prefixes: Vec::with_capacity(self.prefixes.len()),
        };
        for (_, subtree) in &(self.prefixes) {
            let subtree_pb = subtree.proto();
            P.prefixes.push(subtree_pb);
        }
        return P;
    }

    // serialize to protobuf bytes
    pub fn serialize(
        &self,
        compress: bool,
    ) -> Result<types::ProtoBytes, errors::SerializationError> {
        let P = self.proto();
        let mut buf = vec![];
        P.encode(&mut buf)?;
        if compress {
            return Ok(compress::compress_bytes(&buf)?);
        }
        return Ok(buf);
    }

    // create a sampler from serialized proto
    pub fn deserialize(
        buf: &types::ProtoBytes,
        compressed: bool,
    ) -> Result<SuffixTreeSet, errors::DeserializationError> {
        if compressed {
            let b = compress::decompress_bytes(buf)?;
            return SuffixTreeSet::deserialize(&b, false);
        }
        let P: types::pb::SuffixTreeSet = Message::decode(&buf[..])?;
        return Ok(SuffixTreeSet::from_proto(&P));
    }

    // return this Sampler as a JSON string
    pub fn json(&self) -> Result<String, serde_json::Error> {
        return Ok(serde_json::to_string(self)?);
    }

    pub fn memory(&self) -> usize {
        let m: usize = self
            .prefixes
            .iter()
            .map(|(_, tree)| tree.memory())
            .sum::<usize>();
        return self.sampler.memory() + m; // 4 + 2 +
    }

    pub fn parse(&mut self, p: &[types::TokenType], t: types::TokenType, dense: bool) {
        if p.len() == 0 {
            return; // no action, avoid complexities from returning errors
        }
        if dense {
            self.sampler.add(t);
        }
        let r = p.len() - 1;
        let l = p[r];
        let d: u16;
        match self.prefixes.get_mut(&l) {
            Some(tree) => {
                d = tree.parse(&p[0..r], t, dense);
            }
            _ => {
                let mut tree = suffixtree::SuffixTree::new(l);
                d = tree.parse(&p[0..r], t, dense);
                self.prefixes.insert(l, tree);
            }
        }
        if d + 1 > self.depth {
            self.depth = d + 1;
        }
    }

    pub fn parse_all(&mut self, s: &[types::TokenType], b: usize, dense: bool) {
        // can o/w error out if s.len() < b
        if s.len() < b {
            for i in 1..s.len() {
                self.parse(&s[0..i], s[i], dense);
            }
            return;
        }

        // use two loops to avoid a conditional in each iteration
        for i in 1..b {
            self.parse(&s[0..i], s[i], dense);
        }
        for i in b..s.len() - 1 {
            self.parse(&s[i - b..i], s[i], dense);
        }
    }

    pub fn densify(&mut self) {
        for (_, tree) in &mut (self.prefixes) {
            tree.densify();
            for (&t, &c) in &(tree.sampler.counts) {
                self.sampler.add_count(t, c);
            }
        }
    }

    pub fn sparsify(&mut self) {
        for (_, tree) in &mut (self.prefixes) {
            tree.sparsify();
        }
        self.sampler = sampler::Sampler::new(); // Correct?
    }

    pub fn occurrences(&self) -> usize {
        return self.prefixes.iter().map(|(_, tree)| tree.occurrences()).sum();
    }

    pub fn count_prefixes(&self) -> usize {
        return self
            .prefixes
            .iter()
            .map(|(_, tree)| tree.count_prefixes())
            .sum::<usize>();
    }

    pub fn count_patterns(&self) -> usize {
        return self
            .prefixes
            .iter()
            .map(|(_, tree)| tree.count_patterns())
            .sum::<usize>();
    }

    pub fn merge(&mut self, other: &mut SuffixTreeSet) {
        // NOTE: destructive to "other"

        if self.size < other.size {
            self.size = other.size;
        }
        if self.depth < other.depth {
            self.depth = other.depth;
        }
        self.sampler.merge(&other.sampler);

        // merge all prefixes

        // TODO: how to reserve well? Important?
        let mut shr_keys = Vec::<types::TokenType>::new();
        let mut new_keys = Vec::<types::TokenType>::new();
        for &t in other.prefixes.keys() {
            if self.prefixes.contains_key(&t) {
                shr_keys.push(t);
            } else {
                new_keys.push(t);
            }
        }

        for t in &shr_keys {
            match other.prefixes.remove(t) {
                // DESTRUCTIVE to other
                Some(mut new_tree) => match self.prefixes.remove(t) {
                    Some(mut old_tree) => {
                        old_tree.merge(&mut new_tree);
                        self.prefixes.insert(*t, old_tree);
                    }
                    None => (),
                },
                None => (), // Error?
            };
        }

        for t in &new_keys {
            match other.prefixes.remove(t) {
                // DESTRUCTIVE to other
                Some(new_tree) => self.prefixes.insert(*t, new_tree),
                None => None,
            };
        }
    }

    pub fn matches(&self, p: &[types::TokenType]) -> bool {
        if p.len() == 0 {
            return false;
        }
        let r = p.len() - 1; // r == 0 <==> p.len() == 1
        let l = p[r];
        match self.prefixes.get(&l) {
            Some(tree) => {
                if r == 0 {
                    return true;
                }
                return tree.matches(&p[0..r]);
            }
            _ => return false,
        };
    }

    pub fn match_length(&self, p: &[types::TokenType]) -> u32 {
        if p.len() == 0 {
            return 0;
        }
        let r = p.len() - 1;
        let l = p[r];
        match self.prefixes.get(&l) {
            Some(tree) => {
                return tree.match_length(&p[0..r]) + 1;
            }
            _ => return 0,
        };
    }

    // need error type response because technically sampler may error
    // we could ignore this if we can verify well-formedness of samplers
    //
    // TODO: Should we, optionally or otherwise, be stricter about prefixes
    // with unknown tokens? That is, not fall back to just sampling random
    // tokens based on a "uni-gram" model.
    pub fn sample(&self, p: &[types::TokenType]) -> Result<types::TokenType, String> {
        if p.len() == 0 {
            return Err("Sampling requires a (nontrivial) prefix".to_string());
        }
        let r = p.len() - 1;
        let l = p[r];
        match self.prefixes.get(&l) {
            Some(tree) => return Ok(tree.sample(&p[0..r])?),
            _ => return self.sampler.sample(), // sample from raw token occurrences
        }
    }

    // return the probability `t` follows `p`
    pub fn probability(&self, p: &[types::TokenType], t: types::TokenType) -> f64 {
        if p.len() == 0 {
            return self.sampler.probability(t);
        }
        let r = p.len() - 1;
        let l = p[r];
        match self.prefixes.get(&l) {
            Some(tree) => {
                // return non-zero probabilities; zero means "not found"
                // and we should fall back to raw token occurrences?
                let prob = tree.probability(&p[0..r], t);
                if prob > 0.0 {
                    return prob;
                }
            }
            _ => (),
        }
        return self.sampler.probability(t); // raw token occurrences
    }

    // Given a sequence p, compute the "perplexity" relative to this
    // model of the "text". That is,
    //
    //      lg PP = - 1/(|p|-B) sum_{i=B}^{|p|-1} lg q(p[i-B..i), p[i])
    //      q(•, •) == self.probability(•, •)
    //
    pub fn perplexity(&self, p: &[types::TokenType], block_size: usize) -> f64 {
        let mut lgsum: f64 = 0.0;
        let mut prob: f64;
        let cutoff = 10.0_f64.powf(-8.0_f64);
        for i in block_size..p.len() {
            prob = self.probability(&p[i - block_size..i], p[i]);
            if prob == 0.0 {
                prob = cutoff; // avoids "inf", but that's also a sign
            }
            lgsum += prob.log2();
        }
        lgsum = -lgsum / ((p.len() - block_size) as f64);
        return lgsum.powf(2.0);
    }

    pub fn generate(
        &self,
        size: usize,
        block_size: usize,
        prompt: &[types::TokenType],
    ) -> Result<Vec<types::TokenType>, String> {
        if prompt.len() == 0 {
            return Err("Cannot generate with an empty prompt.".to_string());
        }

        let total_size = prompt.len() + size;
        let mut gen = Vec::<types::TokenType>::with_capacity(total_size);

        for i in 0..prompt.len() {
            gen.push(prompt[i]);
        }
        if prompt.len() <= block_size {
            for i in prompt.len()..block_size {
                gen.push(self.sample(&gen[0..i])?);
            }
            for i in block_size..size {
                gen.push(self.sample(&gen[i - block_size..i])?);
            }
        } else {
            // if prompt.len() > block, start at prompt
            for i in prompt.len()..size {
                gen.push(self.sample(&gen[i - block_size..i])?);
            }
        }

        Ok(gen)
    }
}

#[cfg(test)]
mod tests {

    use super::*;
    use rand::Rng;
    use std::cmp;

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

    fn assert_samplers_equal(r: &sampler::Sampler, s: &sampler::Sampler) {
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

    fn assert_suffix_trees_equal(r: &suffixtree::SuffixTree, s: &suffixtree::SuffixTree) {
        assert_eq!(r.token, s.token);
        assert_eq!(r.depth, s.depth);
        assert_samplers_equal(&(r.sampler), &(s.sampler));
        for (t, tree) in &(r.prefixes) {
            assert!(s.prefixes.contains_key(&t));
            assert_suffix_trees_equal(&tree, &(s.prefixes[&t]));
        }
        for (t, tree) in &(s.prefixes) {
            assert!(r.prefixes.contains_key(&t));
            assert_suffix_trees_equal(&tree, &(r.prefixes[&t]));
        }
    }

    fn assert_suffix_tree_sets_equal(r: &SuffixTreeSet, s: &SuffixTreeSet) {
        assert_eq!(r.size, s.size);
        assert_eq!(r.depth, s.depth);
        assert_samplers_equal(&(r.sampler), &(s.sampler));
        for (t, tree) in &(r.prefixes) {
            assert!(s.prefixes.contains_key(&t));
            assert_suffix_trees_equal(&tree, &(s.prefixes[&t]));
        }
        for (t, tree) in &(s.prefixes) {
            assert!(r.prefixes.contains_key(&t));
            assert_suffix_trees_equal(&tree, &(r.prefixes[&t]));
        }
    }

    #[test]
    fn test_parser() {
        let tok_size: types::TokenType = 3;
        let num_tokens = 1000;
        let block_size = 10;

        let mut m = SuffixTreeSet::new();

        // match m.json() {
        //     Ok(j) => println!("JSON: {}", j),
        //     Err(e) => println!("Error: {}", e),
        // }

        let s = create_arbitrary_token_sequence(tok_size, num_tokens);

        m.parse_all(&s, block_size, true);

        // match m.json() {
        //     Ok(j) => println!("JSON: {}", j),
        //     Err(e) => println!("Error: {}", e),
        // }

        // assert every subsequence in the sequence is in the SuffixTreeSet
        for i in 1..block_size {
            assert!(m.matches(&s[0..i]));
        }
        for i in block_size..num_tokens - 1 {
            assert!(m.matches(&s[i - block_size..i]));
        }

        // verify we can generate
        let p: Vec<types::TokenType> = vec![0];
        match m.generate(100, block_size, &p) {
            Ok(gen) => println!("generated: {:?}", gen),
            Err(e) => println!("Error in generate: {}", e),
        }

        // serde

        let p = m.proto();
        let m1 = SuffixTreeSet::from_proto(&p);
        assert_suffix_tree_sets_equal(&m, &m1);

        match m.serialize(false) {
            Ok(b) => {
                println!("-- proto size in bytes: {}", b.len());
                match SuffixTreeSet::deserialize(&b, false) {
                    Ok(m2) => {
                        assert_suffix_tree_sets_equal(&m, &m2);
                    }
                    Err(e) => {
                        println!("Error in deserialize: {}", e);
                        assert!(false);
                    }
                }
            }
            Err(e) => {
                println!("Error in serialize: {}", e);
                assert!(false);
            }
        }

        m.sparsify();
        match m.serialize(false) {
            Ok(b) => {
                println!("-- sparse proto size in bytes: {}", b.len());
            }
            _ => (),
        }
        m.densify();
        match m.serialize(false) {
            Ok(b) => {
                println!("-- dense proto size in bytes: {}", b.len());
            }
            _ => (),
        }
    }

    #[test]
    fn test_merge_parsers() {
        let tok_size: types::TokenType = 3;
        let num_tokens = 100;
        let block_size = 3;

        let mut m1 = SuffixTreeSet::new();
        let mut m2 = SuffixTreeSet::new();
        let mut m = SuffixTreeSet::new();

        let s1 = create_arbitrary_token_sequence(tok_size, num_tokens);
        let s2 = create_arbitrary_token_sequence(tok_size, num_tokens);

        m1.parse_all(&s1, block_size, true);
        m2.parse_all(&s2, block_size, true);

        // assert "correctness" (TODO: still one-sided)

        for i in 1..block_size {
            assert!(m1.matches(&s1[0..i]));
        }
        for i in block_size..num_tokens - 1 {
            assert!(m1.matches(&s1[i - block_size..i]));
        }

        for i in 1..block_size {
            assert!(m2.matches(&s2[0..i]));
        }
        for i in block_size..num_tokens - 1 {
            assert!(m2.matches(&s2[i - block_size..i]));
        }

        m.merge(&mut m1);
        m.merge(&mut m2);

        // destructive action - moving resources
        assert_eq!(m1.prefixes.len(), 0);
        assert_eq!(m2.prefixes.len(), 0);

        assert_eq!(m.size, cmp::max(m1.size, m2.size));
        assert_eq!(m.depth, cmp::max(m1.depth, m2.depth));

        // assert "correctness" (TODO: still one-sided)

        for i in 1..block_size {
            assert!(m.matches(&s1[0..i]));
            assert!(m.matches(&s2[0..i]));
        }
        for i in block_size..num_tokens - 1 {
            assert!(m.matches(&s1[i - block_size..i]));
            assert!(m.matches(&s2[i - block_size..i]));
        }

        // verify we can generate
        let prompt: Vec<types::TokenType> = vec![0];
        match m.generate(100, block_size, &prompt) {
            Ok(gen) => println!("generated: {:?}", gen),
            Err(e) => println!("Error: {}", e),
        }
    }
}
