import argparse

from datetime import datetime as dt

from . import CharLanguage, SuffixTreeSet

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
        required=True,
        help="""File name containing corpus data""",
    )

    parser.add_argument(
        "-b",
        "--block-size",
        type=int,
        default=5,
        help="""Block size""",
    )

    parser.add_argument(
        "-s",
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
    return (dt.now()-started).total_seconds()


class TimedPrinter:

    def __init__(self) -> None:
        self._started = dt.now()

    def __call__(self, msg: str) -> None:
        print(f"[{dt.now().isoformat()} | {since(self._started):.6f}s] {msg}")

if __name__ == "__main__":

    args = cli()

    _print = TimedPrinter()

    if args.verbose:
        _print("Reading text corpus")

    data: str
    with open(args.corpus, "r") as f:
        data = f.read()

    if args.verbose:
        _print(f"Forming (character) language")

    L = CharLanguage.from_corpus(data)

    if args.verbose:
        _print(f"Encoding corpus in the language constructed")

    C = L.encode(data)

    N = len(C)  # Note: needs to be size in _tokens_ not corpus chars (may differ)
    B = args.block_size
    G = args.generate

    if args.verbose:
        _print(f"Corpus is {N:,} tokens long")

    # split
    Sp = int(args.split * N)
    Ct, Cv = (C[:Sp], C[(Sp - B - 1) :]) if args.split < 1.0 else (C, [])

    if args.verbose:
        _print(f"Parsing prefix/successor tokens")

    S = SuffixTreeSet(L.size)
    for i in range(B, N - 1):
        S.parse(C[i - B : i], C[i])

    if args.verbose:
        _print(f"Parsed prefixes and successors in corpus")
        prefix_count = len(S.prefixes())
        pop = 100.0 * prefix_count / (N-B-1) # exclude last element
        _print(f"Found {prefix_count:,} prefixes ({pop:.1f}% of possible)")
        pattern_count = len(S.patterns())
        pop = 100.0 * pattern_count / (N-B-1) # exclude last element
        _print(f"Found {pattern_count:,} patterns ({pop:.1f}% of possible)")

        _print(f"Normalizing to empirical frequencies")

    S.normalize()

    if args.verbose and args.memory:
        mem = S.memory()
        mem_mb = mem / 1024 / 1024
        mem_d = int(mem / 8)
        mem_f = int(mem / 4)
        _print(
            f"Memory (roughly) required: {mem_mb:.3} "
            f"MB (about {mem_d:,} dbl, {mem_f:,} fl)"
        )

    if Cv:

        hr = 0.0
        for i in range(B + 1, len(Cv) - 1):
            t = S.sample(Cv[i - B - 1 : i - 1])
            if t == Cv[i]:
                hr += 1
            else:
                print(Cv[i - B - 1 : i - 1], Cv[i], t, S.empfreq(Cv[i - B - 1 : i - 1]))

        hr /= N - Sp - 1
        if args.verbose:
            _print(
                f"Hit rate on last {N-Sp-1:,} elements "
                f"({100*args.split:.3}%) of the corpus: {100*hr:.2}"
            )

    if G > 0:

        if args.verbose:
            _print(f"Sampling and decoding {G} tokens")

        shake = L.decode(S.generate(G, B, L.encode(args.prompt)))

        if args.output:
            if args.verbose:
                _print(f"Writing sampled results to {args.output}")
            with open(args.output, "w") as f:
                f.write(shake)
        else:
            _print(f"Results: ")
            print(shake)
