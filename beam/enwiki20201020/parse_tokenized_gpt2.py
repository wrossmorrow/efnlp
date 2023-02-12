import argparse
import logging
import re

from typing import Dict, Generator, List, Optional, Tuple

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.io.gcp.bigquery import (
    BigQueryDisposition,
    ReadFromBigQuery,
    WriteToBigQuery,
)


AccmType = Tuple[int, bytes]


class EFNLPParser(beam.DoFn):
    def __init__(self, block_size: int = 10) -> None:
        self.block_size = block_size
        self.logger = logging.getLogger()

    def process(self, record: Dict) -> Generator[Tuple[int, bytes], None, None]:
        import _efnlp

        encoded = record["encoded"]  # List[int]
        parser = _efnlp.EFNLP()
        parser.parse_all(encoded, self.block_size)
        for t, tree_pb in parser.serialized_trees():
            yield (t, tree_pb)


class EFNLPSuffixTreeMerge(beam.CombineFn):
    def create_accumulator(self) -> Optional[AccmType]:
        return None  # SuffixTree() but for what token?

    def add_input(self, accm: Optional[AccmType], inp: bytes) -> AccmType:
        import _efnlp

        itree = _efnlp.SuffixTree.deserialize(inp)
        if accm is None:
            return (itree.token(), itree.serialize()) # just inp?

        atree = _efnlp.SuffixTree.deserialize(accm[1])
        atree.merge(itree)

        return (atree.token(), atree.serialize())

    # TODO: List/Iterable arg? or varargs?
    def merge_accumulators(self, accumulators: List[Optional[AccmType]]) -> Optional[AccmType]:
        import _efnlp

        tree: _efnlp.SuffixTree = None
        for accm in accumulators:
            if accm:
                t, b = accm  # split into token/bytes
                if tree is None:
                    tree = _efnlp.SuffixTree.deserialize(b)  # "initial condition"
                else:
                    other = _efnlp.SuffixTree.deserialize(b)
                    tree.merge(other)  # won't merge if token mismatched
        if tree:
            return (tree.token(), tree.serialize())
        return None

    def extract_output(self, accm: AccmType) -> bytes:
        return accm[1]


class CustomGCSWriter(beam.DoFn):
    def __init__(self, bucket: str, prefix: str, compress: bool = True) -> None:
        self.bucket = bucket
        self.prefix = prefix
        self.compress = compress

    def process(self, record: Tuple[int, bytes]):  # -> Dict[str, Union[str int]:

        # SUPER annoying; need _local_ import statements for module availability
        # we could assess whether using in a class initializer is enough
        import gzip
        from google.cloud import storage

        client = storage.Client()  # Clients are not pickable; can't set on init
        bucket = client.get_bucket(self.bucket)

        token, proto = record
        rawbytes = len(proto)
        written = len(proto)
        location = f"{self.prefix}/{token}.proto.bin"

        if self.compress:
            # Note: not sure you can effective set Content-Encoding on GCS
            #
            # https://github.com/googleapis/google-cloud-python/issues/3099
            #
            location += ".gz"
            proto = gzip.compress(proto)
            written = len(proto)

        blob = bucket.blob(location)
        blob.upload_from_string(proto, content_type="application/octet-stream")

        yield {  # TODO: timestamp?
            "token": token,
            "location": f"{self.bucket}/{location}",
            "rawbytes": rawbytes,
            "written": written,
        }


def cli() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-p",
        "--project",
        type=str,
        default="efnlp-naivegpt",
        help="GCP Project",
    )

    parser.add_argument(
        "-r",
        "--region",
        type=str,
        default="us-central1",
        help="GCP Region",
    )

    parser.add_argument(
        "-s",
        "--staging",
        type=str,
        default="gs://efnlp-dataflow-staging/python/tmp",
        help="Staging area (in GCS)",
    )

    parser.add_argument(
        "-i",
        "--input",
        type=str,
        default="efnlp-naivegpt:enwiki20201020.tokenized_gpt2_intarray",
        help="Input BQ table",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="gs://efnlp-private/models/enwiki20201020/gpt2",
        help="Output BQ table",
    )

    parser.add_argument(
        "-b",
        "--block-size",
        type=int,
        default=10,
        help="block size to use in parsing",
    )

    parser.add_argument(
        "-S",
        "--stats-out",
        type=str,
        default="efnlp-naivegpt:enwiki20201020.statistics",
        help="Output BQ table for statistics",
    )

    parser.add_argument(
        "-l",
        "--local",
        default=False,
        action="store_true",
        help="run locally",
    )

    return parser


def run() -> None:

    args, beam_args = cli().parse_known_args()

    # Create and set your PipelineOptions.
    #
    # For Cloud execution, specify DataflowRunner and set the Cloud Platform
    # project, job name, temporary files location, and region.
    # For more information about regions, check:
    #
    #   https://cloud.google.com/dataflow/docs/concepts/regional-endpoints
    #
    beam_options = PipelineOptions(
        beam_args,
        # job_name='unique-job-name',
        # runner='DataflowRunner',
        project=args.project,
        temp_location=args.staging,
        region=args.region,
    )
    # Note: Repeatable options like dataflow_service_options or experiments must
    # be specified as a list of string(s). e.g.
    #
    #   dataflow_service_options=['enable_prime']
    #

    match = re.match(r"^gs://([^/]+)/(.*)", args.output)
    if not match:
        raise ValueError(f"output is not a GCS location ({args.output})")
    out_bucket = match.group(1)
    out_prefix = match.group(2)

    with beam.Pipeline(options=beam_options) as p:

        # Note: write trees to GCS, in files "partitioned" by token (i.e., not
        # traditionally sharded by desired file size alone)
        stats = (
            p
            | "read from BigQuery"
            >> (
                ReadFromBigQuery(
                    query=f"SELECT * FROM [{args.input}] LIMIT 10",
                    flatten_results=False,
                )
                if args.local
                else ReadFromBigQuery(
                    table=args.input,
                    method=ReadFromBigQuery.Method.DIRECT_READ,
                    flatten_results=False,
                )
            )
            | "break fusion" >> beam.Reshuffle()
            | "parse segments" >> beam.ParDo(EFNLPParser(args.block_size))
            | "merge by token" >> beam.CombinePerKey(EFNLPSuffixTreeMerge())
            | "write out" >> beam.ParDo(CustomGCSWriter(out_bucket, out_prefix))
        )

        # write statistics of output to BigQuery
        if args.stats_out:
            stats | "write stats" >> WriteToBigQuery(
                table=args.stats_out,
                schema={
                    "fields": [
                        {"name": "token", "type": "INTEGER", "mode": "NULLABLE"},
                        {"name": "location", "type": "STRING", "mode": "NULLABLE"},
                        {"name": "rawbytes", "type": "INTEGER", "mode": "NULLABLE"},
                        {"name": "written", "type": "INTEGER", "mode": "NULLABLE"},
                    ]
                },
                create_disposition=BigQueryDisposition.CREATE_NEVER,
                write_disposition=BigQueryDisposition.WRITE_TRUNCATE,
            )

        # Run the pipeline (all operations are deferred until run() is called).


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    run()
