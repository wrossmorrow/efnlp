// @generated
#[derive(Clone, PartialEq, ::prost::Message)]
pub struct Version {
    #[prost(uint32, tag="1")]
    pub major: u32,
    #[prost(uint32, tag="2")]
    pub minor: u32,
}
#[derive(Clone, PartialEq, ::prost::Message)]
pub struct Language {
    /// A "language" specifies how to convert (utf-8?) character sequences into 
    /// "token" sequences. A "token" is just a uint32. Here, we use a list of 
    /// "Encoder" objects that map strings to tokens (proto will compress them).
    #[prost(string, tag="1")]
    pub name: ::prost::alloc::string::String,
    #[prost(message, optional, tag="2")]
    pub version: ::core::option::Option<Version>,
    #[prost(message, repeated, tag="3")]
    pub suffixes: ::prost::alloc::vec::Vec<SuffixEncoder>,
    #[prost(message, optional, tag="4")]
    pub options: ::core::option::Option<LanguageOptions>,
    #[prost(message, optional, tag="5")]
    pub stats: ::core::option::Option<LanguageStats>,
}
#[derive(Clone, PartialEq, ::prost::Message)]
pub struct LanguageOptions {
    /// how to handle unknown data/tokens
    #[prost(message, optional, tag="1")]
    pub unknown: ::core::option::Option<UnknownHandler>,
    /// "special" token encodings
    #[prost(message, repeated, tag="2")]
    pub special: ::prost::alloc::vec::Vec<SuffixEncoder>,
}
#[derive(Clone, PartialEq, ::prost::Message)]
pub struct LanguageStats {
    /// more than 32 would be cray cray
    #[prost(uint32, tag="1")]
    pub size: u32,
    /// more than 32 would be cray cray
    #[prost(uint32, tag="2")]
    pub depth: u32,
}
#[derive(Clone, PartialEq, ::prost::Message)]
pub struct UnknownHandler {
    /// an encoder for unknown tokens/string data... if data is encountered
    /// (and parse_unknown_data == true) encode it as the listed token; 
    /// conversely if an unknown token is encountered (and parse_unknown_token
    /// == false) decode it as the listed string. 
    ///
    /// default false (code should raise an error)
    #[prost(bool, tag="1")]
    pub parse_unknown_data: bool,
    /// default false (code should raise an error)
    #[prost(bool, tag="2")]
    pub parse_unknown_token: bool,
    /// default SuffixEncoder{0, 0, 0, []}
    #[prost(message, optional, tag="3")]
    pub unknown: ::core::option::Option<SuffixEncoder>,
}
#[derive(Clone, PartialEq, ::prost::Message)]
pub struct SuffixEncoder {
    /// The token (maybe). An Encoder plays a role in realizing suffix trees, 
    /// wherein we break up any bytestrings into bytes and parse "backwards"
    /// to find longest matching suffixes. This is a recursive datastructure 
    /// for modeling that style of suffix tree. 
    ///
    /// UTF-8 string components (code points)
    #[prost(string, tag="1")]
    pub value: ::prost::alloc::string::String,
    #[prost(uint32, tag="2")]
    pub depth: u32,
    /// uint16 is enough; proto serialization compresses ints
    #[prost(uint32, tag="3")]
    pub token: u32,
    #[prost(bool, tag="4")]
    pub atom: bool,
    #[prost(message, repeated, tag="5")]
    pub prefixes: ::prost::alloc::vec::Vec<SuffixEncoder>,
}
/// TBD: a Token message would make units clean across uses, but the schema annoying
#[derive(Clone, PartialEq, ::prost::Message)]
pub struct Token {
    #[prost(uint32, tag="1")]
    pub value: u32,
}
#[derive(Clone, PartialEq, ::prost::Message)]
pub struct Sampler {
    /// 64? MaxUInt32 ~ 4.3B which sounds pretty high. And we _can_ reduce...
    #[prost(uint32, tag="1")]
    pub total: u32,
    #[prost(message, repeated, tag="2")]
    pub counts: ::prost::alloc::vec::Vec<SamplerTokenCount>,
}
#[derive(Clone, PartialEq, ::prost::Message)]
pub struct SamplerTokenCount {
    #[prost(uint32, tag="1")]
    pub token: u32,
    #[prost(uint32, tag="2")]
    pub count: u32,
}
#[derive(Clone, PartialEq, ::prost::Message)]
pub struct SuffixTree {
    #[prost(uint32, tag="1")]
    pub token: u32,
    #[prost(uint32, tag="2")]
    pub depth: u32,
    #[prost(message, optional, tag="3")]
    pub sampler: ::core::option::Option<Sampler>,
    #[prost(message, repeated, tag="4")]
    pub prefixes: ::prost::alloc::vec::Vec<SuffixTree>,
}
#[derive(Clone, PartialEq, ::prost::Message)]
pub struct SuffixTreeSet {
    #[prost(uint32, tag="1")]
    pub size: u32,
    #[prost(uint32, tag="2")]
    pub depth: u32,
    #[prost(message, optional, tag="3")]
    pub sampler: ::core::option::Option<Sampler>,
    #[prost(message, repeated, tag="4")]
    pub prefixes: ::prost::alloc::vec::Vec<SuffixTree>,
}
// @@protoc_insertion_point(module)
