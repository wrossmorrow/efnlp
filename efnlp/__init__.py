from __future__ import annotations

from dataclasses import dataclass, field
from random import choices
from typing import Dict, List, Optional, Tuple, Union


@dataclass
class Target:

    token: int
    count: int = field(init=False)
    probability: float = field(init=False)

    def __post_init__(self) -> None:
        self.count = 1
        self.probability = 0.0

    def increment(self) -> Target:
        self.count += 1
        return self

    def normalize(self, total: float) -> Target:
        self.probability = self.count / total
        return self


@dataclass
class SuffixTree:

    token: int  # token index
    count: int = field(init=False)  # occurrences
    children: Dict[int, SuffixTree] = field(init=False)  # "children" is a bad name
    nexts: Dict[int, Target] = field(init=False)
    sampler: Tuple[List[int], List[float]] = field(init=False)  # normalized weights needed?

    def __post_init__(self) -> None:
        self.count = 0
        self.children = {}
        self.nexts = {}
        self.sampler = ([], [])

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

        if successor in self.nexts:
            self.nexts[successor].increment()
        else:
            self.nexts[successor] = Target(successor)

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

    def normalize(self) -> SuffixTree:
        """Construct probabilities, recursively. Chainable."""
        self._normalize()
        for _, c in self.children.items():
            c.normalize()
        return self

    def _normalize(self) -> None:
        """Internal: construct probabilities for this node only."""
        s = 0
        for _, t in self.nexts.items():
            s += t.count
        for _, t in self.nexts.items():
            t.normalize(s)
        self.sampler = (
            [t for t in self.nexts],
            [t.probability for _, t in self.nexts.items()],
        )

    def memory(self) -> int:
        """Return an estimate of the memory requirements for this tree"""
        return 16 * len(self.nexts) + sum([c.memory() for _, c in self.children.items()])

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
            return [([self.token], t) for t in self.nexts]
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
            return choices(self.sampler[0], weights=self.sampler[1], k=1)[0]
        return self[prefix[-1]].sample(prefix[:-1])

    def empfreq(self, prefix: List[int]) -> Tuple[List[int], List[float]]:
        """Return empirical frequencies. Equivalent to sampling
        in structure, except that we don't sample, we return the
        successor tokens and their probabilities."""
        if len(prefix) == 0 or prefix[-1] not in self:  # sample from children?
            return self.sampler[0], self.sampler[1]
        return self[prefix[-1]].empfreq(prefix[:-1])

    def probability(self, prefix: List[int], successor: int) -> float:
        """Return pattern probability. Basically suffix search
        but returning the probability of the longest match."""

        if len(prefix) == 0:
            return self.nexts[successor].probability if successor in self.nexts else 0.0

        # search children
        C = self.get(prefix[-1])
        if C is None:
            return 0.0  # no match in this prefix, probability zero

        # recurse into matched child with the prefix's prefix
        p = C.probability(prefix[:-1], successor)
        if p > 0.0:
            return p

        # child has no match
        return self.nexts[successor].probability if successor in self.nexts else 0.0


@dataclass
class SuffixTreeSet:

    size: int  # "vocab" size
    trees: List[SuffixTree] = field(init=False)

    def __post_init__(self) -> None:
        self.trees = [SuffixTree(t) for t in range(self.size)]

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
        return sum([t.memory() for t in self.trees])

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

    def normalize(self) -> SuffixTreeSet:
        for t in self.trees:
            t.normalize()
        return self

    def sample(self, prefix: List[int] = []) -> int:
        if len(prefix) == 0:  # sample from token marginals?
            return 0
        return self.trees[prefix[-1]].sample(prefix[:-1])

    def empfreq(self, prefix: List[int] = []) -> Tuple[List[int], List[float]]:
        if len(prefix) == 0:  # sample from token marginals?
            return [], []
        return self.trees[prefix[-1]].empfreq(prefix[:-1])

    def probability(self, prefix: List[int], successor: int) -> float:
        if len(prefix) == 0:  # raw count occurrence of the successor
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
