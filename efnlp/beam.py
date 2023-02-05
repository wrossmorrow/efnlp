from __future__ import annotations

from warnings import warn

from typing import cast, List, Optional, Tuple

from . import SuffixTree, SuffixTreeSet, Language


AccmType = Tuple[int, bytes]


class _SuffixTreeParser:  # (beam.DoFn): if beam importable; see below
    def __init__(
        self,
        language: Language,
        block_size: int,
        documents: bool = False,
        doc_start_tok: int = 0,
        doc_end_tok: int = 1,
        text_encoded: bool = False,
        text_delimiter: str = ",",
        text_field: str = "segment",
    ):
        self.L = language
        self.B = block_size

        # TODO: annoying; setattr over generic kwargs? cleaner code
        # but much more opaque interface/API here
        self.documents = documents
        self.doc_start_tok = doc_start_tok
        self.doc_end_tok = doc_end_tok
        self.text_encoded = text_encoded
        self.text_delimiter = text_delimiter
        self.text_field = text_field

    def process(self, record):  # -> Generator[Tuple[int, bytes]]?

        # size: int; but what about dynamic parsing?
        T = SuffixTreeSet()

        # encode segment in language; TODO: generalize
        encoded: List[int] = []
        text = cast(str, record[self.text_field])
        if self.text_encoded:
            encoded = [int(i) for i in text.split(self.text_delimiter)]
        encoded = self.L.encode(text)

        # TODO: doc start + encoded + doc end...
        if self.documents:
            encoded = [self.doc_start_tok] + encoded + [self.doc_end_tok]

        # parse token string
        T.parse_all(encoded, self.B)

        # emit each tree
        for t, tree in T.trees.items():
            # TODO: tuple form sufficient for a "keyed" PCollection?
            yield (t, bytes(tree))  # bytes -> protobuf encoding


class _SuffixTreeMerge:  # (beam.CombineFn): if beam importable; see below
    # are we merging based on proto, or pyobjects?

    def create_accumulator(self) -> Optional[AccmType]:
        return None  # SuffixTree() but for what token?

    def add_input(self, accm: Optional[AccmType], inp: bytes) -> AccmType:
        if accm is None:
            tree = SuffixTree.from_proto_bytes(inp)
            return (tree.token, bytes(tree))
        tree = SuffixTree.merge_proto_bytes(accm[1], inp)
        return (tree.token, bytes(tree))

    # TODO: List/Iterable arg? or varargs?
    def merge_accumulators(self, accumulators: List[Optional[AccmType]]) -> Optional[AccmType]:
        tree = None
        for accm in accumulators:
            if accm:
                t, b = accm  # split into token/bytes
                if tree:
                    other = SuffixTree.from_proto_bytes(b)
                    tree.merge(other)  # won't merge if token mismatched
                else:
                    tree = SuffixTree.from_proto_bytes(b)
        if tree:
            return (tree.token, bytes(tree))
        return None

    def extract_output(self, accm: AccmType) -> bytes:
        return accm[1]


try:

    import apache_beam as beam

    # Note: MRO requires inheriting _SuffixTreeXXX first; o/w class will
    # access beam.DoFn/CombineFn's process method first and error out

    class SuffixTreeParser(_SuffixTreeParser, beam.DoFn):
        pass

    class SuffixTreeMerge(_SuffixTreeMerge, beam.CombineFn):
        pass

except ImportError as err:

    warn(
        f"Cannot import beam: SuffixTreeParser and SuffixTreeMerge will not be parallelized ({err})"
    )

    class Unimportable:
        def __init__(self, *args, **kwargs) -> None:
            raise NotImplementedError(
                f"Cannot initialize {self.__class__.__name__} without `beam` modules"
            )

    class SuffixTreeParser(_SuffixTreeParser):  # type:ignore
        pass

    class SuffixTreeMerge(_SuffixTreeMerge):  # type:ignore
        pass
