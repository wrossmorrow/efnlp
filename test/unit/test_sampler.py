import pytest  # noqa: F401

from collections import Counter
from random import random, randint

from efnlp import Sampler

from .conftest import Timer


def test_sampler() -> None:

    weights = [randint(1, 100) for _ in range(10)]
    total = sum(weights)
    probs = [w / total for w in weights]

    S = Sampler()
    for i, w in enumerate(weights):
        for _ in range(w):
            S += i

    tokens = 1000000
    with Timer() as T:
        samples = [S.sample() for _ in range(tokens)]
    smpl_time = T.duration / tokens

    counted = Counter(samples)
    scount = [p[1] for p in sorted([(i, c) for i, c in counted.items()], key=lambda C: C[0])]
    stotal = sum(scount)
    sprobs = [c / stotal for c in scount]

    diffs = [abs(p - sprobs[i]) for i, p in enumerate(probs)]

    print(f"{smpl_time*1e6} us/sample, max prob diff: {max(diffs)}")

    assert max(diffs) <= 0.001, diffs


def test_sampler_proto() -> None:

    S = Sampler()
    for i, w in enumerate([randint(1, 100) for _ in range(10)]):
        for _ in range(w):
            S += i

    R = Sampler.from_proto(S.proto())
    assert S.total == R.total
    assert all([R.counts[t] == c for t, c in S.counts.items()])

    R = Sampler.from_proto_bytes(bytes(S))
    assert S.total == R.total
    assert all([R.counts[t] == c for t, c in S.counts.items()])

    # TODO: proto_files


def test_sampler_iter() -> None:

    S = Sampler()
    for i, w in enumerate([randint(1, 100) for _ in range(10)]):
        for _ in range(w):
            S += i

    # TODO: assertions


def test_sampler_merge() -> None:

    S = Sampler()
    for i, w in enumerate([randint(1, 100) for _ in range(10) if random() < 0.5]):
        for _ in range(w):
            S += i

    R = Sampler()
    for i, w in enumerate([randint(1, 100) for _ in range(10) if random() < 0.5]):
        for _ in range(w):
            R += i

    T = Sampler.copy(S)
    T.merge(R)

    assert T.total == R.total + S.total
    for t in T:
        assert (t in S) or (t in R)
        assert T[t] == (S[t] if t in S else 0) + (R[t] if t in R else 0)
