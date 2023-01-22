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
    children: Dict[int, SuffixTree] = field(init=False)  # "children" is a bad name
    nexts: Dict[int, Target] = field(init=False)
    sampler: Tuple[List[int], List[float]] = field(init=False)  # normalized weights needed?

    def __post_init__(self) -> None:
        self.children = {}
        self.nexts = {}
        self.sampler = ([], [])

    def __add__(self, child: SuffixTree) -> SuffixTree:
        return self.add(child)

    def __contains__(self, token: int) -> bool:
        return token in self.children

    def __getitem__(self, token: int) -> SuffixTree:
        return self.children[token]

    def __setitem__(self, token: int, value: SuffixTree) -> SuffixTree:
        self.children[token] = value
        return self

    def __call__(self, seq: List[int]) -> float:
        return 0.0

    def get(self, token: int) -> Optional[SuffixTree]:
        return self.children.get(token)

    def add(self, child: SuffixTree) -> SuffixTree:
        self.children[child.token] = child
        return self

    def parse(self, prefix: List[int], token: int) -> SuffixTree:

        if token in self.nexts:
            self.nexts[token].increment()
        else:
            self.nexts[token] = Target(token)

        if len(prefix) > 0:
            C = self.get(prefix[-1])
            if C is None:
                C = SuffixTree(prefix[-1])
                self[prefix[-1]] = C
            C.parse(prefix[:-1], token)

        return self

    def memory(self) -> int:
        return 16 * len(self.nexts) + sum([c.memory() for _, c in self.children.items()])

    def prefixes(self) -> List[List[int]]:
        if len(self.children) == 0:
            return [[self.token]]
        return [(p + [self.token]) for _, c in self.children.items() for p in c.prefixes()]

    def patterns(self) -> List[Tuple[List[int], int]]:
        if len(self.children) == 0:
            return [([self.token], t) for t in self.nexts]
        return [
            (p[0] + [self.token], p[1]) for _, c in self.children.items() for p in c.patterns()
        ]

    def search(self, prefix: List[int]) -> List[int]:
        if len(prefix) == 0:
            return [self.token]
        C = self.get(prefix[-1])
        return (C.search(prefix[:-1]) + [prefix[-1]]) if C is not None else [self.token]

    def normalize(self) -> SuffixTree:
        self._normalize()
        for _, c in self.children.items():
            c.normalize()
        return self

    def _normalize(self) -> None:
        s = 0
        for _, t in self.nexts.items():
            s += t.count
        for _, t in self.nexts.items():
            t.normalize(s)
        self.sampler = (
            [t for t in self.nexts],
            [t.probability for _, t in self.nexts.items()],
        )

    def sample(self, prefix: List[int]) -> int:
        if len(prefix) == 0 or prefix[-1] not in self:  # sample from children?
            return choices(self.sampler[0], weights=self.sampler[1], k=1)[0]
        return self[prefix[-1]].sample(prefix[:-1])

    def empfreq(self, prefix: List[int]) -> Tuple[List[int], List[float]]:
        if len(prefix) == 0 or prefix[-1] not in self:  # sample from children?
            return self.sampler[0], self.sampler[1]
        return self[prefix[-1]].empfreq(prefix[:-1])


@dataclass
class SuffixTreeSet:

    size: int
    trees: List[SuffixTree] = field(init=False)

    def __post_init__(self) -> None:
        self.trees = [SuffixTree(t) for t in range(self.size)]

    def __getitem__(self, token: int) -> SuffixTree:
        return self.trees[token]

    def parse(self, prefix: List[int], target: int) -> SuffixTreeSet:
        if len(prefix) > 0:
            self.trees[prefix[-1]].parse(prefix[:-1], target)
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
