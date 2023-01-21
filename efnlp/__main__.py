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
        description=header, 
        formatter_class=argparse.RawTextHelpFormatter
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
        default='\n',
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
        "-q",
        "--quiet",
        dest="verbose",
        action="store_false",
        default=True,
        help="Don't print information to the console",
    )

    return parser.parse_args()


if __name__ == "__main__":
    
    args = cli()
    
    data: str
    with open(args.corpus, "r") as f:
        data = f.read()

    if args.verbose:
        print(f"[{dt.now().isoformat()}] Forming (character) language")

    L = CharLanguage.from_corpus(data)

    if args.verbose:
        print(f"[{dt.now().isoformat()}] Encoding corpus")

    C = L.encode(data)

    N = len(C) # Note: needs to be size in _tokens_ not corpus chars (may differ)
    B = args.block_size
    G = args.generate

    if args.verbose:
        print(f"[{dt.now().isoformat()}] Parsing prefix/follower tokens")

    S = SuffixTreeSet(L.size)
    for i in range(B, N-1):
        S.parse(C[i-B:i], C[i])

    if args.verbose:
        print(f"[{dt.now().isoformat()}] Normalizing to empirical frequencies")

    S.normalize()

    if G > 0:

        if args.verbose:
            print(f"[{dt.now().isoformat()}] Sampling and decoding {G} tokens")

        code = L.encode(args.prompt)
        shake = L.decode(code)
        for i in range(G):
            prefix = code if len(code) < B else code[-B:]
            code.append(S.sample(prefix)) 
            shake += L.decode(code[-1])
        
        if args.output:
            with open(args.output, "w") as f:
                f.write(shake)
        else:
            print(shake)
    