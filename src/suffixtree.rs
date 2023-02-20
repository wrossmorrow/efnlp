#![allow(dead_code)]
#![allow(non_snake_case)]

use serde_derive::{Deserialize, Serialize};
use std::collections::HashMap;

use prost::Message;

use crate::compress;
use crate::errors;
use crate::sampler;
use crate::types;

///
/// A basic suffix tree like sampler data structure. We store (un-
/// compressed) suffixes that can be recursively searched, with
/// samplers either at every level ("dense") or just at leaves
/// ("sparse"). The difference could be very relevant for serialization
/// because a "sparse" structure can have half the size of a "dense"
/// structure, a "dense" structure is only needed for efficient
/// sampling, and it is easy to "densify" by accumulating up from
/// leaves.
///
/// Protobuf serialization is preferred.
///

#[derive(Serialize, Deserialize)]
pub struct SuffixTree {
    pub token: types::TokenType,
    pub depth: u16, // O(65k); u8 would be enough really
    pub sampler: sampler::Sampler,
    pub prefixes: HashMap<types::TokenType, SuffixTree>,
}

impl SuffixTree {
    // new empty SuffixTree
    pub fn new(t: types::TokenType) -> SuffixTree {
        return SuffixTree {
            token: t,
            depth: 0,
            sampler: sampler::Sampler::new(),
            prefixes: HashMap::new(),
        };
    }

    // create a sampler from proto
    pub fn from_proto(P: &types::pb::SuffixTree) -> SuffixTree {
        let mut S = SuffixTree::new(P.token as types::TokenType);
        S.depth = P.depth as u16;
        match &P.sampler {
            Some(s) => S.sampler = sampler::Sampler::from_proto(&s),
            _ => (),
        }
        for subtree_pb in P.prefixes.iter() {
            let subtree = SuffixTree::from_proto(subtree_pb);
            S.prefixes.insert(subtree.token, subtree);
        }
        return S;
    }

    // return this sampler as a protobuf Message
    pub fn proto(&self) -> types::pb::SuffixTree {
        let mut P = types::pb::SuffixTree {
            token: self.token as u32,
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
    ) -> Result<SuffixTree, errors::DeserializationError> {
        if compressed {
            let b = compress::decompress_bytes(buf)?;
            return SuffixTree::deserialize(&b, false);
        }
        let P: types::pb::SuffixTree = Message::decode(&buf[..])?;
        return Ok(SuffixTree::from_proto(&P));
    }

    // return this Sampler as a JSON string
    pub fn json(&self) -> Result<String, serde_json::Error> {
        return Ok(serde_json::to_string(self)?);
    }

    // return a memory estimate: basically recursive size plus
    pub fn memory(&self) -> usize {
        let m: usize = self
            .prefixes
            .iter()
            .map(|(_, tree)| tree.memory()) // 2 +
            .sum::<usize>();
        return 2 + self.sampler.memory() + m; // 4 +
    }

    pub fn occurrences(&self) -> usize {
        if self.prefixes.len() == 0 {
            return self.sampler.total as usize;
        }
        return self.prefixes.iter().map(|(_, tree)| tree.occurrences()).sum();
    }

    // Parse a prefix p, assigning an occurrence of a token t
    // in it's sampler. Recursively traverse sub-suffixes,
    // creating new nodes as needed. If "dense" is true,
    // define the sampler for any nodes, o/w just for leaves.
    pub fn parse(&mut self, p: &[types::TokenType], t: types::TokenType, dense: bool) -> u16 {
        if p.len() == 0 {
            self.sampler.add(t);
            return self.depth;
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
                let mut tree = SuffixTree::new(l);
                d = tree.parse(&p[0..r], t, dense);
                self.prefixes.insert(l, tree);
            }
        }
        if d + 1 > self.depth {
            self.depth = d + 1;
        }
        return self.depth;
    }

