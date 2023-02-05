import argparse
import logging

from typing import Any, Dict, List, Optional, Tuple

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.io.gcp.bigquery import (
  BigQueryDisposition,
  ReadFromBigQuery,
  WriteToBigQuery,
)

from google.cloud import storage


def list_objects(bucket: str, prefix: str, delimiter: Optional[str] = None) -> List[str]:
  client = storage.Client()
  blobs = client.list_blobs(bucket, prefix=prefix, delimiter=delimiter)
  return [blob.name for blob in blobs]


class CharCounter(beam.DoFn):

  def __init__(self, bucket: str, exclude: List[str] = ['\x00']) -> None:
    self.bucket = bucket
    self.exclude = exclude

  def process(self, filename: str):

    import lzma

    from lzma import decompress
    from collections import Counter
    from google.cloud import storage # beam requirement

    client = storage.Client()
    bucket = client.bucket(self.bucket)
    blob = bucket.blob(filename) # like "data/openwebtext/orig/xz/urlsf_subset20-80_data.xz"
    
    # local_filename = filename.split("/")[-1]
    # blob.download_to_filename(local_filename)
    # C = Counter()
    # with lzma.open(local_filename, mode='rt') as file:
    #   for line in file:
    #     C.update([c for c in line.strip() if c not in self.exclude])

    try:
      data = blob.download_as_string() # -> bytes
    except Exception as err:
      print(f"There eas an error downloading {filename}: {err}")
      return

    content: str
    try:
      content = decompress(data).decode()
    except Exception as err:
      print(f"There eas an error decompressing {filename}: {err}")
      return

    C = Counter([c for c in content if c not in self.exclude])
    for c, count in C.items():
      yield (c,count)


class LineCharCounter(beam.DoFn):

  def __init__(self, exclude: List[str] = ['\x00']) -> None:
    self.exclude = exclude

  def process(self, content: str):
    from collections import Counter
    C = Counter([c for c in content if c not in self.exclude])
    for c, count in C.items():
      yield (c,count)
    yield ('\n', 1) # at least one newline was stripped in ReadFromText

def format_counts(kvp: Tuple[str, int]):
  return {"char": kvp[0], "count": kvp[1]}


def cli() -> argparse.ArgumentParser:

  parser = argparse.ArgumentParser()

  parser.add_argument(
    '-p', '--project',
    default="efnlp-naivegpt",
    help="GCP Project",
  )

  parser.add_argument(
    '-r', '--region',
    default='us-central1',
    help="GCP Region",
  )

  parser.add_argument(
    '-i', '--input',
    required=True,
    help="GCP Region",
  )

  parser.add_argument(
    '-l', '--local',
    default=False,
    action="store_true",
    help="local run, not dataflow",
  )

  parser.add_argument(
    '-s', '--staging',
    default="gs://efnlp-dataflow-staging/python/tmp",
    help='Staging area (in GCS)',
  )

  parser.add_argument(
    '-o', '--output',
    required=True,
    help="BigQuery to write results to"
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

    # dirlist = list_objects(args.bucket, args.prefix) # , delimiter="/") # delim fails

    # files = (
    #   p | beam.Create(dirlist) 
    #   | "break fusion 1" >> beam.Reshuffle() # break fusion ==> parallelism?
    # )

    # files = (
    #   p | "read manifest" >> beam.io.ReadFromText(args.manifest)
    # )

    # Form counts: first split, then count, then format for BQ
    # counts = (
    #   files | "download unarchive and count" >> beam.ParDo(CharCounter(args.bucket)) # (char, count) tuples
    #     | "count chars" >> beam.CombinePerKey(sum) # sum up the counts per character
    #     | "format for BigQuery" >> beam.Map(format_counts)
    #     | "write to BigQuery" >> WriteToBigQuery(
    #       table=args.output,
    #       schema='char:STRING, count:INTEGER',
    #       create_disposition=BigQueryDisposition.CREATE_NEVER,
    #       write_disposition=BigQueryDisposition.WRITE_TRUNCATE,
    #     )
    # )

    if args.local:
      result = (
        p | "read files" >> beam.io.ReadFromText(args.input) # lines of text
          | "count chars" >> beam.ParDo(LineCharCounter()) # (char, count) tuples
          | "combine char counts" >> beam.CombinePerKey(sum) # sum up the counts per character
          | "format for BigQuery" >> beam.Map(format_counts) # format
          | "write to local file" >> beam.io.WriteToText(args.output) # just to text
      )

    else:
      result = (
        p | "read files" >> beam.io.ReadFromText(args.input) # lines of text
          | "count chars" >> beam.ParDo(LineCharCounter()) # (char, count) tuples
          | "combine char counts" >> beam.CombinePerKey(sum) # sum up the counts per character
          | "format for BigQuery" >> beam.Map(format_counts) # format
          | "write to BigQuery" >> WriteToBigQuery(
            table=args.output,
            schema='char:STRING, count:INTEGER',
            create_disposition=BigQueryDisposition.CREATE_NEVER,
            write_disposition=BigQueryDisposition.WRITE_TRUNCATE,
          )
      )

    # Run the pipeline (all operations are deferred until run() is called).

if __name__ == '__main__':
  logging.getLogger().setLevel(logging.INFO)
  run()
