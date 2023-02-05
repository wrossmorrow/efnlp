from __future__ import annotations


from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import efnlp_pb2 as pb
from . import Sampler
from .util import read_binary_file


@dataclass
class SuffixTree:

    token: int  # token index
    depth: int = field(init=False)  # occurrences
    sampler: Sampler = field(init=False)
    children: Dict[int, SuffixTree] = field(init=False)  # "children" is a bad name

    def __post_init__(self) -> None:
        self.depth = 0
        self.sampler = Sampler()
        self.children = {}

    @staticmethod
    def from_proto_file(name: str) -> SuffixTree:
        data = read_binary_file(name)
        return SuffixTree.from_proto_bytes(data)

    @staticmethod
    def from_proto_bytes(data: bytes) -> SuffixTree:
        P = pb.SuffixTree()
        P.ParseFromString(data)
        return SuffixTree.from_proto(P)

    @staticmethod
    def from_proto(T: pb.SuffixTree) -> SuffixTree:
        t = SuffixTree(token=T.token)
        t.sampler = Sampler.from_proto(T.sampler)
        for c in T.prefixes:
            t.children[c.token] = SuffixTree.from_proto(c)
        return t

    @staticmethod
    def copy(T: SuffixTree) -> SuffixTree:
        S = SuffixTree(token=T.token)
        S.depth = T.depth
        S.sampler = Sampler.copy(T.sampler)
        S.children = {t: SuffixTree.copy(T.children[t]) for t in T}
        return S

    def proto(self) -> pb.SuffixTree:
        T = pb.SuffixTree(token=self.token)
        T.sampler.CopyFrom(self.sampler.proto())
        for _, c in self.children.items():
            T.prefixes.append(c.proto())
        return T

    def __bytes__(self) -> bytes:
        return self.proto().SerializeToString()

    def __add__(self, child: SuffixTree) -> SuffixTree:
        return self.add(child)

    def __contains__(self, token: int) -> bool:
        return token in self.children

    def __getitem__(self, token: int) -> SuffixTree:
        return self.children[token]

    def __setitem__(self, token: int, child: SuffixTree) -> SuffixTree:
        self.children[token] = child
        return self

    def __iter__(self):
        return self.children.__iter__()

    def __next__(self):
        return self.children.__next__()

    def __call__(self, prefix: List[int]) -> float:
        """Convenience for sampling."""
        return self.sample(prefix)

    def get(self, token: int) -> Optional[SuffixTree]:
        """Return the child with given token, or None."""
        return self.children.get(token)

    def add(self, child: SuffixTree) -> SuffixTree:
        """Add a "child" token in the children map (though "children"
        is a bit misleading in context). Chainable."""
        self.children[child.token] = child
        return self

    def parse(self, prefix: List[int], successor: int) -> SuffixTree:
        """Parse a prefix into this SuffixTree, including the successor
        token. Chainable."""
        self.sampler += successor
        if len(prefix) > 0:
            C = self.get(prefix[-1])
            if C is None:
                C = SuffixTree(prefix[-1])
                self[prefix[-1]] = C
            C.parse(prefix[:-1], successor)
            self.depth = max(self.depth, C.depth + 1)

        return self

    @staticmethod
    def merge_proto_bytes(a: bytes, b: bytes) -> SuffixTree:
        return SuffixTree.merge_trees(
            SuffixTree.from_proto_bytes(a), SuffixTree.from_proto_bytes(b)
        )

    @staticmethod
    def merge_proto(a: pb.SuffixTree, b: pb.SuffixTree) -> SuffixTree:
        return SuffixTree.merge_trees(SuffixTree.from_proto(a), SuffixTree.from_proto(b))

    @staticmethod
    def merge_trees(a: SuffixTree, b: SuffixTree) -> SuffixTree:
        return a.merge(b)

    def merge(self, other: SuffixTree) -> SuffixTree:
        """Merge another SuffixTree into this one"""
        assert self.token == other.token
        self.depth += max(self.depth, other.depth)
        self.sampler.merge(other.sampler)
        for t in self:
            if t in other:
                self.children[t].merge(other.children[t])
        for t in other:
            if t not in self:
                self.children[t] = SuffixTree.copy(other.children[t])
                # TODO: is a copy required? why not just reference?
        return self

    def memory(self) -> int:
        """Return an estimate of the memory requirements for this tree"""
        return self.sampler.memory() + sum([4 + c.memory() for t, c in self.children.items()])

    def prefixes(self) -> List[List[int]]:
        """List all prefixes held in this SuffixTree. These are
        basically the set of paths to leaf nodes from this node."""
        if len(self.children) == 0:
            return [[self.token]]
        return [(p + [self.token]) for _, c in self.children.items() for p in c.prefixes()]

    def patterns(self) -> List[Tuple[List[int], int]]:
        """List all "patterns" held in this SuffixTree. These are
        basically the set of paths to leaf nodes from this node,
        along with any successor tokens."""
        if len(self.children) == 0:
            return [([self.token], t) for t in self.sampler.counts]
        return [
            (p[0] + [self.token], p[1]) for _, c in self.children.items() for p in c.patterns()
        ]

    def search(self, prefix: List[int]) -> List[int]:
        """Search for a given prefix in this tree. Returns
        the longest match."""
        if (len(prefix) > 0) and (prefix[-1] in self):
            if len(prefix) == 1:
                return [prefix[-1], self.token]
            return self[prefix[-1]].search(prefix[:-1]) + [self.token]
        return [self.token]

    def match(self, prefix: List[int]) -> bool:
        """Return true if the presented prefix is in the suffix tree"""
        if len(prefix) == 0:
            raise ValueError("can't match the empty token string")
        if prefix[-1] in self:
            if len(prefix) == 1:
                return True
            return self[prefix[-1]].match(prefix[:-1])
        return False

    def sample(self, prefix: List[int]) -> int:
        """Sample a token that likely follows a prefix. Requires
        a normalized tree for now. Recurses to search for the
        longest matching suffix for the prefix."""
        if len(prefix) == 0 or prefix[-1] not in self:
            return self.sampler.sample()
        return self[prefix[-1]].sample(prefix[:-1])

    def probability(self, prefix: List[int], successor: int) -> float:
        """Return pattern probability. Basically suffix search
        but returning the probability of the longest match."""

        if len(prefix) == 0:
            return self.sampler.counts.get(successor, 0) / self.sampler.total

        # search children
        C = self.children.get(prefix[-1])
        if C is None:
            return self.sampler.counts.get(successor, 0) / self.sampler.total

        # recurse into matched child with the prefix's prefix
        return C.probability(prefix[:-1], successor)

        # TODO: verify


