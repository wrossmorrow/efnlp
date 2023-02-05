import pytest  # noqa: F401

from efnlp import Language, SuffixTreeSet, split_input, merge_split_input

from .conftest import Timer


def test_split_parsing() -> None:

    block_size, num_segments = 5, 75

    with Timer() as T:
        corpus = ""
        with open("data/tinywillspeare.txt", "r") as f:
            corpus = f.read()
    T.log_us("read corpus")

    assert len(corpus) > 0

    # make a character language
    with Timer() as T:
        characters = sorted(list(set(corpus)))
        lang_dict = {c: t for t, c in enumerate(characters)}
        language = Language.from_dict(lang_dict)
    T.log_us("constructed language")

    # encode text corpus (NOTE: takes a long time now with suffix
    # based language encoding/tokenization)
    with Timer() as T:
        encoded = language.encode(corpus)
    T.log_us("encoded corpus")

    with Timer() as T:
        segments = split_input(encoded, num_segments, block_size)
    T.log_us("split encoded corpus")

    # TODO: move these asserts to a split_input specific test.

    # quick check: after the first segment, successive segments should
    # overlap: a segment starts with a prefix equal to the last block_size
    # elements of the previous segment. This is because a segment will
    # estimate up to ([-block_size-1:-1], [-1]), so the first prefix for
    # a next segment should be [-block_size:] (followed by a "new" value)
    with Timer() as T:
        assert len(segments) == num_segments
        for i in range(1, num_segments):
            assert segments[i][0:block_size] == segments[i - 1][-block_size:]
    T.log_us("verified segments overlap")

    # "recombine" to verify a properly _partitioned_ corpus
    with Timer() as T:
        recomposed = merge_split_input(segments, block_size)
        assert len(recomposed) == len(encoded)
        assert all([recomposed[i] == t for i, t in enumerate(encoded)])
    T.log_us("verified segments partition the corpus")

    with Timer() as T:
        trees = [
            SuffixTreeSet().parse_all(segment, block_size, ignore_start=True)
            for segment in segments
        ]
    T.log_us("parsed segment trees in")

    with Timer() as T:
        for i in range(block_size, len(encoded) - 1):
            prefix = encoded[i - block_size : i]
            assert any(T.match(prefix) for T in trees), (i, prefix, language.decode(prefix))
    T.log_us("verified every (encoded) corpus prefix is in some tree")

    S = SuffixTreeSet()
    with Timer() as T:
        for tree in trees:
            S.merge(tree)
    T.log_us("merged all segment trees")

    assert len(S.prefixes()) > 0

    with Timer() as T:
        for tree in trees:
            prefixes = tree.prefixes()
            assert len(prefixes) > 0
            for p in prefixes:
                assert S.match(p)
    T.log_us("verified all segment tree prefixes exist in the merged tree")

    with Timer() as T:
        errors = []
        for i in range(block_size, len(encoded) - 1):
            prefix = encoded[i - block_size : i]
            try:
                assert S.match(prefix), (i, prefix, language.decode(prefix))
            except AssertionError as err:
                errors.append(err)

            # NOTE: we do not actually know if there aren't repeated
            # subsequences in the actual segments... there might actually
            # be.
            #
            # assert any([
            #     not T.match(encoded[i-block_size:i]) for T in trees
            # ]), (
            #     L.decode(encoded[i-block_size:i]),
            #     len(trees),
            #     len([
            #         T for T in trees if T.match(encoded[i-block_size:i])
            #     ])
            # )

        assert len(errors) == 0, errors
    T.log_us("verified all (encoded) corpus prefixes exist in the merged tree")
