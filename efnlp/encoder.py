from __future__ import annotations

from json import dumps, loads

from typing import cast, Dict, Optional, Tuple

from . import efnlp_pb2 as pb
from .types import TokenType, ValueType
from .util import read_binary_file


class SuffixEncoder:
    # depth: int # max(prefixes[*].depth) + 1
    # value: str # bytes?
    # token: int
    # prefixes: Dict[str, SuffixEncoder]

    def __init__(self, value: ValueType) -> None:
        self.value: ValueType = value  # really a bytes[0]
        self.depth: int = 0
        self.token: int = -1  # signals "in-path" bytes, as opposed to "atoms"
        # self.atom = False
        self.prefixes: Dict[ValueType, SuffixEncoder] = {}

    @staticmethod
    def from_proto_file(name: str) -> SuffixEncoder:
        data = read_binary_file(name)
        return SuffixEncoder.from_proto_bytes(data)

    @staticmethod
    def from_proto_bytes(data: bytes) -> SuffixEncoder:
        P = pb.SuffixEncoder()
        P.ParseFromString(data)
        return SuffixEncoder.from_proto(P)

    @staticmethod
    def from_proto(P: pb.SuffixEncoder) -> SuffixEncoder:
        E = SuffixEncoder(P.value)  # self.token = -1
        E.depth = P.depth
        # E.atom = P.atom
        if P.atom:  # ignore token if atom == false
            E.token = P.token
        for p in P.prefixes:
            E.prefixes[p.value] = SuffixEncoder.from_proto(p)
        return E

    def proto(self) -> pb.SuffixEncoder:
        P = pb.SuffixEncoder(
            value=self.value,
            depth=self.depth,
            token=max(self.token, 0),  # ignored if atom == true
            atom=(self.token >= 0),
        )
        for _, e in self.prefixes.items():
            P.prefixes.append(e.proto())
        return P

    def __bytes__(self) -> bytes:
        return self.proto().SerializeToString()

    @staticmethod
    def from_json(J: str) -> SuffixEncoder:
        return SuffixEncoder.from_dict(loads(J))

    @staticmethod
    def from_dict(D: Dict[ValueType, int]) -> SuffixEncoder:
        v: Optional[ValueType] = None
        for p, t in D.items():
            assert len(p) > 0
            v = p[-1]
            if v is None:
                v = p[-1]
            else:
                assert v == p[-1]
        E = SuffixEncoder(cast(ValueType, v))
        for p, t in D.items():
            E.define(p[1:], t)
        return E

    def dict(self) -> Dict[ValueType, int]:
        v = self.value
        D = {(p + v): t for _, e in self.prefixes.items() for p, t in e.dict().items()}
        if self.token >= 0:  # an "atom" only if set >= 0
            D[v] = self.token
        return D

    def json(self) -> str:
        return dumps(self.dict())

    def define(self, p: ValueType, t: int) -> int:
        if len(p) == 0:
            self.token = t
            # self.atom = True
            return 0
        # initialize a suffix Encoder if not defined
        if p[-1] not in self.prefixes:
            self.prefixes[p[-1]] = SuffixEncoder(p[-1])
        # recursively define, and set depth in this Encoder (depth of longest
        # subpath)
        depth = self.prefixes[p[-1]].define(p[:-1], t) + 1
        self.depth = max(self.depth, depth)
        return self.depth

    def encode(self, p: ValueType) -> Tuple[TokenType, int]:
        # if we've called with an empty string (see below) we have
        # hit a search limit, and should return this Encoder's token.
        if len(p) == 0 or len(self.prefixes) == 0:
            return (self.token, 1)
        # if we can't search further (b["-1"] is the most recent
        # match, where "-1" here doesn't mean reverse indexing), then
        # we need to return with this token.
        if p[-1] not in self.prefixes:
            return (self.token, 1)
        # b[0] is in some encodable suffix of this element, so we need
        # to recurse to find a match. We can only get a valid response
        # here, but we have to increment the "depth" of the response to
        # match the recursion and move forward the "cursor" in a caller.
        result = self.prefixes[p[-1]].encode(p[:-1])
        if result[0] == -1:  # didn't _actually_ find a defined match
            return (self.token, 1)
        return (result[0], result[1] + 1)

    # def encode_idx(self, s: str, i: int) -> Optional[Tuple[int, int]]:
    #     if i >= len(s):
    #         return None
    #     if s[i] not in self.prefixes:
    #         return (self.token, i + 1)
    #     return self.prefixes[s[i]].encode_idx(s, i + 1)
