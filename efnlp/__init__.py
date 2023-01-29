from __future__ import annotations

from dataclasses import dataclass, field
from random import random
from typing import Dict, List, Optional, Tuple, Union


@dataclass
class Sampler:
    
    total: int = field(init=False)
    counts: Dict[int, int] = field(init=False)

    def __post_init__(self) -> None:
        self.total = 0
        self.counts = {}

    def __add__(self, t: int) -> Sampler:
        return self.add(t)

    def __iadd__(self, t: int) -> Sampler:
        return self.add(t)

    def add(self, t: int) -> Sampler:
        self.total += 1
        if t in self.counts:
            self.counts[t] += 1
        else:
            self.counts[t] = 1
        return self

    def memory(self) -> int:
        return 4 + 2 * len(self.counts)

    def sample(self) -> int:
        r = self.total * random()
        for t, c in self.counts.items():
            if r < c:
                return t
            r -= c
        raise Exception("We should not be here, sampler malformed")


@dataclass
class SuffixTree:

    token: int  # token index
    count: int = field(init=False)  # occurrences
    children: Dict[int, SuffixTree] = field(init=False)  # "children" is a bad name
    sampler: Sampler = field(init=False)

    def __post_init__(self) -> None:
        self.count = 0
        self.children = {}
        self.sampler = Sampler()

    def __add__(self, child: SuffixTree) -> SuffixTree:
        return self.add(child)

    def __contains__(self, token: int) -> bool:
        return token in self.children

    def __getitem__(self, token: int) -> SuffixTree:
        return self.children[token]

    def __setitem__(self, token: int, child: SuffixTree) -> SuffixTree:
        self.children[token] = child
        return self

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
        return self

    def merge(self, other: SuffixTree) -> SuffixTree:
        """Merge another SuffixTree into this one"""
        assert self.token == other.token
        # merge overall target tokens and counts
        # then merge matching children
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
        if len(prefix) == 0:
            return [self.token]
        C = self.get(prefix[-1])
        if C is None:
            return [self.token]
        return C.search(prefix[:-1]) + [self.token]

    def match(self, prefix: List[int]) -> bool:
        """Return true if the presented prefix is in the suffix tree"""
        if len(prefix) == 0:
            raise ValueError("can't match the empty token string")

        C = self.get(prefix[-1])
        if C is None:
            return False

        if len(prefix) == 1:
            return True

        return C.match(prefix[:-1])

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


@dataclass
class SuffixTreeSet:

    size: int  # "vocab" size
    trees: Dict[int, SuffixTree] = field(init=False)

    def __post_init__(self) -> None:
        self.trees = {t: SuffixTree(t) for t in range(self.size)}

    def __getitem__(self, token: int) -> SuffixTree:
        return self.trees[token]

    def parse(self, prefix: List[int], target: int) -> SuffixTreeSet:
        if len(prefix) == 0:
            raise ValueError("Cannot parse empty prefix")
        self.trees[prefix[-1]].parse(prefix[:-1], target)
        return self

    def merge(self, other: SuffixTreeSet) -> SuffixTreeSet:
        assert self.size == other.size
        for i in range(self.size):
            self.trees[i].merge(other.trees[i])
        return self

    def memory(self) -> int:
        return sum([st.memory() for t, st in self.trees.items()])

    def prefixes(self, token: Optional[int] = None) -> List[List[int]]:
        if token is None:
            r = []
            for t in range(self.size):
                r += self.prefixes(t)
            return r
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
        return self.trees[prefix[-1]].search(prefix[:-1])

    def match(self, prefix: List[int]) -> bool:
        if len(prefix) == 0:
            raise ValueError("can't match the empty token string")
        return self.trees[prefix[-1]].match(prefix[:-1])

    def sample(self, prefix: List[int] = []) -> int:
        if len(prefix) == 0:  # sample from token marginals?
            return 0
        return self.trees[prefix[-1]].sample(prefix[:-1])

    def probability(self, prefix: List[int], successor: int) -> float:
        if len(prefix) == 0:  # TODO: raw count occurrence of the successor?
            return 0
        p = self.trees[prefix[-1]].probability(prefix[:-1], successor)
        if p > 0:
            return p
        return self.trees[prefix[-1]].probability(prefix[:-1], successor)

    def generate(self, size: int, window: int, prompt: List[int]) -> List[int]:
        code = prompt
        for i in range(size):
            prefix = code if len(code) < window else code[-window:]
            code.append(self.sample(prefix))
        return code


@dataclass
class CharLanguage:

    size: int
    stot: Dict[str, int]
    ttos: Dict[int, str]

    @staticmethod
    def from_corpus(C: str) -> CharLanguage:
        lang = sorted(list(set(c for c in C)))
        return CharLanguage(
            size=len(lang),
            stot={c: i for i, c in enumerate(lang)},
            ttos={i: c for i, c in enumerate(lang)},
        )

    def encode(self, s: str) -> List[int]:
        return [self.stot[s] for s in s]

    def decode(self, tokens: Union[int, List[int]]) -> str:
        if isinstance(tokens, list):
            return "".join(self.ttos[t] for t in tokens)
        return self.decode([tokens])
