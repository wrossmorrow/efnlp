#![allow(dead_code)]
#![allow(non_snake_case)]

use pyo3::exceptions;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyList};
use pyo3::PyResult;

mod compress;
mod errors;
mod language;
mod sampler;
mod suffixtree;
mod suffixtreeset;
mod types;

#[pyclass(name = "SuffixTree")]
struct PySuffixTree {
    wrapped: suffixtree::SuffixTree,
}

#[pymethods]
impl PySuffixTree {
    // TODO: replace key errors with suitable error types

    #[new]
    fn new(t: types::TokenType) -> PyResult<PySuffixTree> {
        Ok(PySuffixTree {
            wrapped: suffixtree::SuffixTree::new(t),
        })
    }

    #[staticmethod]
    fn deserialize(b: &PyBytes, compressed: bool) -> PyResult<PySuffixTree> {
        let bytes = b.as_bytes().to_vec(); // TODO: copying? Could just accept slices
        match suffixtree::SuffixTree::deserialize(&bytes, compressed) {
            Ok(m) => return Ok(PySuffixTree { wrapped: m }),
            Err(e) => Err(PyErr::new::<exceptions::PyValueError, _>(e.to_string())),
        }
    }

    fn serialize(&self, py: Python, compress: bool) -> PyResult<PyObject> {
        match self.wrapped.serialize(compress) {
            Ok(b) => return Ok(PyBytes::new(py, &b).into()),
            Err(e) => Err(PyErr::new::<exceptions::PyValueError, _>(e.to_string())),
        }
    }

    fn json(&self) -> PyResult<String> {
        match self.wrapped.json() {
            Ok(s) => Ok(s),
            Err(e) => Err(PyErr::new::<exceptions::PyValueError, _>(e.to_string())),
        }
    }

    fn token(&self) -> PyResult<types::TokenType> {
        Ok(self.wrapped.token)
    }

    fn depth(&self) -> PyResult<u32> {
        Ok(self.wrapped.depth as u32)
    }

    fn memory(&self) -> PyResult<usize> {
        Ok(self.wrapped.memory())
    }

    fn parse(
        &mut self,
        p: Vec<types::TokenType>,
        t: types::TokenType,
        dense: bool,
    ) -> PyResult<()> {
        if p.len() == 0 {
            return Err(PyErr::new::<exceptions::PyValueError, _>(
                "Cannot parse empty input".to_string(),
            ));
        }
        self.wrapped.parse(&p, t, dense);
        Ok(())
    }

    fn densify(&mut self) -> PyResult<()> {
        Ok(self.wrapped.densify())
    }

    fn sparsify(&mut self) -> PyResult<()> {
        Ok(self.wrapped.sparsify())
    }

    fn merge(&mut self, other: &mut PySuffixTree) -> PyResult<()> {
        Ok(self.wrapped.merge(&mut other.wrapped))
    }

    fn matches(&self, p: Vec<types::TokenType>) -> PyResult<bool> {
        Ok(self.wrapped.matches(&p))
    }

    fn match_length(&self, p: Vec<types::TokenType>) -> PyResult<u32> {
        Ok(self.wrapped.match_length(&p))
    }

    fn sample(&self, p: Vec<types::TokenType>) -> PyResult<types::TokenType> {
        match self.wrapped.sample(&p) {
            Ok(s) => Ok(s),
            Err(e) => Err(PyErr::new::<exceptions::PyValueError, _>(e.to_string())),
        }
    }

    fn probability(&self, p: Vec<types::TokenType>, t: types::TokenType) -> PyResult<f64> {
        Ok(self.wrapped.probability(&p, t))
    }
}

#[pyclass]
struct EFNLP {
    wrapped: suffixtreeset::SuffixTreeSet,
}

#[pymethods]
impl EFNLP {
    // TODO: replace key errors with suitable error types

    #[new]
    fn new() -> PyResult<EFNLP> {
        return Ok(EFNLP {
            wrapped: suffixtreeset::SuffixTreeSet::new(),
        });
    }

    #[staticmethod]
    fn deserialize(b: &PyBytes, compressed: bool) -> PyResult<EFNLP> {
        let bytes = b.as_bytes().to_vec(); // TODO: copying? Could just accept slices
        match suffixtreeset::SuffixTreeSet::deserialize(&bytes, compressed) {
            Ok(m) => return Ok(EFNLP { wrapped: m }),
            Err(e) => Err(PyErr::new::<exceptions::PyValueError, _>(e.to_string())),
        }
    }

    fn serialize(&self, py: Python, compress: bool) -> PyResult<PyObject> {
        match self.wrapped.serialize(compress) {
            Ok(b) => Ok(PyBytes::new(py, &b).into()),
            Err(e) => Err(PyErr::new::<exceptions::PyValueError, _>(e.to_string())),
        }
    }

    fn json(&self) -> PyResult<String> {
        match self.wrapped.json() {
            Ok(s) => Ok(s),
            Err(e) => Err(PyErr::new::<exceptions::PyValueError, _>(e.to_string())),
        }
    }

    fn size(&self) -> PyResult<u32> {
        Ok(self.wrapped.size as u32)
    }

    fn depth(&self) -> PyResult<u32> {
        Ok(self.wrapped.depth as u32)
    }

    fn memory(&self) -> PyResult<usize> {
        Ok(self.wrapped.memory())
    }

    fn occurrences(&self) -> PyResult<usize> {
        Ok(self.wrapped.occurrences())
    }

