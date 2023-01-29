

variable vpc_cidr {
  type = string
  default = "10.0.0.0/16"
}

variable public_subnets_cidr {
  type = list(string)
  default = [
    "10.0.0.0/20", 
    "10.0.16.0/20", 
    "10.0.32.0/20",
  ]
}

variable private_subnets_cidr {
  type = list(string)
  default = [
    "10.0.48.0/20", 
    "10.0.64.0/20", 
    "10.0.80.0/20",
  ]
}

variable availability_zones {
  type = list(string)
  default = [
    "us-east-1a",
    "us-east-1b",
    "us-east-1c",
  ]
}

variable alb_logs_bucket {
  type = string
  default = "efnlp-private"
}

variable image_tag {
  type = string
  default = "latest"
}

variable acm_cert_arn {
  type = string
  default = "arn:aws:acm:us-east-1:396610714890:certificate/8a81cc89-2011-49a6-8226-146f4a8d5ece"
}
