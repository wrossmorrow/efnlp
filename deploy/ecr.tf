
resource aws_ecr_repository efnlp {
  name                 = "efnlp"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = false # no scan
  }
}