class SuffixTreeSet:

    # size: int  # "vocab" size
    # depth: int = field(init=False)
    # trees: Dict[int, SuffixTree] = field(init=False)
    # sampler: Sampler = field(init=False) # for counting raw token occurrences

    def __init__(self, size: int = 0) -> None:
        self.size: int = size
        self.depth: int = 0
        self.trees: Dict[int, SuffixTree] = {t: SuffixTree(t) for t in range(self.size)}
        self.sampler: Sampler = Sampler()

    @staticmethod
    def from_proto_file(name: str) -> SuffixTreeSet:
        data = read_binary_file(name)
        return SuffixTreeSet.from_proto_bytes(data)

    @staticmethod
    def from_proto_bytes(data: bytes) -> SuffixTreeSet:
        P = pb.SuffixTreeSet()
        P.ParseFromString(data)
        return SuffixTreeSet.from_proto(P)

    @staticmethod
    def from_proto(S: pb.SuffixTreeSet) -> SuffixTreeSet:
        s = SuffixTreeSet(size=len(S.prefixes))
        for c in S.prefixes:
            s.trees[c.token] = SuffixTree.from_proto(c)
        return s

    def proto(self) -> pb.SuffixTreeSet:
        S = pb.SuffixTreeSet()
        for _, c in self.trees.items():
            S.prefixes.append(c.proto())
        return S

    def __bytes__(self) -> bytes:
        return self.proto().SerializeToString()

    def __contains__(self, token: int) -> bool:
        return token in self.trees

    def __getitem__(self, token: int) -> SuffixTree:
        return self.trees[token]

    def __iter__(self):
        return self.trees.__iter__()

    def __next__(self):
        return self.trees.__next__()

    def items(self):
        return self.trees.items()

    def parse(self, prefix: List[int], successor: int) -> SuffixTreeSet:
        if len(prefix) == 0:
            raise ValueError("Cannot parse empty prefix")
        self.sampler += successor
        if prefix[-1] not in self.trees:
            self.trees[prefix[-1]] = SuffixTree(prefix[-1])
        self.trees[prefix[-1]].parse(prefix[:-1], successor)
        self.depth = max(self.depth, self.trees[prefix[-1]].depth + 1)
        return self

    def parse_all(
        self, tokens: List[int], block_size: int, ignore_start: bool = False
    ) -> SuffixTreeSet:
        if not ignore_start:
            for i in range(1, block_size):  # leading sub-block_size prefixes
                self.parse(tokens[0:i], tokens[i])
        for i in range(block_size, len(tokens) - 1):
            self.parse(tokens[i - block_size : i], tokens[i])
        return self

    def merge(self, other: SuffixTreeSet) -> SuffixTreeSet:
        self.depth = max(self.depth, other.depth)
        for t, tree in self.trees.items():
            if t in other:
                tree.merge(other[t])
        for t, tree in other.items():
            if t not in self:
                self.trees[t] = SuffixTree.copy(tree)
        return self

    def accumulate(self, *others: SuffixTreeSet) -> SuffixTreeSet:
        for other in others:
            self.merge(other)
        return self

    def memory(self) -> int:
        return self.sampler.memory() + sum([T.memory() for _, T in self.trees.items()])

    def prefixes(self, token: Optional[int] = None) -> List[List[int]]:
        if token is None:
            r = []
            for t, tree in self.items():
                r += tree.prefixes()
            return r
            # return [p for _, t in self.items() for p in t.prefixes()]
        return self.trees[token].prefixes()

    def patterns(self, token: Optional[int] = None) -> List[Tuple[List[int], int]]:
        if token is None:
            r = []
            for t in range(self.size):
                r += self.patterns(t)
            return r
        return self.trees[token].patterns()

    def search(self, prefix: List[int]) -> List[int]:
        if len(prefix) == 0:
            raise ValueError("can't search the empty token string")
        if prefix[-1] in self:
            return self.trees[prefix[-1]].search(prefix[:-1])
        return []

    def match(self, prefix: List[int]) -> bool:
        if len(prefix) == 0:
            raise ValueError("can't match the empty token string")
        if prefix[-1] in self:
            return self.trees[prefix[-1]].match(prefix[:-1])
        return False

    def sample(self, prefix: List[int] = []) -> int:
        if (len(prefix) == 0) or (prefix[-1] not in self.trees):
            return self.sampler.sample()  # sample from raw token occurrence frequencies
        return self.trees[prefix[-1]].sample(prefix[:-1])

    def probability(self, prefix: List[int], successor: int) -> float:
        if (len(prefix) == 0) or (prefix[-1] not in self.trees):
            return self.sampler.probability(
                successor
            )  # raw occurrence probability of the successor
        return self.trees[prefix[-1]].probability(prefix[:-1], successor)

    def generate(self, size: int, window: int, prompt: List[int]) -> List[int]:
        code = prompt
        for i in range(size):
            prefix = code if len(code) < window else code[-window:]
            code.append(self.sample(prefix)) # don't need to "allocate" lists
        return code