    fn parse(
        &mut self,
        p: Vec<types::TokenType>,
        t: types::TokenType,
        dense: bool,
    ) -> PyResult<()> {
        if p.len() == 0 {
            return Err(PyErr::new::<exceptions::PyValueError, _>(
                "Cannot parse empty input".to_string(),
            ));
        }
        Ok(self.wrapped.parse(&p, t, dense))
    }

    fn parse_all(&mut self, p: Vec<types::TokenType>, b: usize, dense: bool) -> PyResult<()> {
        if p.len() <= b {
            return Err(PyErr::new::<exceptions::PyValueError, _>(
                "Sequence length too small for block size".to_string(),
            ));
        }
        Ok(self.wrapped.parse_all(&p, b, dense))
    }

    fn densify(&mut self) -> PyResult<()> {
        Ok(self.wrapped.densify())
    }

    fn sparsify(&mut self) -> PyResult<()> {
        Ok(self.wrapped.sparsify())
    }

    fn count_prefixes(&self) -> PyResult<usize> {
        Ok(self.wrapped.count_prefixes())
    }

    fn count_patterns(&self) -> PyResult<usize> {
        Ok(self.wrapped.count_patterns())
    }

    fn merge(&mut self, other: &mut EFNLP) -> PyResult<()> {
        Ok(self.wrapped.merge(&mut other.wrapped))
    }

    // Iterator over trees? That would be convenient...
    // beam code may want to iterate through SuffixTrees
    fn serialized_trees(&self, py: Python<'_>, compress: bool) -> PyResult<PyObject> {
        // can't use `?` here... serialize fails on buffer capacity issues
        let v: Vec<(types::TokenType, &PyBytes)> = self
            .wrapped
            .prefixes
            .values()
            .map(|tree| {
                (
                    tree.token,
                    PyBytes::new(py, &tree.serialize(compress).unwrap()),
                )
            })
            .collect();
        let l = PyList::new(py, v); // TODO: is this copying?
        return Ok(l.into());
    }

    fn matches(&self, p: Vec<types::TokenType>) -> PyResult<bool> {
        Ok(self.wrapped.matches(&p))
    }

    fn match_length(&self, p: Vec<types::TokenType>) -> PyResult<u32> {
        Ok(self.wrapped.match_length(&p))
    }

    fn sample(&self, p: Vec<types::TokenType>) -> PyResult<types::TokenType> {
        match self.wrapped.sample(&p) {
            Ok(s) => Ok(s),
            Err(e) => Err(PyErr::new::<exceptions::PyValueError, _>(e.to_string())),
        }
    }

    fn probability(&self, p: Vec<types::TokenType>, t: types::TokenType) -> PyResult<f64> {
        Ok(self.wrapped.probability(&p, t))
    }

    fn perplexity(&self, p: Vec<types::TokenType>, block_size: usize) -> PyResult<f64> {
        Ok(self.wrapped.perplexity(&p, block_size))
    }

    fn generate(
        &self,
        size: usize,
        block_size: usize,
        prompt: Vec<types::TokenType>,
    ) -> PyResult<Vec<types::TokenType>> {
        match self.wrapped.generate(size, block_size, &prompt) {
            Ok(g) => Ok(g),
            Err(e) => Err(PyErr::new::<exceptions::PyValueError, _>(e.to_string())),
        }
    }
}

#[pyclass]
struct UnicharEncoder {
    encoder: language::CharLanguage,
}

#[pymethods]
impl UnicharEncoder {
    #[new]
    fn new() -> PyResult<Self> {
        // TODO: admit a "special tokens decoder"
        return Ok(UnicharEncoder {
            encoder: language::CharLanguage::new(),
        });
    }

    // fn load(d: PyDict) -> PyResult<UnicharEncoder> { // read in encoder `dict`
    //    // TODO: admit a "special tokens decoder"
    //     let u = CharLanguage::new();
    //     for (py_char, py_tok) in &d {
    //         let c: char = py_char.extract()?;
    //         let t: types::TokenType = py_tok.extract()?;
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

    fn encode(&self, s: String) -> PyResult<Vec<types::TokenType>> {
        match self.encoder.encode(&s) {
            Ok(t) => Ok(t),
            Err(e) => Err(PyErr::new::<exceptions::PyValueError, _>(e.to_string())),
        }
    }

    fn decode(&self, t: Vec<types::TokenType>) -> PyResult<String> {
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
    // use std::cmp;
    use rand::Rng;

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

    #[test]
    fn test_python_parser() {
        let tok_size: types::TokenType = 3;
        let num_tokens = 100;
        let block_size = 3;
        let mut j: String;

        let mut m = EFNLP::new().unwrap(); // ignore python error here

        // just for convenience
        j = m.json().unwrap();
        println!("JSON: {}", j);

        let s = create_arbitrary_token_sequence(tok_size, num_tokens);

        // pass Vec explicitly, not by ref; clone for test only
        // without cloning, we get errors from the slice "copies" below
        m.parse_all(s.clone(), block_size, false).unwrap();

        // just for convenience
        j = m.json().unwrap();
        println!("JSON: {}", j);

        // assert every subsequence in the sequence is in the EFNLP
        // here a conditional in the loop is fine?
        for i in 1..num_tokens - 1 {
            let p: Vec<types::TokenType>;
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

        m.densify().unwrap();

        // verify we can generate
        let p: Vec<types::TokenType> = vec![0];
        let g = m.generate(100, block_size, p).unwrap();
        println!("generated: {:?}", g);

        // let b = m.serialize(); // missing `py` arg; hot to get in testing?
        // let n = EFNLP::deserialize(b);
    }
}
