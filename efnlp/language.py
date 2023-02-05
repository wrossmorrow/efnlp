from __future__ import annotations

# from dataclasses import dataclass
from io import StringIO
from json import dumps, loads
from typing import Dict, List

from . import efnlp_pb2 as pb
from . import SuffixEncoder
from .types import TokenType, ValueType
from .util import read_binary_file, write_binary_file


# suffix tree based byte-sequence encoding language
class Language:

    # name: str
    # size: int
    # depth: int  # max(suffixes[*].depth) + 1
    # suffixes: Dict[int, SuffixEncoder]
    # decoder: Dict[int, str] # token -> string

    def __init__(self, name: str = "", size: int = 0, depth: int = 0) -> None:
        self.name: str = name
        self.size: int = size
        self.depth: int = depth
        self.suffixes: Dict[ValueType, SuffixEncoder] = {}
        self.decoder: Dict[TokenType, str] = {}

    @staticmethod
    def from_proto_file(name: str) -> Language:
        data = read_binary_file(name)
        return Language.from_proto_bytes(data)

    @staticmethod
    def from_proto_bytes(data: bytes) -> Language:
        P = pb.Language()
        P.ParseFromString(data)
        return Language.from_proto(P)

    @staticmethod
    def from_proto(P: pb.Language) -> Language:
        L = Language(
            name=P.name,
            depth=P.stats.depth,
            size=P.stats.size,
        )
        L.suffixes = {p.value: SuffixEncoder.from_proto(p) for p in P.suffixes}
        L.decoder = {t: p for p, t in L.dict().items()}
        return L

    def proto(self) -> pb.Language:
        # TODO: version, options
        P = pb.Language(
            name=self.name,
            stats=pb.LanguageStats(
                size=self.size,
                depth=self.depth,
            ),
        )
        for _, e in self.suffixes.items():
            P.suffixes.append(e.proto())
        return P

    def __bytes__(self) -> bytes:
        return self.proto().SerializeToString()

    def dump(self, filename: str, compress: bool = True) -> None:
        write_binary_file(filename, bytes(self), compress=compress)

    @staticmethod
    def from_json_file(name: str) -> Language:
        with open(name, "r") as f:
            return Language.from_json(f.read())

    @staticmethod
    def from_json(J: str) -> Language:
        return Language.from_dict(loads(J))

    @staticmethod
    def from_dict(D: Dict, name: str = "") -> Language:
        # presume {prefix: token} dict, like OpenAI's at
        #
        #   https://openaipublic.blob.core.windows.net/gpt-2/encodings/main/encoder.json
        #
        L = Language(name=name)
        for p, t in D.items():
            L.define(p, t)  # sets depth
            L.size = max(L.size, t)  # presume tokens are sequential?
        L.decoder = {t: p for p, t in L.dict().items()}
        return L

    def dict(self) -> Dict[str, int]:
        return {p: t for _, e in self.suffixes.items() for p, t in e.dict().items()}

    def json(self) -> str:
        return dumps(self.dict())

    def encodables(self) -> List[ValueType]:
        return [p for _, p in self.decoder.items()]

    def define(self, p: bytes | str, t: int) -> Language:
        if len(p) == 0:
            raise ValueError("cannot define an encoder for an empty string")
        if isinstance(p, bytes):
            p = p.decode("utf-8")  # assert utf-8 encoding
        if p[-1] not in self.suffixes:
            self.suffixes[p[-1]] = SuffixEncoder(p[-1])
        depth = self.suffixes[p[-1]].define(p[:-1], t) + 1
        self.depth = max(self.depth, depth)
        return self

    def decode(
        self, seq: TokenType | List[TokenType], ignore_errors: bool = False, join: bool = False
    ) -> str:

        # join is slightly slower (maybe 30% slower) than a StringIO style builder
        # we'll keep the code, but default to stream style creation in decoding

        if isinstance(seq, TokenType):
            return self.decode([seq], ignore_errors=ignore_errors, join=join)

        if join:
            if ignore_errors:
                return "".join([self.decoder.get(t, "") for t in seq])
            return "".join([self.decoder[t] for t in seq])

        builder = StringIO()
        if ignore_errors:
            for t in seq:
                builder.write(self.decoder.get(t, ""))
        else:
            for t in seq:
                builder.write(self.decoder[t])
        return builder.getvalue()

    def encode(self, s: str | bytes, ignore_errors: bool = False) -> List[int]:

        # work with UTIF-8 strings
        if isinstance(s, bytes):
            s = s.decode("utf-8")  # TODO: errors=? (ie UTF-8 encoding error behavior)

        # If we _don't_ have to use tree search, don't. That is, if all encodable
        # suffixes are UTF-8 chars, use a simpler and faster method. HOWEVER, this
        # means the Language depth _must_ be correct for encoding to work.
        if self.depth == 1:
            return self._encode_flat(s, ignore_errors=ignore_errors)

        print("using deep search")

        # If we do have to use multi-character suffixes, we have to use an expensive
        # backwards search. (Well, expensive as written and in python. This is fast
        # in go, for example.)
        return self._encode_deep(s, ignore_errors=ignore_errors)

    def _encode_flat(self, s: str, ignore_errors: bool = False) -> List[int]:
        if ignore_errors:
            result: List[int] = []
            for c in s:
                if c in self.suffixes:
                    result.append(self.suffixes[c].token)
            return result
        try:
            return [self.suffixes[c].token for c in s]
        except KeyError as err:
            raise ValueError(f"An unencodable UTF-8 character ({err}) was found.")

    def _encode_deep(self, s: str, ignore_errors: bool = False) -> List[int]:
        result: List[int] = []
        i = len(s) - 1
        while i >= 0:
            if s[i] in self.suffixes:
                t, c = self.suffixes[s[i]].encode(s[:i])  # reference? avoid copy
                result.insert(0, t)  # we're working backward...
                i -= c  # move backward by bytes matched
            else:
                if not ignore_errors:
                    p = max(i - self.depth, 0)
                    raise ValueError(
                        f'sequence "...{s[p:i+1]}"',
                        f"starting at position {i} is not encodable",
                    )
                i -= 1  # is one byte enough? seems arbitrary...
        return result

    # # TODO: need (lru-)cachable encodings? The trouble with a suffix tree
    # # approach is _what_ substring to look up is unclear. If we want the
    # # logest ("stable") match, we have to use trees to "order" the keys.
    # def _encode(self, s: bytes, strict: bool = True) -> int:
    #     if s in self.suffixes:
    #         t, c = self.suffixes[s[i]].encode(s[:i])  # reference? avoid copy
    #         # print(f"  matched \"{s[:i-c+1].decode()}|{s[i-c+1:i+1].decode()}|{s[i+1:].decode()}\" ({t}, {c})")
    #         result[C] = t
    #         i -= c  # move backward by bytes matched
    #         C -= 1  # increment encoding count
    #     else:
    #         if strict:
    #             p = max(i-self.depth,0)
    #             raise ValueError(
    #                 f'sequence "{s[p:i+1].decode()}..."',
    #                 f"starting at position {i} is not encodable",
    #             )
    #         i -= 1  # is one enough?
    #     result = result[C + 1 :]  # we've only stored this many tokens (copy?)
    #     return result
