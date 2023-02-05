# python3 splitshakes.py \
#   --language=gs://efnlp-private/languages/tinywillspeare-language.proto.bin \
#   --input=gs://efnlp-private/data/shakes/tinywillspeare.txt \
#   --output=efnlp-naivegpt:shakespeare.segments \
#   --num-segments=100 \
#   --block-size=10 \
#   --project=efnlp-naivegpt \
#   --region=us-central1 \
#   --staging=gs://efnlp-dataflow-staging/python/tmp \
#   --runner=DataflowRunner \
#   --disk_size_gb=100 \
#   --experiments=use_runner_v2 \
#   --sdk_container_image=us-central1-docker.pkg.dev/efnlp-naivegpt/dataflow/python:draft-v4 \
#   --sdk_location=container


import argparse
import logging
import re

from typing import Any, Dict, List, Tuple

from google.cloud import storage

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.io.gcp.bigquery import (
  BigQueryDisposition,
  ReadFromBigQuery,
  WriteToBigQuery,
)

from efnlp import CharLanguage, split_input

class Formatter(beam.DoFn):
  def __init__(self, lang: CharLanguage, num_segments: int, block_size: int) -> None:
    self.L = lang
    self.N = num_segments
    self.B = block_size

  def process(self, segment: List[int]):
    yield {
      "num_segments": self.N,
      "block_size": self.B,
      "segment": self.L.decode(segment), # ','.join([str(t) for t in segment]),
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
    default="gs://efnlp-private/data/shakes",
    help="Input file location",
  )

  parser.add_argument(
    '-b', '--block-size',
    type=int,
    default=10,
    help="Block size (sequence prefixes); default = 10",
  )

  parser.add_argument(
    '-n', '--num-segments',
    type=int,
    default=50,
    help="number of \"segments\" (sequences) to generate; default = 50",
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
    default="efnlp-naivegpt:shakespeare.segments",
    help=(
      'Output BigQuery table for results specified as: '
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
    runner='DataflowRunner',
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
  bucket_name = match.group(1)
  lang_key = match.group(2)

  bucket = client.get_bucket(bucket_name)
  blob = bucket.get_blob(lang_key)
  langpb = blob.download_as_string() # really a bytes object

  lang = CharLanguage.from_proto_bytes(langpb)

  match = re.match(r'^gs://([^/]+)/(.*)', args.input)
  bucket_name = match.group(1)
  file_key = match.group(2)

  bucket = client.get_bucket(bucket_name)
  blob = bucket.get_blob(file_key)
  text = str(blob.download_as_text()) # not a bytes object, though we could use bytes

  encoded = lang.encode(text)

  segments = split_input(encoded, args.num_segments, args.block_size)

  bq_schema = 'num_segments:INTEGER, block_size:INTEGER, segment:STRING'

  # We _could_ 
  # 
  #   * pass in the segment index boundaries as a PCollection
  #   * supply the text as a side-input
  #   * ParDo over the index bounds and text to parallelize
  # 
  # but that isn't the point here. This is mostly a container test. 

  with beam.Pipeline(options=beam_options) as p:

    segs = (
      p | beam.Create(segments)
        | "format" >> beam.ParDo(Formatter(lang, args.num_segments, args.block_size))
        | 'Write' >> WriteToBigQuery(
          table=args.output,
          schema=bq_schema,
          create_disposition=BigQueryDisposition.CREATE_NEVER,
          write_disposition=BigQueryDisposition.WRITE_TRUNCATE,
        )
    )

    # Run the pipeline (all operations are deferred until run() is called).

if __name__ == '__main__':
  logging.getLogger().setLevel(logging.INFO)
  run()
