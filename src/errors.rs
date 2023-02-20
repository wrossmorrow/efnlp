#![allow(dead_code)]
#![allow(non_snake_case)]

use std::fmt;

#[derive(Debug, Clone)]
pub struct SerializationError {
    msg: String,
}

impl SerializationError {
    pub fn new(msg: String) -> SerializationError {
        SerializationError { msg: msg }
    }
}

impl From<prost::EncodeError> for SerializationError {
    fn from(err: prost::EncodeError) -> SerializationError {
        SerializationError::new(err.to_string())
    }
}

impl From<std::io::Error> for SerializationError {
    fn from(err: std::io::Error) -> SerializationError {
        SerializationError::new(err.to_string())
    }
}

impl fmt::Display for SerializationError {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        write!(f, "{}", self.msg)
    }
}

#[derive(Debug, Clone)]
pub struct DeserializationError {
    msg: String,
}

impl DeserializationError {
    pub fn new(msg: String) -> DeserializationError {
        DeserializationError { msg: msg }
    }
}

impl From<prost::DecodeError> for DeserializationError {
    fn from(err: prost::DecodeError) -> DeserializationError {
        DeserializationError::new(err.to_string())
    }
}

impl From<std::io::Error> for DeserializationError {
    fn from(err: std::io::Error) -> DeserializationError {
        DeserializationError::new(err.to_string())
    }
}

impl fmt::Display for DeserializationError {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        write!(f, "{}", self.msg)
    }
}
