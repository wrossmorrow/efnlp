#![allow(dead_code)]
#![allow(unused_imports)]
#![allow(non_snake_case)]

use std::io::{Read, Write}; // uh, really?

// TODO: enable optional compression in serialization (and decomp in deserialization)
use flate2::read::GzDecoder;
use flate2::write::GzEncoder;
use flate2::Compression;

pub fn compress_bytes(buf: &Vec<u8>) -> Result<Vec<u8>, std::io::Error> {
    let mut e = GzEncoder::new(Vec::<u8>::new(), Compression::default());
    e.write_all(&buf)?;
    return Ok(e.finish()?);
}

pub fn decompress_bytes(buf: &Vec<u8>) -> Result<Vec<u8>, std::io::Error> {
    let mut d = GzDecoder::new(&buf[..]);
    let mut b = Vec::<u8>::new();
    d.read_to_end(&mut b)?;
    return Ok(b);
}
