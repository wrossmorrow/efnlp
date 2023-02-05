import argparse
import logging

from typing import Any, Dict, List, Tuple

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.io.gcp.bigquery import (
  BigQueryDisposition,
  ReadFromBigQuery,
  WriteToBigQuery,
)

def split_text(row: Dict[str, Any]) -> List[str]:
  return [c for c in row.get("text", "")]

def format_counts(kvp: Tuple[str, int]):
  return {"char": kvp[0], "count": kvp[1]}

def cli() -> argparse.ArgumentParser:

  parser = argparse.ArgumentParser()

  parser.add_argument(
    '-p', '--project',
    required=True,
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
    help=(
        'Input BigQuery table to process specified as: '
        'PROJECT:DATASET.TABLE or DATASET.TABLE.'
    ),
  )

  parser.add_argument(
    '-s', '--staging',
    default="gs://efnlp-dataflow-staging/python/tmp",
    help='Staging area (in GCS)',
  )

  parser.add_argument(
    '-o', '--output',
    required=True,
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

  with beam.Pipeline(options=beam_options) as p:

    # Read BigQuery table rows into a PCollection.
    rows = p | 'read' >> ReadFromBigQuery(
      table=args.input,
      method=ReadFromBigQuery.Method.DIRECT_READ,
    )

    # Form counts: first split, then count, then format for BQ
    counts = (
      rows | "split to chars" >> beam.FlatMap(split_text)
      | "count chars" >> beam.combiners.Count.PerElement()
      | "format" >> beam.Map(format_counts)
    )

    # Write the output using a "Write" transform that has side effects.
    counts | 'Write' >> WriteToBigQuery(
      table=args.output,
      schema='char:STRING, count:INTEGER',
      create_disposition=BigQueryDisposition.CREATE_NEVER,
      write_disposition=BigQueryDisposition.WRITE_TRUNCATE,
    )

    # Run the pipeline (all operations are deferred until run() is called).

if __name__ == '__main__':
  logging.getLogger().setLevel(logging.INFO)
  run()
