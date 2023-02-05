#![allow(dead_code)]
#![allow(unused_imports)]
#![allow(non_snake_case)]

use rand::Rng;
use serde_derive::{Deserialize, Serialize};
use std::collections::HashMap;

use pyo3::exceptions;
use pyo3::prelude::*;
use pyo3::PyResult;

//
// Basic objects
//

pub type TokenType = u16;

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

    // return this Sampler as a JSON string
    pub fn json(&self) -> Result<String, serde_json::Error> {
        return Ok(serde_json::to_string(self)?);
    }

    // add an observed element to this sampler
    pub fn add(&mut self, t: TokenType) {
        self.total += 1.0;
        match self.counts.get(&t) {
            Some(&count) => self.counts.insert(t, count + 1),
            _ => self.counts.insert(t, 1),
        };
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

    // return this Sampler as a JSON string
    pub fn json(&self) -> Result<String, serde_json::Error> {
        return Ok(serde_json::to_string(self)?);
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

    // return this Sampler as a JSON string
    pub fn json(&self) -> Result<String, serde_json::Error> {
        return Ok(serde_json::to_string(self)?);
    }

    pub fn parse(&mut self, p: &[TokenType], t: TokenType) {
        if p.len() == 0 {
            return;
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

    pub fn parse_all(&mut self, p: &[TokenType], b: usize) {
        for i in 1..b {
            self.parse(&p[0..i], p[i]);
        }
        for i in b..p.len() - 1 {
            self.parse(&p[i - b..i], p[i]);
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

//
// Python interface
//

#[pyclass]
struct EFNLP {
    model: SuffixTreeSet,
}

#[pymethods]
impl EFNLP {
    #[new]
    fn new() -> PyResult<Self> {
        return Ok(EFNLP {
            model: SuffixTreeSet::new(),
        });
    }

    fn json(&self) -> PyResult<String> {
        match self.model.json() {
            Ok(s) => Ok(s),
            Err(e) => Err(PyErr::new::<exceptions::PyKeyError, _>(e.to_string())),
        }
    }

    fn parse(&mut self, p: Vec<TokenType>, t: TokenType) {
        self.model.parse(&p, t);
    }

    fn parse_all(&mut self, p: Vec<TokenType>, b: usize) {
        self.model.parse_all(&p, b);
    }

    fn matches(&self, p: Vec<TokenType>) -> PyResult<bool> {
        if self.model.matches(&p) {
            return Ok(true);
        }
        return Ok(false);
    }

    fn sample(&self, p: Vec<TokenType>) -> PyResult<TokenType> {
        match self.model.sample(&p) {
            Ok(s) => Ok(s),
            Err(e) => Err(PyErr::new::<exceptions::PyKeyError, _>(e.to_string())),
        }
    }

    fn probability(&self, p: Vec<TokenType>, t: TokenType) -> PyResult<f64> {
        return Ok(self.model.probability(&p, t));
    }

    fn generate(
        &self,
        size: usize,
        block_size: usize,
        prompt: Vec<TokenType>,
    ) -> PyResult<Vec<TokenType>> {
        match self.model.generate(size, block_size, &prompt) {
            Ok(g) => Ok(g),
            Err(e) => Err(PyErr::new::<exceptions::PyKeyError, _>(e.to_string())),
        }
    }
}

#[pymodule]
fn _efnlp(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<EFNLP>()?;
    Ok(())
}

//
// Unit tests
//

#[cfg(test)]
mod tests {

    use super::*;

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

    #[test]
    fn test_sampler() {
        let mut s = Sampler::new();

        for _ in 1..10 {
            s.add(draw_arbitrary_token(3))
        }

        match s.json() {
            Ok(j) => println!("JSON: {}", j),
            Err(e) => println!("Error: {}", e),
        }

        for _ in 1..10 {
            match s.sample() {
                Ok(t) => println!("Sampled: {}", t),
                Err(e) => println!("Error: {}", e),
            }
        }
    }

    #[test]
    fn test_parser() {
        let tok_size: TokenType = 3;
        let num_tokens = 100;
        let block_size = 3;

        let mut treeset = SuffixTreeSet::new();

        match treeset.json() {
            Ok(j) => println!("JSON: {}", j),
            Err(e) => println!("Error: {}", e),
        }

        let seq = create_arbitrary_token_sequence(tok_size, num_tokens);

        treeset.parse_all(&seq, block_size);

        match treeset.json() {
            Ok(j) => println!("JSON: {}", j),
            Err(e) => println!("Error: {}", e),
        }

        let prompt: Vec<TokenType> = vec![0];
        match treeset.generate(100, block_size, &prompt) {
            Ok(gen) => println!("generated: {:?}", gen),
            Err(e) => println!("Error: {}", e),
        }
    }
}
