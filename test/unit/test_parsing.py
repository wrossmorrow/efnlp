import pytest

from os.path import dirname
from random import randint
from typing import List

from efnlp import Language, SuffixTreeSet

from .conftest import Timer


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
def test_parsing_is_complete_abstract(L: int, B: int) -> None:

    # generate a covering corpus
    C = covering_corpus(L)
    Cs = "".join(str(t) for t in C)
    N = len(C)

    # parse a suffix tree
    S = SuffixTreeSet().parse_all(C, B)

    # every B-element substring in the corpus is in the tree(s)
    for i in range(B, N - 1):
        assert S.match(C[i - B : i])
        for b in range(B):
            assert C[i - B + b : i] == S.search(C[i - B + b : i])

    # every pattern (prefix, successor) in the corpus is in the tree(s)
    # we can assess this by demonstrating a positive probability
    for i in range(B, N - 1):
        for b in range(B):
            p = C[i - B + b : i]
            P = S.probability(p, C[i])
            assert P > 0

    # every B-element prefix stored is actually in the corpus
    for p in S.prefixes():
        ps = "".join(str(t) for t in p)
        assert ps in Cs, f"prefix {ps} was not found in corpus"

    # every B+1-element pattern stored is actually in the corpus
    for q in S.patterns():
        ps = "".join(str(t) for t in q[0]) + str(q[1])
        assert ps in Cs, f"prefix {ps} was not found in corpus"


# @pytest.mark.skip(reason="temporary")
def test_parsing_is_complete_shakespeare_charlang() -> None:

    block_size = 5

    corpus = ""
    with open("data/tinywillspeare.txt", "r") as f:
        corpus = f.read()

    assert len(corpus) > 0

    # make a character language
    with Timer() as T:
        characters = sorted(list(set(corpus)))
        lang_dict = {c: t for t, c in enumerate(characters)}
        language = Language.from_dict(lang_dict)
    T.log_us("created char language")

    # encode text corpus
    with Timer() as T:
        encoded = language.encode(corpus)
    T.log_us("encoded corpus")

    # parse a suffix tree
    S = SuffixTreeSet()
    with Timer() as T:
        S.parse_all(encoded, block_size)
    T.log_us("parsed tree")

    # every B-element substring in the corpus is in the tree(s)
    for i in range(block_size, len(encoded) - 1):
        prefix = encoded[i - block_size : i]
        assert S.match(prefix)
        for b in range(block_size):
            prefix = encoded[i - block_size + b : i]
            assert prefix == S.search(prefix)

    # every B-element prefix stored is actually in the corpus
    for p in S.prefixes():
        ps = language.decode(p)
        assert ps in corpus, f'prefix "{ps}" was not found in corpus'

    # every B+1-element pattern stored is actually in the corpus
    for q in S.patterns():
        ps = language.decode(q[0] + [q[1]])
        assert ps in corpus, f"prefix {ps} was not found in corpus"

    # every B+1-element substring in the corpus is in the tree(s)
    for i in range(block_size, len(encoded) - 1):
        for b in range(block_size):
            prefix, successor = encoded[i - block_size + b : i], encoded[i]
            P = S.probability(prefix, successor)
            assert P > 0


# @pytest.mark.skip(reason="temporary")
def test_parsing_is_complete_shakespeare_gpt_2() -> None:

    block_size = 5

    corpus = ""
    with open("data/tinywillspeare.txt", "r") as f:
        corpus = f.read()

    assert len(corpus) > 0

    # read the language
    with Timer() as T:
        name = f"{dirname(__file__)}/data/gpt-2.json"
        language = Language.from_json_file(name)
    T.log_us("created gpt-2 language")

    # encode text corpus
    with Timer() as T:
        encoded = language.encode(corpus)
    T.log_us("encoded corpus")

    # parse a suffix tree
    S = SuffixTreeSet()
    with Timer() as T:
        S.parse_all(encoded, block_size)
    T.log_us("parsed tree")

    # every B-element substring in the corpus is in the tree(s)
    for i in range(block_size, len(encoded) - 1):
        prefix = encoded[i - block_size : i]
        assert S.match(prefix)
        for b in range(block_size):
            prefix = encoded[i - block_size + b : i]
            assert prefix == S.search(prefix)

    # every B-element prefix stored is actually in the corpus
    for p in S.prefixes():
        ps = language.decode(p)
        assert ps in corpus, f'prefix "{ps}" was not found in corpus'

    # every B+1-element pattern stored is actually in the corpus
    for q in S.patterns():
        ps = language.decode(q[0] + [q[1]])
        assert ps in corpus, f"prefix {ps} was not found in corpus"

    # every B+1-element substring in the corpus is in the tree(s)
    for i in range(block_size, len(encoded) - 1):
        for b in range(block_size):
            prefix, successor = encoded[i - block_size + b : i], encoded[i]
            P = S.probability(prefix, successor)
            assert P > 0


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
    S = SuffixTreeSet(L).parse_all(C, B)

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
def test_tree_is_mergeable(L: int, B: int, T: int) -> None:

    # generate some covering corpuses
    Cs = [covering_corpus(L) for _ in range(3)]

    # parse suffix trees
    Ss = [SuffixTreeSet(L).parse_all(C, B) for C in Cs]

    # verify the parsed results (repetitive but ok)
    for C, S in zip(Cs, Ss):
        for i in range(B, len(C) - 1):
            assert S.match(C[i - B : i]), (C[i - B : i], S.search(C[i - B : i]))

    # merge all the trees (novel)
    S = SuffixTreeSet(L)
    for s in Ss:
        S.merge(s)

    # every B-element substring in both corpuses is in the merged tree
    # while _some_ prefix missing from every pre-merged tree
    for C in Cs:
        assert all([S.match(C[i - B : i]) for i in range(B, len(C) - 1)])
        assert any([not s.match(C[i - B : i]) for i in range(B, len(C) - 1) for s in Ss])