    // recursively "rehydrate" samplers at every level
    pub fn densify(&mut self) {
        if self.prefixes.len() > 0 {
            for (_, tree) in &mut (self.prefixes) {
                tree.densify(); // recurse first (DFS)
                for (&t, &c) in &(tree.sampler.counts) {
                    self.sampler.add_count(t, c);
                }
            }
        }
    }

    // remove any sampler observations related to prefixes in
    // any nodes with prefixes, and clean the samplers. this
    // can save a significant amount of space.
    pub fn sparsify(&mut self) {
        if self.prefixes.len() > 0 {
            for (_, tree) in &mut (self.prefixes) {
                for (t, &c) in &(tree.sampler.counts) {
                    self.sampler.remove_count(t, c);
                }
                tree.sparsify();
            }
            self.sampler.clean();
            // self.sampler = Sampler::new(); // enough?
        }
    }

    pub fn count_prefixes(&self) -> usize {
        if self.prefixes.len() == 0 {
            return 1 as usize;
        }
        return self
            .prefixes
            .iter()
            .map(|(_, tree)| tree.count_prefixes())
            .sum::<usize>();
    }

    pub fn count_patterns(&self) -> usize {
        if self.prefixes.len() == 0 {
            return self.sampler.counts.len() as usize;
        }
        return self
            .prefixes
            .iter()
            .map(|(_, tree)| tree.count_patterns()) // TODO: not _quite_ right...
            .sum::<usize>();
    }

    // merge two trees, DESTRUCTIVE to other. We could alternatively
    // clone other, but that increases memory. perhaps two methods,
    // but the broad idea (usage in a CombinePerKey like paradigm)
    // should admit destructive merges.
    pub fn merge(&mut self, other: &mut SuffixTree) {
        // assert!(self.token == other.token)

        if self.depth < other.depth {
            self.depth = other.depth;
        }

        if !self.sampler.is_empty() || !other.sampler.is_empty() {
            self.sampler.merge(&other.sampler);
        }

        // merge all prefixes

        // let shr_keys = Vec::<types::TokenType>::with_capacity(other.prefixes.len()); // overestimate?
        // let new_keys = Vec::<types::TokenType>::with_capacity(other.prefixes.len()); // overestimate?

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

    // Attempt to match a specific prefix.
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
        }
    }

    // Return the length of the longest match
    pub fn match_length(&self, p: &[types::TokenType]) -> u32 {
        if p.len() == 0 {
            return 0;
        }
        let r = p.len() - 1; // r == 0 <==> p.len() == 1
        let l = p[r];
        match self.prefixes.get(&l) {
            Some(tree) => {
                if r == 0 {
                    return 1;
                }
                return tree.match_length(&p[0..r]) + 1;
            }
            _ => return 0,
        }
    }

    // need error type response because technically sampler may error
    // we could ignore this if we can verify well-formedness of samplers
    pub fn sample(&self, p: &[types::TokenType]) -> Result<types::TokenType, String> {
        if p.len() == 0 {
            return Ok(self.sampler.sample()?);
        }
        let r = p.len() - 1;
        let l = p[r];
        match self.prefixes.get(&l) {
            Some(tree) => return tree.sample(&p[0..r]),
            _ => return Ok(self.sampler.sample()?),
        }
    }

    // return the probability of a particular token (t) occurrence
    // after the specified prefix (p)
    pub fn probability(&self, p: &[types::TokenType], t: types::TokenType) -> f64 {
        if p.len() == 0 {
            return self.sampler.probability(t);
        }
        let r = p.len() - 1;
        let l = p[r];
        match self.prefixes.get(&l) {
            Some(tree) => return tree.probability(&p[0..r], t),
            _ => self.sampler.probability(t),
        }
    }
}

#[cfg(test)]
mod tests {

    use super::*;
    // use std::cmp;

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

    fn assert_suffix_trees_equal(r: &SuffixTree, s: &SuffixTree) {
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

    #[test]
    fn test_suffix_tree() {
        // let mut s = SuffixTree::new(0);

        // TBD
    }
}
