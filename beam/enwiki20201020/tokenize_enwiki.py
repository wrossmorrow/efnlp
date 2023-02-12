import argparse
import logging

from typing import Dict, Generator, Union

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.io.gcp.bigquery import (
    BigQueryDisposition,
    ReadFromBigQuery,
    WriteToBigQuery,
)


class Tokenizer(beam.DoFn):
    def __init__(self, encoding: str, strict: bool = False):
        # `CoreBPE` (the rust module) is _not_ pickable (arg)
        # self.encoder = tiktoken.get_encoding(encoding)
        self.encoding = encoding
        self.logger = logging.getLogger()
        self.strict = strict

    def process(
        self, record: Dict[str, str]
    ) -> Generator[Dict[str, Union[str, bytes]], None, None]:
        import tiktoken
        import base64

        if isinstance(record["id"], int):
            self.logger.warning("record read id as an integer")
            record["id"] = str(record["id"])

        self.encoder = tiktoken.get_encoding(self.encoding)
        try:

            encoded = self.encoder.encode(
                record["text"] + "<|endoftext|>",
                allowed_special={"<|endoftext|>"},
            ) # List[int]
            yield {
                "id": record["id"],
                "encoded": encoded,
            }


            # encoded_bytes = b"".join([i.to_bytes(2, byteorder="big") for i in encoded])
            # encoded_b64 = base64.b64encode(encoded_bytes).decode("utf-8")
            # yield {
            #     "id": record["id"],
            #     "tokenized_text_b64": encoded_b64,
            # }

        except Exception as err:
            self.logger.error(f"Error during tokenization: ({err.__class__.__name__}) {err}")
            if self.strict:
                raise err


def print_written_records(record):
    print(record)


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
        "-i",
        "--input",
        type=str,
        default="efnlp-naivegpt:enwiki20201020.rawtxt",
        help="Input BQ table",
    )

    parser.add_argument(
        "-s",
        "--staging",
        type=str,
        default="gs://efnlp-dataflow-staging/python/tmp",
        help="Staging area (in GCS)",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="efnlp-naivegpt:enwiki20201020.tokenized_gpt2_intarray",
        # default="efnlp-naivegpt:enwiki20201020.tokenized_gpt2",
        help="Output BQ table",
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
        # runner='DataflowRunner',
        project=args.project,
        # job_name='unique-job-name',
        temp_location=args.staging,
        region=args.region,
    )
    # Note: Repeatable options like dataflow_service_options or experiments must
    # be specified as a list of string(s). e.g.
    #
    #   dataflow_service_options=['enable_prime']
    #

    with beam.Pipeline(options=beam_options) as p:

        # Read BigQuery table rows into a PCollection, like
        #
        #   PCollection[{id: str, title: str, text: str, src: str}]
        #
        rows = (
            p
            | "read from BigQuery"
            >> ReadFromBigQuery(
                table=args.input,
                method=ReadFromBigQuery.Method.DIRECT_READ,
                # query=f"SELECT id, text FROM [{args.input}] LIMIT 10"
            )
            | "break fusion" >> beam.Reshuffle()
            | "tokenize (gpt2)" >> beam.ParDo(Tokenizer("gpt2"))
            | "output tokens"
            >> WriteToBigQuery(  # noqa: F841
                table=args.output,
                schema={
                    'fields': [{
                        'name': 'id', 
                        'type': 'STRING', 
                        'mode': 'NULLABLE'
                    }, {
                        'name': 'encoded', 
                        'type': 'INTEGER', 
                        'mode': 'REPEATED'
                    }]
                },
                # schema="id:STRING, tokenized_text_b64:STRING",
                create_disposition=BigQueryDisposition.CREATE_NEVER,
                write_disposition=BigQueryDisposition.WRITE_TRUNCATE,
            )
        )

        # NOTE: verify passed
        # rows = (
        #     p | "re-read to test" >> ReadFromBigQuery(
        #         table=args.output,
        #         method=ReadFromBigQuery.Method.DIRECT_READ,
        #     )
        #     | "print" >> beam.ParDo(print_written_records)
        # )

        # Run the pipeline (all operations are deferred until run() is called).


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    run()
