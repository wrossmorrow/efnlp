import pytest

from random import randint
from typing import List

from efnlp import SuffixTreeSet


def covering_corpus(L: int) -> List[int]:
    C = [randint(0, L - 1) for k in range(10 * L)]
    while len(set(C)) < L:
        C += [randint(0, L - 1) for k in range(10 * L)]
    return C


@pytest.mark.parametrize(
    "L",
    (
        10,
        25,
        65,
    ),
)
@pytest.mark.parametrize("B", (3, 5, 7))
def test_parsing_is_complete(L: int, B: int) -> None:

    # generate a covering corpus
    C = covering_corpus(L)
    Cs = ",".join(str(t) for t in C)
    N = len(C)

    # parse a suffix tree
    S = SuffixTreeSet(L)
    for i in range(B, N - 1):
        S.parse(C[i - B : i], C[i])

    # every B-element prefix stored is actually in the corpus
    for p in S.prefixes():
        ps = ",".join(str(t) for t in p)
        assert ps in Cs, f"prefix {ps} was not found in corpus"

    # every B+1-element pattern stored is actually in the corpus
    for q in S.patterns():
        ps = ",".join(str(t) for t in q[0]) + "," + str(q[1])
        assert ps in Cs, f"prefix {ps} was not found in corpus"

    # every B-element substring in the corpus is in the tree(s)
    for i in range(B, N - 1):
        assert S.match(C[i - B : i])
        for b in range(B):
            assert C[i - B + b : i] == S.search(C[i - B + b : i])

    # # every B+1-element substring in the corpus is in the tree(s)
    # for i in range(B, N-1):
    #     assert S.match(C[i-B:i])
    #     for b in range(B):
    #     	assert C[i-B+b:i] == S.search(C[i-B+b:i])


@pytest.mark.parametrize(
    "L",
    (
        10,
        25,
        65,
    ),
)
@pytest.mark.parametrize("B", (3, 5, 7))
def test_tree_is_searchable(L: int, B: int) -> None:

    # generate a covering corpus
    C = covering_corpus(L)
    N = len(C)

    # parse a suffix tree
    S = SuffixTreeSet(L)
    for i in range(B, N - 1):
        S.parse(C[i - B : i], C[i])

    # every B-element substring in the corpus is in the tree(s)
    for i in range(B, N - 1):
        assert S.match(C[i - B : i])
        for b in range(B):
            assert C[i - B + b : i] == S.search(C[i - B + b : i])


@pytest.mark.parametrize(
    "L",
    (
        10,
        25,
        65,
    ),
)
@pytest.mark.parametrize("B", (3, 5, 7))
@pytest.mark.parametrize(
    "T",
    (
        10,
        50,
        100,
    ),
)
def test_tree_is_sampleable(L: int, B: int, T: int) -> None:

    # generate a covering corpus
    C = covering_corpus(L)
    N = len(C)

    # parse a suffix tree
    S = SuffixTreeSet(L)
    for i in range(B, N - 1):
        S.parse(C[i - B : i], C[i])

    # sample
    codes = S.generate(T, B, [0])
    assert all(0 <= c for c in codes)
    assert all(c < L for c in codes)
