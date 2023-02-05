import pytest  # noqa: F401

from random import choices
from string import ascii_letters, digits
from typing import Dict, List, Optional

import efnlp

from .conftest import Timer


def test_suffix_tree_parser_and_merger() -> None:

    block_size, num_segments = 3, 50

    ascii_lang = [c for c in ascii_letters + digits]
    lang_dict = {s: i for i, s in enumerate(ascii_lang)}
    language = efnlp.Language.from_dict(lang_dict)

    corpus = "".join(choices(ascii_lang, k=1000))

    with Timer() as T:
        encoded = language.encode(corpus)
    print(f"encoded corpus in {T.us()}us")

    with Timer() as T:
        segments = [
            language.decode(s) for s in efnlp.split_input(encoded, num_segments, block_size)
        ]
    T.log_us("decoded split corpus")

    results = []

    with Timer() as T:
        P = efnlp.SuffixTreeParser(language, block_size)
        for segment in segments:
            count = 0
            record = {"segment": segment}
            for t, tree in P.process(record):
                count += 1
                results.append((t, tree))
                assert isinstance(t, int)
                assert isinstance(tree, bytes)
                ST = efnlp.SuffixTree.from_proto_bytes(tree)
                assert t == ST.token
            # assert count == len(set(c for c in segment[B:-1]))
    T.log_us("parsed segments")

    grouped: Dict[int, List[bytes]] = {}
    for t, b in results:
        if t in grouped:
            grouped[t].append(b)
        else:
            grouped[t] = [b]

    M = efnlp.SuffixTreeMerge()
    with Timer() as T:
        merged: Dict[int, Optional[bytes]] = {t: None for t in grouped}
        for t in grouped:
            accm = M.create_accumulator()
            for b in grouped[t]:
                accm = M.add_input(accm, b)
            if accm:
                out = M.extract_output(accm)
                assert efnlp.SuffixTree.from_proto_bytes(out).token == t
                merged[t] = out
    T.log_us("merged parsed trees (input)")

    assert all([m is not None for _, m in merged.items()])
    assert all([isinstance(m, bytes) for _, m in merged.items()])
    assert all(
        [
            efnlp.SuffixTree.from_proto_bytes(m) is not None
            for _, m in merged.items()
            if m is not None  # not for testing, this is for typing
        ]
    )

    with Timer() as T:
        merged = {t: None for t in grouped}
        for t in grouped:
            accm = M.create_accumulator()
            accm = M.merge_accumulators([accm] + [(t, g) for g in grouped[t]])
            if accm:
                out = M.extract_output(accm)
                assert efnlp.SuffixTree.from_proto_bytes(out).token == t
                merged[t] = out
    T.log_us("merged parsed trees (accumulators)")

    assert all([m is not None for _, m in merged.items()])
    assert all([isinstance(m, bytes) for _, m in merged.items()])
    assert all(
        [
            efnlp.SuffixTree.from_proto_bytes(m) is not None
            for _, m in merged.items()
            if m is not None  # not for testing, this is for typing
        ]
    )
