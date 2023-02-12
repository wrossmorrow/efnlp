#![allow(dead_code)]
#![allow(unused_imports)]
#![allow(non_snake_case)]

use rand::Rng;
use serde_derive::{Deserialize, Serialize};
use std::cmp;
use std::collections::hash_map::Iter;
use std::collections::HashMap;

use pyo3::exceptions;
use pyo3::prelude::*;
use pyo3::types::IntoPyDict;
use pyo3::types::{PyBytes, PyDict, PyList};
use pyo3::PyResult;

use prost::Message;

pub mod efnlp_pb {
    pub mod pb {
        include!("efnlp.v1alpha1.rs");
    }
}

use efnlp_pb::pb;

// // // // // // // // // // // // // // // // // // // // // // // // // // // // // //
//
// Basic objects
//
// // // // // // // // // // // // // // // // // // // // // // // // // // // // // //

pub type TokenType = u16;
pub type ProtoBytes = Vec<u8>;

// Simple character based language; naive, but maybe super fast

#[derive(Serialize, Deserialize)]
pub struct CharLanguage {
    size: TokenType,
    encoder: HashMap<char, TokenType>,
    decoder: HashMap<TokenType, char>,
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

    pub fn add_tok(&mut self, c: char, t: TokenType) {
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

    pub fn encode(&self, s: &String) -> Result<Vec<TokenType>, String> {
        let mut encoded = Vec::<TokenType>::with_capacity(s.len()); // overestimate
        for c in s.chars() {
            match self.encoder.get(&c) {
                Some(&t) => encoded.push(t),
                _ => return Err("character not encodable".to_string()),
            }
        }
        Ok(encoded)
    }

    pub fn decode(&self, tokens: &Vec<TokenType>) -> Result<String, String> {
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

// Simple uniform sampler based on counts and totals

#[derive(Serialize, Deserialize)]
pub struct Sampler {
    total: f64,
    counts: HashMap<TokenType, u32>,
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
    pub fn from_proto(P: &pb::Sampler) -> Sampler {
        let mut S = Sampler::new();
        S.total = P.total as f64;
        for stc in P.counts.iter() {
            S.counts.insert(stc.token as TokenType, stc.count as u32);
        }
        return S;
    }

    // return this sampler as a protobuf Message
    pub fn proto(&self) -> pb::Sampler {
        let mut P = pb::Sampler {
            total: self.total as u32,
            counts: Vec::with_capacity(self.counts.len()),
        };
        for (&t, &c) in &(self.counts) {
            P.counts.push(pb::SamplerTokenCount {
                token: t as u32,
                count: c as u32,
            });
        }
        return P;
    }

    // serialize to protobuf bytes
    pub fn serialize(&self) -> Result<ProtoBytes, prost::EncodeError> {
        let P = self.proto();
        let mut buf = vec![];
        P.encode(&mut buf)?; // insufficient capacity
        return Ok(buf);
    }

    // create a sampler from serialized proto
    pub fn deserialize(buf: ProtoBytes) -> Result<Sampler, prost::DecodeError> {
        let P: pb::Sampler = Message::decode(&buf[..])?;
        return Ok(Sampler::from_proto(&P));
    }

    // return this Sampler as a JSON string
    pub fn json(&self) -> Result<String, serde_json::Error> {
        return Ok(serde_json::to_string(self)?);
    }

    pub fn memory(&self) -> usize {
        return 8 + 4 * self.counts.len();
    }

    // add an observed element to this sampler
    pub fn add(&mut self, t: TokenType) {
        self.total += 1.0;
        match self.counts.get(&t) {
            Some(&count) => self.counts.insert(t, count + 1),
            _ => self.counts.insert(t, 1),
        };
    }

    pub fn merge(&mut self, other: &Sampler) {
        // compute updates
        let mut updates = HashMap::<TokenType, u32>::new();
        for (t, c) in &(self.counts) {
            if other.counts.contains_key(t) {
                let d = other.counts[t];
                updates.insert(*t, *c + d);
            }
        }

        for (t, c) in &(other.counts) {
            if !self.counts.contains_key(t) {
                updates.insert(*t, *c);
            }
        }

        self.total += other.total; // add together totals

        // insert updates
        for (t, c) in updates {
            self.counts.insert(t, c);
        }
    }

    // sample from the distribution described by this sampler
    pub fn sample(&self) -> Result<TokenType, String> {
        let mut r: f64 = rand::thread_rng().gen_range(0.0..self.total);
        for (&t, &c) in self.counts.iter() {
            let fc = c as f64;
            if r < fc {
                return Ok(t);
            }
            r -= fc;
        }
        Err("sampler malformed".to_string())
    }

    // return the probability of sampling a particular token
    pub fn probability(&self, t: TokenType) -> f64 {
        match self.counts.get(&t) {
            Some(&c) => {
                let fc = c as f64;
                return fc / self.total;
            }
            _ => return 0.0,
        };
    }
}

#[derive(Serialize, Deserialize)]
pub struct SuffixTree {
    token: TokenType,
    depth: u16, // O(65k); u8 would be enough really
    sampler: Sampler,
    prefixes: HashMap<TokenType, SuffixTree>,
}

impl SuffixTree {
    // new empty SuffixTree
    pub fn new(t: TokenType) -> SuffixTree {
        return SuffixTree {
            token: t,
            depth: 0,
            sampler: Sampler::new(),
            prefixes: HashMap::new(),
        };
    }

    // create a sampler from proto
    pub fn from_proto(P: &pb::SuffixTree) -> SuffixTree {
        let mut S = SuffixTree::new(P.token as TokenType);
        S.depth = P.depth as u16;
        match &P.sampler {
            Some(s) => S.sampler = Sampler::from_proto(&s),
            _ => (),
        }
        for subtree_pb in P.prefixes.iter() {
            let subtree = SuffixTree::from_proto(subtree_pb);
            S.prefixes.insert(subtree.token, subtree);
        }
        return S;
    }

    // return this sampler as a protobuf Message
    pub fn proto(&self) -> pb::SuffixTree {
        let mut P = pb::SuffixTree {
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
    pub fn serialize(&self) -> Result<ProtoBytes, prost::EncodeError> {
        let P = self.proto();
        let mut buf = vec![];
        P.encode(&mut buf)?;
        return Ok(buf);
    }

    // create a sampler from serialized proto
    pub fn deserialize(buf: &ProtoBytes) -> Result<SuffixTree, prost::DecodeError> {
        let P: pb::SuffixTree = Message::decode(&buf[..])?;
        return Ok(SuffixTree::from_proto(&P));
    }

    // return this Sampler as a JSON string
    pub fn json(&self) -> Result<String, serde_json::Error> {
        return Ok(serde_json::to_string(self)?);
    }

    // return a memory estimate
    pub fn memory(&self) -> usize {
        let mut m: usize = 0;
        for (_, tree) in &self.prefixes {
            m += 2 + tree.memory();
        }
        return 4 + self.sampler.memory() + m;
    }

    pub fn parse(&mut self, p: &[TokenType], t: TokenType) -> u16 {
        self.sampler.add(t);
        if p.len() == 0 {
            return self.depth;
        }
        let r = p.len() - 1;
        let l = p[r];
        let d: u16;
        match self.prefixes.get_mut(&l) {
            Some(u) => {
                d = u.parse(&p[0..r], t);
            }
            _ => {
                let mut n = SuffixTree::new(l);
                d = n.parse(&p[0..r], t);
                self.prefixes.insert(l, n);
            }
        }
        if d + 1 > self.depth {
            self.depth = d + 1;
        }
        return self.depth;
    }

    pub fn merge(&mut self, other: &mut SuffixTree) {
        // NOTE: destructive to "other"

        // assert self.token == other.token?

        if self.depth < other.depth {
            self.depth = other.depth;
        }

        self.sampler.merge(&other.sampler);

        // merge all prefixes

        // let shr_keys = Vec::<TokenType>::with_capacity(other.prefixes.len()); // overestimate?
        // let new_keys = Vec::<TokenType>::with_capacity(other.prefixes.len()); // overestimate?

        // TODO: how to reserve well? Important?
        let mut shr_keys = Vec::<TokenType>::new();
        let mut new_keys = Vec::<TokenType>::new();
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

    pub fn matches(&self, p: &[TokenType]) -> bool {
        if p.len() == 0 {
            return false;
        }
        let r = p.len() - 1;
        let l = p[r];
        match self.prefixes.get(&l) {
            Some(t) => {
                // &SuffixTree
                if r == 0 {
                    // p.len()-1 == 0 <==> p.len() == 1
                    return true;
                }
                return t.matches(&p[0..r]);
            }
            _ => return false,
        }
    }

    // need error type response because technically sampler may error
    pub fn sample(&self, p: &[TokenType]) -> Result<TokenType, String> {
        if p.len() == 0 {
            return Ok(self.sampler.sample()?);
        }
        let r = p.len() - 1;
        let l = p[r];
        match self.prefixes.get(&l) {
            Some(t) => return t.sample(&p[0..r]),
            _ => return Ok(self.sampler.sample()?),
        }
    }

    pub fn probability(&self, p: &[TokenType], t: TokenType) -> f64 {
        if p.len() == 0 {
            return self.sampler.probability(t);
        }
        let r = p.len() - 1;
        let l = p[r];
        match self.prefixes.get(&l) {
            Some(u) => return u.probability(&p[0..r], t),
            _ => self.sampler.probability(t),
        }
    }
}

#[derive(Serialize, Deserialize)]
pub struct SuffixTreeSet {
    size: u32,
    depth: u16, // O(65k); u8 would be enough really
    sampler: Sampler,
    prefixes: HashMap<TokenType, SuffixTree>,
}

impl SuffixTreeSet {
    // new empty SuffixTree
    pub fn new() -> SuffixTreeSet {
        return SuffixTreeSet {
            size: 0,
            depth: 0,
            sampler: Sampler::new(),
            prefixes: HashMap::new(),
        };
    }

    // create a sampler from proto
    pub fn from_proto(P: &pb::SuffixTreeSet) -> SuffixTreeSet {
        let mut S = SuffixTreeSet::new();
        S.size = P.size as u32; // is it u32?
        S.depth = P.depth as u16;
        match &P.sampler {
            Some(s) => S.sampler = Sampler::from_proto(&s),
            _ => (),
        }
        for subtree_pb in P.prefixes.iter() {
            let subtree = SuffixTree::from_proto(subtree_pb);
            S.prefixes.insert(subtree.token, subtree);
        }
        return S;
    }

    // return this sampler as a protobuf Message
    pub fn proto(&self) -> pb::SuffixTreeSet {
        let mut P = pb::SuffixTreeSet {
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
    pub fn serialize(&self) -> Result<ProtoBytes, prost::EncodeError> {
        let P = self.proto();
        let mut buf = vec![];
        P.encode(&mut buf)?;
        return Ok(buf);
    }

    // create a sampler from serialized proto
    pub fn deserialize(buf: &ProtoBytes) -> Result<SuffixTreeSet, prost::DecodeError> {
        let P: pb::SuffixTreeSet = Message::decode(&buf[..])?;
        return Ok(SuffixTreeSet::from_proto(&P));
    }

    // return this Sampler as a JSON string
    pub fn json(&self) -> Result<String, serde_json::Error> {
        return Ok(serde_json::to_string(self)?);
    }

    pub fn memory(&self) -> usize {
        let mut m: usize = 4 + 2 + self.sampler.memory(); // u32 + u16 + ?
        for (_, tree) in &(self.prefixes) {
            m += tree.memory();
        }
        return m;
    }

    pub fn parse(&mut self, p: &[TokenType], t: TokenType) {
        if p.len() == 0 {
            return; // no action, avoid complexities from returning errors
        }
        self.sampler.add(t);
        let r = p.len() - 1;
        let l = p[r];
        let d: u16;
        match self.prefixes.get_mut(&l) {
            Some(tree) => {
                // &SuffixTree
                d = tree.parse(&p[0..r], t);
            }
            _ => {
                let mut n = SuffixTree::new(l);
                d = n.parse(&p[0..r], t);
                self.prefixes.insert(l, n);
            }
        }
        if d + 1 > self.depth {
            self.depth = d + 1;
        }
    }

    pub fn parse_all(&mut self, s: &[TokenType], b: usize) {
        // use two loops to avoid a conditional in each iter
        // TODO: can error out if s.len() < b
        for i in 1..b {
            self.parse(&s[0..i], s[i]);
        }
        for i in b..s.len() - 1 {
            self.parse(&s[i - b..i], s[i]);
        }
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
        let mut shr_keys = Vec::<TokenType>::new();
        let mut new_keys = Vec::<TokenType>::new();
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

    pub fn matches(&self, p: &[TokenType]) -> bool {
        if p.len() == 0 {
            return false;
        }
        let r = p.len() - 1;
        let l = p[r];
        match self.prefixes.get(&l) {
            Some(t) => {
                // &SuffixTree
                if r == 0 {
                    // p.len()-1 == 0 <==> p.len() == 1
                    return true;
                }
                return t.matches(&p[0..r]);
            }
            _ => return false,
        };
    }

    pub fn sample(&self, p: &[TokenType]) -> Result<TokenType, String> {
        if p.len() == 0 {
            return Err("Sampling requires a (nontrivial) prefix".to_string());
        }
        let r = p.len() - 1;
        let l = p[r];
        match self.prefixes.get(&l) {
            Some(t) => return Ok(t.sample(&p[0..r])?),
            _ => return Err("Unknown token in prefix".to_string()),
        }
    }

    pub fn probability(&self, p: &[TokenType], t: TokenType) -> f64 {
        if p.len() == 0 {
            return self.sampler.probability(t);
        }
        let r = p.len() - 1;
        let l = p[r];
        match self.prefixes.get(&l) {
            Some(u) => return u.probability(&p[0..r], t),
            _ => self.sampler.probability(t),
        }
    }

    pub fn generate(
        &self,
        size: usize,
        block_size: usize,
        prompt: &[TokenType],
    ) -> Result<Vec<TokenType>, String> {
        if prompt.len() == 0 {
            return Err("Cannot generate with an empty prompt.".to_string());
        }

        let total_size = prompt.len() + size;
        let mut gen = Vec::<TokenType>::with_capacity(total_size);

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

// // // // // // // // // // // // // // // // // // // // // // // // // // // // // //
//
// Python interface
//
// // // // // // // // // // // // // // // // // // // // // // // // // // // // // //

#[pyclass(name = "SuffixTree")]
struct PySuffixTree {
    wrapped: SuffixTree,
}

#[pymethods]
impl PySuffixTree {
    // TODO: replace key errors with suitable error types

    #[new]
    fn new(t: TokenType) -> PyResult<PySuffixTree> {
        return Ok(PySuffixTree {
            wrapped: SuffixTree::new(t),
        });
    }

    #[staticmethod]
    fn deserialize(b: &PyBytes) -> PyResult<PySuffixTree> {
        let bytes = b.as_bytes().to_vec(); // TODO: copying? Could just accept slices
        match SuffixTree::deserialize(&bytes) {
            Ok(m) => return Ok(PySuffixTree { wrapped: m }),
            Err(e) => Err(PyErr::new::<exceptions::PyKeyError, _>(e.to_string())),
        }
    }

    fn serialize(&self, py: Python) -> PyResult<PyObject> {
        match self.wrapped.serialize() {
            Ok(b) => return Ok(PyBytes::new(py, &b).into()),
            Err(e) => Err(PyErr::new::<exceptions::PyKeyError, _>(e.to_string())),
        }
    }

    fn json(&self) -> PyResult<String> {
        match self.wrapped.json() {
            Ok(s) => Ok(s),
            Err(e) => Err(PyErr::new::<exceptions::PyKeyError, _>(e.to_string())),
        }
    }

    fn token(&self) -> PyResult<TokenType> {
        Ok(self.wrapped.token)
    }

    fn depth(&self) -> PyResult<u32> {
        Ok(self.wrapped.depth as u32)
    }

    fn memory(&self) -> PyResult<usize> {
        return Ok(self.wrapped.memory());
    }

    fn parse(&mut self, p: Vec<TokenType>, t: TokenType) -> PyResult<()> {
        if p.len() == 0 {
            return Err(PyErr::new::<exceptions::PyValueError, _>(
                "Cannot parse empty input".to_string(),
            ));
        }
        self.wrapped.parse(&p, t);
        Ok(())
    }

    fn merge(&mut self, other: &mut PySuffixTree) {
        self.wrapped.merge(&mut other.wrapped);
    }

    fn matches(&self, p: Vec<TokenType>) -> PyResult<bool> {
        if self.wrapped.matches(&p) {
            return Ok(true);
        }
        return Ok(false);
    }

    fn sample(&self, p: Vec<TokenType>) -> PyResult<TokenType> {
        match self.wrapped.sample(&p) {
            Ok(s) => Ok(s),
            Err(e) => Err(PyErr::new::<exceptions::PyKeyError, _>(e.to_string())),
        }
    }

    fn probability(&self, p: Vec<TokenType>, t: TokenType) -> PyResult<f64> {
        return Ok(self.wrapped.probability(&p, t));
    }
}

#[pyclass]
struct EFNLP {
    wrapped: SuffixTreeSet,
}

#[pymethods]
impl EFNLP {
    // TODO: replace key errors with suitable error types

    #[new]
    fn new() -> PyResult<EFNLP> {
        return Ok(EFNLP {
            wrapped: SuffixTreeSet::new(),
        });
    }

    #[staticmethod]
    fn deserialize(b: &PyBytes) -> PyResult<EFNLP> {
        let bytes = b.as_bytes().to_vec(); // TODO: copying? Could just accept slices
        match SuffixTreeSet::deserialize(&bytes) {
            Ok(m) => return Ok(EFNLP { wrapped: m }),
            Err(e) => Err(PyErr::new::<exceptions::PyKeyError, _>(e.to_string())),
        }
    }

    fn serialize(&self, py: Python) -> PyResult<PyObject> {
        match self.wrapped.serialize() {
            Ok(b) => return Ok(PyBytes::new(py, &b).into()),
            Err(e) => Err(PyErr::new::<exceptions::PyKeyError, _>(e.to_string())),
        }
    }

    fn json(&self) -> PyResult<String> {
        match self.wrapped.json() {
            Ok(s) => Ok(s),
            Err(e) => Err(PyErr::new::<exceptions::PyKeyError, _>(e.to_string())),
        }
    }

    fn size(&self) -> PyResult<u32> {
        Ok(self.wrapped.size as u32)
    }

    fn depth(&self) -> PyResult<u32> {
        Ok(self.wrapped.depth as u32)
    }

    fn memory(&self) -> PyResult<usize> {
        return Ok(self.wrapped.memory());
    }

    fn parse(&mut self, p: Vec<TokenType>, t: TokenType) -> PyResult<()> {
        // TODO: return Python exception when p.len() == 0?
        if p.len() == 0 {
            return Err(PyErr::new::<exceptions::PyValueError, _>(
                "Cannot parse empty input".to_string(),
            ));
        }
        self.wrapped.parse(&p, t);
        Ok(())
    }

    fn parse_all(&mut self, p: Vec<TokenType>, b: usize) {
        // TODO: return Python exception when p.len() == 0?
        self.wrapped.parse_all(&p, b);
    }

    fn merge(&mut self, other: &mut EFNLP) {
        self.wrapped.merge(&mut other.wrapped);
    }

    // Iterator over trees? That would be convenient...
    // beam code may want to iterate through SuffixTrees
    fn serialized_trees(&self, py: Python<'_>) -> PyResult<PyObject> {
        // can't use `?` here... serialize fails on buffer capacity issues
        let v: Vec<(TokenType, &PyBytes)> = self
            .wrapped
            .prefixes
            .values()
            .map(|tree| (tree.token, PyBytes::new(py, &tree.serialize().unwrap())))
            .collect();
        let l = PyList::new(py, v); // TODO: is this copying?
        return Ok(l.into());
    }

    fn matches(&self, p: Vec<TokenType>) -> PyResult<bool> {
        if self.wrapped.matches(&p) {
            return Ok(true);
        }
        return Ok(false);
    }

    fn sample(&self, p: Vec<TokenType>) -> PyResult<TokenType> {
        match self.wrapped.sample(&p) {
            Ok(s) => Ok(s),
            Err(e) => Err(PyErr::new::<exceptions::PyKeyError, _>(e.to_string())),
        }
    }

    fn probability(&self, p: Vec<TokenType>, t: TokenType) -> PyResult<f64> {
        return Ok(self.wrapped.probability(&p, t));
    }

    fn generate(
        &self,
        size: usize,
        block_size: usize,
        prompt: Vec<TokenType>,
    ) -> PyResult<Vec<TokenType>> {
        match self.wrapped.generate(size, block_size, &prompt) {
            Ok(g) => Ok(g),
            Err(e) => Err(PyErr::new::<exceptions::PyValueError, _>(e.to_string())),
        }
    }
}

#[pyclass]
struct UnicharEncoder {
    encoder: CharLanguage,
}

#[pymethods]
impl UnicharEncoder {
    #[new]
    fn new() -> PyResult<Self> {
        // TODO: admit a "special tokens decoder"
        return Ok(UnicharEncoder {
            encoder: CharLanguage::new(),
        });
    }

    // fn load(d: PyDict) -> PyResult<UnicharEncoder> { // read in encoder `dict`
    //    // TODO: admit a "special tokens decoder"
    //     let u = CharLanguage::new();
    //     for (py_char, py_tok) in &d {
    //         let c: char = py_char.extract()?;
    //         let t: TokenType = py_tok.extract()?;
    //         u.add_tok(c, t);
    //     }
    //     return Ok(UnicharEncoder{encoder: u});
    // }

    // fn loads(j: String) -> PyResult<UnicharEncoder> {
    //     // TODO: admit a "special tokens decoder"
    //     match CharLanguage::from_json(&j) {
    //         Ok(u) => return Ok(UnicharEncoder{encoder: u}),
    //         Err(e) => Err(PyErr::new::<exceptions::PyValueError, _>(e.to_string())),
    //     }
    // }

    // fn dump(&self) -> PyResult<PyDict> // write out encoder `dict`
    fn dumps(&self) -> PyResult<String> {
        match self.encoder.json() {
            Ok(s) => Ok(s),
            Err(e) => Err(PyErr::new::<exceptions::PyValueError, _>(e.to_string())),
        }
    }

    fn add_str(&mut self, s: String) {
        self.encoder.add_str(&s);
    }

    fn encode(&self, s: String) -> PyResult<Vec<TokenType>> {
        match self.encoder.encode(&s) {
            Ok(t) => Ok(t),
            Err(e) => Err(PyErr::new::<exceptions::PyValueError, _>(e.to_string())),
        }
    }

    fn decode(&self, t: Vec<TokenType>) -> PyResult<String> {
        // -> PyString?
        match self.encoder.decode(&t) {
            Ok(s) => Ok(s),
            Err(e) => Err(PyErr::new::<exceptions::PyValueError, _>(e.to_string())),
        }
    }
}

#[pymodule]
fn _efnlp(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<PySuffixTree>()?;
    m.add_class::<EFNLP>()?;
    m.add_class::<UnicharEncoder>()?;
    Ok(())
}

// // // // // // // // // // // // // // // // // // // // // // // // // // // // // //
//
// Unit tests
//
// // // // // // // // // // // // // // // // // // // // // // // // // // // // // //

#[cfg(test)]
mod tests {

    use super::*;
    use std::cmp;

    fn draw_arbitrary_token(tok_size: TokenType) -> TokenType {
        return rand::thread_rng().gen_range(0..tok_size);
    }

    fn create_arbitrary_token_sequence(tok_size: TokenType, size: usize) -> Vec<TokenType> {
        let mut seq = Vec::<TokenType>::with_capacity(size);
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

        match s.serialize() {
            Ok(b) => match Sampler::deserialize(b) {
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

    #[test]
    fn test_suffix_tree() {
        let mut s = SuffixTree::new(0);

        // TBD
    }

    #[test]
    fn test_parser() {
        let tok_size: TokenType = 3;
        let num_tokens = 100;
        let block_size = 3;

        let mut m = SuffixTreeSet::new();

        match m.json() {
            Ok(j) => println!("JSON: {}", j),
            Err(e) => println!("Error: {}", e),
        }

        let s = create_arbitrary_token_sequence(tok_size, num_tokens);

        m.parse_all(&s, block_size);

        match m.json() {
            Ok(j) => println!("JSON: {}", j),
            Err(e) => println!("Error: {}", e),
        }

        // assert every subsequence in the sequence is in the SuffixTreeSet
        for i in 1..block_size {
            assert!(m.matches(&s[0..i]));
        }
        for i in block_size..num_tokens - 1 {
            assert!(m.matches(&s[i - block_size..i]));
        }

        // verify we can generate
        let p: Vec<TokenType> = vec![0];
        match m.generate(100, block_size, &p) {
            Ok(gen) => println!("generated: {:?}", gen),
            Err(e) => println!("Error in generate: {}", e),
        }

        // serde

        let p = m.proto();
        let m1 = SuffixTreeSet::from_proto(&p);
        assert_suffix_tree_sets_equal(&m, &m1);

        match m.serialize() {
            Ok(b) => match SuffixTreeSet::deserialize(&b) {
                Ok(m2) => {
                    assert_suffix_tree_sets_equal(&m, &m2);
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
    fn test_merge_parsers() {
        let tok_size: TokenType = 3;
        let num_tokens = 100;
        let block_size = 3;

        let mut m1 = SuffixTreeSet::new();
        let mut m2 = SuffixTreeSet::new();
        let mut m = SuffixTreeSet::new();

        let s1 = create_arbitrary_token_sequence(tok_size, num_tokens);
        let s2 = create_arbitrary_token_sequence(tok_size, num_tokens);

        m1.parse_all(&s1, block_size);
        m2.parse_all(&s2, block_size);

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
        let prompt: Vec<TokenType> = vec![0];
        match m.generate(100, block_size, &prompt) {
            Ok(gen) => println!("generated: {:?}", gen),
            Err(e) => println!("Error: {}", e),
        }
    }

    #[test]
    fn test_python_parser() {
        let tok_size: TokenType = 3;
        let num_tokens = 100;
        let block_size = 3;

        let mut m = EFNLP::new().unwrap(); // avoid python error

        // just for convenience
        match m.json() {
            Ok(j) => println!("JSON: {}", j),
            Err(e) => println!("Error: {}", e),
        }

        let s = create_arbitrary_token_sequence(tok_size, num_tokens);

        // pass Vec explicitly, not by ref; clone for test only
        // without cloning, we get errors from the slice "copies" below
        m.parse_all(s.clone(), block_size);

        // just for convenience
        match m.json() {
            Ok(j) => println!("JSON: {}", j),
            Err(e) => println!("Error: {}", e),
        }

        // assert every subsequence in the sequence is in the EFNLP
        // here a conditional in the loop is fine?
        for i in 1..num_tokens - 1 {
            let p: Vec<TokenType>;
            if i <= block_size {
                p = (&s[0..i]).to_vec();
            } else {
                p = (&s[i - block_size..i]).to_vec();
            }
            match m.matches(p) {
                Ok(b) => assert!(b),
                _ => assert!(false),
            }
        }

        // verify we can generate
        let p: Vec<TokenType> = vec![0];
        match m.generate(100, block_size, p) {
            Ok(gen) => println!("generated: {:?}", gen),
            Err(e) => println!("Error in generate: {}", e),
        }

        // let b = m.serialize(); // missing py arg
        // let n = EFNLP::deserialize(b);
    }
}

// // // // // // // // // // // // // // // // // // // // // // // // // // // // // //
//
// Fin
//
// // // // // // // // // // // // // // // // // // // // // // // // // // // // // //
