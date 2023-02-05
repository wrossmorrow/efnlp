import pytest  # noqa: F401

from json import loads
from os import remove
from os.path import dirname
from random import choices
from string import ascii_letters, digits
from typing import List
from uuid import uuid4

import efnlp

from .conftest import Timer


@pytest.mark.parametrize(
    "prefixes, unknown",
    (
        (["aaa", "aab", "aa", "a", "b"], ["?"]),
        (["aaa", "aab", "aa", "a"], ["?"]),
        (["aa", "ab", "a"], ["?"]),
        # NOT ENCODABLE with greedy forwards prefix search. Specifically, consider:
        #
        #   aab ~ |a|ab| ~ 2,1
        #
        # A greedy (longest match) forwards prefix search will parse
        #
        #   aab -> |aa|b -> ?
        #
        # before getting "stuck" at "b". Note that a greedy backwards suffix search
        # works:
        #
        #   aab ~ |a|ab| ~ 2,1
        #
        (["aa", "ba", "a"], ["?"]),
        # NOT ENCODABLE with greedy backwards suffix search. Specifically, consider:
        #
        #   baa ~ |ba|a| ~ 1,2
        #
        # A greedy (longest match) backwards suffix search will parse
        #
        #   baa -> b|aa| -> ?
        #
        # before getting stuck at "b". Note that a greedy forward prefix search
        # works:
        #
        #   baa -> |ba|a ~ |ba|a| ~ 1,2
        #
        ([c for c in (ascii_letters + digits)], ["?"]),
    ),
)
def test_language_ascii(prefixes: List[str], unknown: List[str]) -> None:

    # create string-token mapping from test inputs
    D = {s: i for i, s in enumerate(prefixes)}

    # initialize an EncoderSet from that mapping
    E = efnlp.Language.from_dict(D)

    # we should have the same thing
    assert E.dict() == D
    assert E.depth == max(len(k) for k in D)

    # all the declared strings match declared tokens
    for p, t in D.items():
        assert E.encode(p) == [t], (p, t, E.encode(p))

    # invalid character raises in strict mode
    for c in unknown:
        with pytest.raises(ValueError):
            E.encode(c)

    # decoding encoded strings is a no-op
    for _ in range(10):
        s = "".join(choices(prefixes, k=100))
        assert E.decode(E.encode(s)) == s

    # non-strict mode ignores unknown characters
    for _ in range(10):
        s = "".join(choices(prefixes + unknown, k=100))
        r = "".join([c for c in s if c not in unknown])
        assert E.decode(E.encode(s, ignore_errors=True)) == r


@pytest.mark.parametrize(
    "prefixes, unknown",
    (
        (["aaa", "aab", "aa", "a", "b"], ["?"]),
        (["aaa", "aab", "aa", "a"], ["?"]),
        ([c for c in (ascii_letters + digits)], ["?"]),
    ),
)
def test_language_proto(prefixes: List[str], unknown: List[str]) -> None:

    # create string-token mapping from test inputs
    D = {s: i for i, s in enumerate(prefixes)}

    # initialize an EncoderSet from that mapping
    L = efnlp.Language.from_dict(D)

    # recompose from proto, and run easy test of equality (if unfocused
    # by including dict transform)
    M = efnlp.Language.from_proto(L.proto())
    assert L.dict() == M.dict()

    # recompose as proto bytes and test
    M = efnlp.Language.from_proto_bytes(bytes(L))
    assert L.dict() == M.dict()

    # recompose as proto file and test

    filename = f"{dirname(__file__)}/{str(uuid4())}"
    L.dump(filename, compress=False)
    M = efnlp.Language.from_proto_file(filename)
    assert L.dict() == M.dict()
    remove(filename)

    L.dump(filename, compress=True)
    M = efnlp.Language.from_proto_file(f"{filename}.gz")
    assert L.dict() == M.dict()
    remove(f"{filename}.gz")


def test_language_gpt2() -> None:

    GPT = ""
    with open(f"{dirname(__file__)}/data/gpt-2.json", "r") as f:
        GPT = f.read()

    D = loads(GPT)
    L = efnlp.Language.from_json(GPT)

    assert L.dict() == D
    assert len(D) == len(L.dict())

    Ps = L.encodables()
    for _ in range(10):
        s = "".join(choices(Ps, k=100))

        with Timer() as T:
            e = L.encode(s)
        T.log_us("encoded sample")

        with Timer() as T:
            d = L.decode(e)
        T.log_us("decoded sample")

        assert d == s

    filename = f"{dirname(__file__)}/{str(uuid4())}"

    with Timer() as T:
        L.dump(filename, compress=False)
    T.log_us("dumped proto (uncompressed)")

    with Timer() as T:
        M = efnlp.Language.from_proto_file(filename)
    T.log_us("re-read proto (uncompressed)")

    assert L.dict() == M.dict()
    remove(filename)

    with Timer() as T:
        L.dump(filename, compress=True)
    T.log_us("dumped proto (compressed)")

    with Timer() as T:
        M = efnlp.Language.from_proto_file(f"{filename}.gz")
    T.log_us("re-read proto (compressed)")

    assert L.dict() == M.dict()
    remove(f"{filename}.gz")
