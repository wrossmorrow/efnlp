import argparse

from datetime import datetime as dt

import _efnlp

from . import Language, SuffixTreeSet

header = """
- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

EFNLP (Empirical Frequency Natural Language Processor)

Computes the empirical frequencies according to sequences of tokenized string data.
Can generate too, via random sampling from matching against the naively estimated
conditional distributions and their associated marginals for shorter sequences.

Note this software is provided AS-IS under the GPL v2.0 License. Contact the author
with any questions. Copyright 2023+ W. Ross Morrow.

- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
"""


def cli() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=header, formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument(
        "-c",
        "--corpus",
        type=str,
        default=None,
        # required=True,
        help="""File name containing corpus data""",
    )

    parser.add_argument(
        "-L",
        "--language",
        type=str,
        default=None,
        help="""Language file (protobuf)""",
    )

    parser.add_argument(
        "-M",
        "--model",
        type=str,
        default=None,
        help="""Model file (protobuf)""",
    )

    parser.add_argument(
        "-b",
        "--block-size",
        type=int,
        default=5,
        help="""Block size""",
    )

    parser.add_argument(
        "-v",
        "--split",
        type=float,
        default=1.0,
        help="""('training') split: front fraction of the corpus for computing,
        remainder used for validation""",
    )

    parser.add_argument(
        "-g",
        "--generate",
        type=int,
        default=1000,
        help="""Length of a sample to generate""",
    )

    parser.add_argument(
        "-p",
        "--prompt",
        type=str,
        default="\n",
        help="""prompt (so to speak) for generation""",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="""output to write to; None is stdout""",
    )

    parser.add_argument(
        "-s",
        "--stats",
        dest="stats",
        action="store_true",
        default=False,
        help="Print some stats to the console",
    )

    parser.add_argument(
        "-m",
        "--memory",
        dest="memory",
        action="store_true",
        default=False,
        help="Print memory to the console",
    )

    parser.add_argument(
        "-q",
        "--quiet",
        dest="verbose",
        action="store_false",
        default=True,
        help="Don't print information to the console",
    )

    return parser.parse_args()


def since(started: dt) -> float:
    return (dt.now() - started).total_seconds()


class TimedPrinter:
    def __init__(self) -> None:
        self._started = dt.now()

    def __call__(self, msg: str) -> None:
        print(f"[{dt.now().isoformat()} | {self.elapsed():.6f}s] {msg}")

    def elapsed(self) -> float:
        return since(self._started)


if __name__ == "__main__":

    args = cli()

    _print = TimedPrinter()

    if args.language:
        # L = Language.from_proto_file(args.language)
        L = Language.from_json_file(args.language)
        print(L)
    else:
        raise ValueError("language is required (for now)")

    if args.model:
        M = SuffixTreeSet.from_proto_file(args.model)
        print(M)

    if args.verbose:
        _print("Reading text corpus")

    corpus: str = ""
    with open(args.corpus, "r") as f:
        corpus = f.read()

    # if args.verbose:
    #     _print("Forming (character) language")

    # L = Language.from_corpus(data)

    if args.verbose:
        _print("Encoding corpus in the language")

    encoded = L.encode(corpus)

    N = len(encoded)  # Note: needs to be size in _tokens_ not corpus chars (may differ)
    B = args.block_size
    G = args.generate

    if args.verbose:
        _print(f"Corpus is {N:,} tokens long")

    # split
    Sp = int(args.split * N)
    Ct, Cv = (encoded[:Sp], encoded[(Sp - B - 1) :]) if args.split < 1.0 else (encoded, [])

    if args.verbose:
        _print("Parsing prefix/successor tokens")

    ps = dt.now()
    S = _efnlp.EFNLP()
    S.parse_all(encoded, B, False)
    # S = SuffixTreeSet().parse_all(encoded, B)
    pt = (dt.now() - ps).total_seconds() * 1000

    if args.verbose and args.stats:
        _print(f"Parsed prefixes and successors in corpus in {pt:0.2f}ms")
        # prefix_count = len(S.prefixes())
        prefix_count = S.count_prefixes()
        pop = 100.0 * prefix_count / (N - B - 1)  # exclude last element
        _print(f"Found {prefix_count:,} prefixes ({pop:.1f}% of possible)")
        # pattern_count = len(S.patterns())
        pattern_count = S.count_patterns()
        pop = 100.0 * pattern_count / (N - B - 1)  # exclude last element
        _print(f"Found {pattern_count:,} patterns ({pop:.1f}% of possible)")
        _print(f"Roughly {pattern_count/prefix_count} patterns/prefix")

    if args.verbose and args.memory:
        mem = S.memory()
        mem_mb = mem / 1024 / 1024
        mem_d = int(mem / 8)
        mem_f = int(mem / 4)
        _print(
            f"Memory (roughly) required: {mem_mb:.3} " f"MB (about {mem_d:,} dbl, {mem_f:,} fl)"
        )

    if Cv:
        raise NotImplementedError("Still working on validation strategy")

    if G > 0:

        S.densify()

        if args.verbose:
            _print(f"Sampling and decoding {G} tokens")

        gs = dt.now()
        shake = L.decode(S.generate(G, B, L.encode(args.prompt)))
        if args.verbose:
            gf = 1e6 * (dt.now() - gs).total_seconds() / G
            _print(f"Generation frequency: {gf:0.1f} us/tok")

        if args.output:
            if args.verbose:
                _print(f"Writing sampled results to {args.output}")
            with open(args.output, "w") as f:
                f.write(shake)
        else:
            _print("Generated results: ")
            print(shake)
