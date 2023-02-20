pub type TokenType = u16;
pub type ProtoBytes = Vec<u8>;

pub mod pb {
    include!("efnlp.v1alpha1.rs");
}
