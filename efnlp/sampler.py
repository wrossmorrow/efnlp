from __future__ import annotations

from random import random
from typing import Dict, Optional

from . import efnlp_pb2 as pb
from .util import read_binary_file


class Sampler:

    # total: int
    # counts: Dict[int, int]

    def __init__(self, total: Optional[int] = 0, counts: Optional[Dict[int, int]] = None) -> None:
        self.total: int = total or 0
        self.counts: Dict[int, int] = {} if counts is None else {t: c for t, c in counts.items()}

    @staticmethod
    def from_proto_file(name: str) -> Sampler:
        data = read_binary_file(name)
        return Sampler.from_proto_bytes(data)

    @staticmethod
    def from_proto_bytes(data: bytes) -> Sampler:
        assert isinstance(data, bytes)
        P = pb.Sampler()
        P.ParseFromString(data)
        return Sampler.from_proto(P)

    @staticmethod
    def from_proto(S: pb.Sampler) -> Sampler:
        assert isinstance(S, pb.Sampler), (type(S), S)
        s = Sampler(total=S.total)
        s.counts = {stc.token: stc.count for stc in S.counts}
        return s

    @staticmethod
    def copy(S: Sampler) -> Sampler:
        return Sampler(total=S.total, counts=S.counts)

    def proto(self) -> pb.Sampler:
        S = pb.Sampler(total=self.total)
        for t, c in self.counts.items():
            stc = pb.SamplerTokenCount(token=t, count=c)
            S.counts.append(stc)
        return S

    def __bytes__(self) -> bytes:
        return self.proto().SerializeToString()

    def __contains__(self, token: int) -> bool:
        return token in self.counts

    def __add__(self, t: int) -> Sampler:
        return self.add(t)

    def __iadd__(self, t: int) -> Sampler:
        return self.add(t)

    def __getitem__(self, t: int) -> int:
        return self.counts[t]

    def get(self, t: int, default: int = 0) -> int:
        return self.counts.get(t, default)

    def items(self):  # -> List[Tuple[int, int]]:
        return self.counts.items()

    def __iter__(self):
        return self.counts.__iter__()

    def __next__(self):
        return self.counts.__next__()

    def add(self, t: int) -> Sampler:
        self.total += 1
        if t in self.counts:
            self.counts[t] += 1
        else:
            self.counts[t] = 1
        return self

    def memory(self) -> int:
        return 4 + 2 * len(self.counts)

    def merge(self, other: Sampler) -> Sampler:
        self.total += other.total
        for t in self.counts:
            self.counts[t] += other.get(t)
        for t in other:
            if t not in self.counts:
                self.counts[t] = other[t]
        return self

    def sample(self) -> int:
        r = self.total * random()
        for t, c in self.counts.items():
            if r < c:
                return t
            r -= c
        raise Exception("We should not be here, sampler malformed")

    def probability(self, token: int) -> float:
        return self.counts.get(token, 0) / self.total
