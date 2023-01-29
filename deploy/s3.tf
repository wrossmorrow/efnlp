

# {
#   "Id": "Policy",
#   "Version": "2012-10-17",
#   "Statement": [
#     {
#       "Action": [
#         "s3:PutObject"
#       ],
#       "Effect": "Allow",
#       "Resource": "arn:aws:s3:::my-elb-tf-test-bucket/AWSLogs/*",
#       "Principal": {
#         "AWS": [
#           "${data.aws_elb_service_account.main.arn}"
#         ]
#       }
#     }
#   ]
# }

resource aws_s3_bucket efnlp {
  bucket = "efnlp-private"
}

data aws_elb_service_account aws {}

data aws_iam_policy_document alb_logs {
  statement {

    principals {
      type        = "AWS"
      identifiers = [
        data.aws_elb_service_account.aws.arn,
      ]
    }

    actions = [
      "s3:PutObject",
    ]

    resources = [
      aws_s3_bucket.efnlp.arn,
      "${aws_s3_bucket.efnlp.arn}/*",
    ]
  }
}

resource aws_s3_bucket_policy alb_logs {
  bucket = aws_s3_bucket.efnlp.id
  policy = data.aws_iam_policy_document.alb_logs.json
}
