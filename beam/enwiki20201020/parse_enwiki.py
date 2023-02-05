# python3 parseshakes.py \
#   --language=gs://efnlp-private/languages/enwiki/commonchars.proto.bin \
#   --input=efnlp-naivegpt:enwiki20201020.rawtxt \
#   --output=gs://efnlp-private/models/enwiki20201020/test \
#   --stats-out=efnlp-naivegpt:enwiki20201020.statistics \
#   --block-size=10 \
#   --project=efnlp-naivegpt \
#   --region=us-central1 \
#   --staging=gs://efnlp-dataflow-staging/python/tmp \
#   --runner=DataflowRunner \
#   --disk_size_gb=100 \
#   --experiments=use_runner_v2 \
#   --sdk_container_image=us-central1-docker.pkg.dev/efnlp-naivegpt/dataflow/python:draft-v0.1.12 \
#   --sdk_location=container

import argparse
import logging
import re

from typing import Any, Dict, List, Optional, Tuple

from google.cloud import storage

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.io.gcp.bigquery import (
  BigQueryDisposition,
  ReadFromBigQuery,
  WriteToBigQuery,
)

import efnlp


class CustomGCSWriter(beam.DoFn):
  def __init__(self, bucket: str, prefix: str, compress: bool = True) -> None:
    self.bucket = bucket
    self.prefix = prefix
    self.compress = compress

  def process(self, record: Tuple[int, bytes]): # -> Dict[str, Union[str int]:

    # SUPER annoying; need _local_ import statements for module availability
    # we could assess whether using in a class initializer is enough
    import gzip
    from google.cloud import storage

    client = storage.Client() # Clients are not pickable; can't set on init
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

    yield { # TODO: timestamp?
      "token": token,
      "location": f"{self.bucket}/{location}",
      "rawbytes": rawbytes,
      "written": written,
    }


def cli() -> argparse.ArgumentParser:

  parser = argparse.ArgumentParser()

  parser.add_argument(
    '-p', '--project',
    type=str,
    default="efnlp-naivegpt",
    help="GCP Project",
  )

  parser.add_argument(
    '-r', '--region',
    type=str,
    default='us-central1',
    help="GCP Region",
  )

  parser.add_argument(
    '-l', '--language',
    type=str,
    default='language.proto.bin',
    help="Language file (proto)",
  )

  parser.add_argument(
    '-i', '--input',
    type=str,
    default="efnlp-naivegpt:shakespeare.segments",
    help="Input file location",
  )

  parser.add_argument(
    '-b', '--block-size',
    type=int,
    default=10,
    help="Block size (sequence prefixes); default = 10",
  )

  parser.add_argument(
    '-s', '--staging',
    type=str,
    default="gs://efnlp-dataflow-staging/python/tmp",
    help='Staging area (in GCS)',
  )

  parser.add_argument(
    '-o', '--output',
    type=str,
    default="gs://efnlp-private/models/shakes/test",
    help=(
      'Output BigQuery table for results specified as: '
      'PROJECT:DATASET.TABLE or DATASET.TABLE.'
    )
  )

  parser.add_argument(
    '-S', '--stats-out',
    type=str,
    default="efnlp-naivegpt:shakespeare.statistics",
    help=(
      'Output BigQuery table for statistics specified as: '
      'PROJECT:DATASET.TABLE or DATASET.TABLE.'
    )
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

  # prep work: read data and read language

  client = storage.Client()

  match = re.match(r'^gs://([^/]+)/(.*)', args.language)
  if not match:
    raise ValueError(f"language is not a GCS location ({args.language})")
  bucket_name = match.group(1)
  lang_key = match.group(2)

  bucket = client.get_bucket(bucket_name)
  blob = bucket.get_blob(lang_key)
  langpb = blob.download_as_string() # really a bytes object
  lang = efnlp.CharLanguage.from_proto_bytes(langpb)

  match = re.match(r'^gs://([^/]+)/(.*)', args.output)
  if not match:
    raise ValueError(f"output is not a GCS location ({args.output})")
  out_bucket = match.group(1)
  out_prefix = match.group(2)

  with beam.Pipeline(options=beam_options) as p:

    # include a "query" arg?
    # query = "SELECT segment FROM [efnlp-naivegpt:shakespeare.segments] LIMIT 10"
    # print(query)
    # query=query,

    # Read BigQuery table rows into a PCollection.
    rows = p | "read from BigQuery" >> ReadFromBigQuery(
      table=args.input,
      method=ReadFromBigQuery.Method.DIRECT_READ,
    ) | ( # PCollection[{num_segments: int, block_size: int, segment: str}]
      "break fusion" >> beam.Reshuffle()
    ) # fusion seems to really slow down processing here

    # create, group, and merge SuffixTrees
    trees = (
      rows | "parse segments" >> beam.ParDo(efnlp.SuffixTreeParser(lang, args.block_size))
        | "merge by token" >> beam.CombinePerKey(efnlp.SuffixTreeMerge())
    ) # PCollection[<token, tree (as proto bytes)>]

    # write trees to GCS, in files "partitioned" by token (i.e., not
    # traditionally sharded by desired file size alone)
    # 
    # TODO: how to limit file size? We have an upper bound via the depth and
    # the storage size, but that's exponentially large: O(|L|^D) where D is
    # the depth and |L| is the (tokenized) language size. A "real" (C)EF tree
    # is likely to have far fewer than all possible patterns (prefixes and 
    # successors). 
    out = (
      trees | "write out" >> beam.ParDo(CustomGCSWriter(out_bucket, out_prefix))
    )

    # write statistics of output to BigQuery
    if args.stats_out:
      bq_schema = ', '.join([
        "token:INTEGER", 
        "location:STRING",
        "rawbytes:INTEGER",
        "written:INTEGER",
      ])
      stats = (
        out | 'write stats' >> WriteToBigQuery(
            table=args.stats_out,
            schema=bq_schema,
            create_disposition=BigQueryDisposition.CREATE_NEVER,
            write_disposition=BigQueryDisposition.WRITE_TRUNCATE,
          )
      )

    # Run the pipeline (all operations are deferred until run() is called).

if __name__ == '__main__':
  logging.getLogger().setLevel(logging.INFO)
  run()
