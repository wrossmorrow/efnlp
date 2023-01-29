# You will need to create an aws_lb, and an aws_lb_target_group. 
# Then create an aws_lb_listener which is assigned to the aws_lb, 
# and has an action that forwards requests to the aws_lb_target_group. 
# The listener "connects" the target group to the load balancer.

resource aws_lb efnlp {
  name               = "efnlp"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.default.id]
  subnets            = [for subnet in aws_subnet.public : subnet.id]

  enable_deletion_protection = true

  access_logs {
    bucket  = var.alb_logs_bucket
    prefix  = "efnlp-lb-logs"
    enabled = true
  }

}

resource aws_lb_target_group efnlp {
  name     = "efnlp"
  port     = 50051
  protocol = "HTTP"
  protocol_version = "GRPC"
  vpc_id   = aws_vpc.vpc.id
  target_type = "ip" # alb/fargate

  # GRPC health check
  health_check {
    enabled = true
    protocol = "HTTP"
    matcher = "0"
    path = "/grpc.health.v1.Health/Check"
  }
}

resource aws_lb_listener efnlp {
  load_balancer_arn = aws_lb.efnlp.arn
  port              = "50051"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-2016-08"
  certificate_arn   = var.acm_cert_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.efnlp.arn
  }
}

data aws_route53_zone efnlp {
  name         = "naivegpt.com."
  private_zone = false
}

resource aws_route53_record api {
  zone_id = data.aws_route53_zone.efnlp.zone_id
  name    = "api.naivegpt.com"
  type    = "A"

  alias {
    name                   = aws_lb.efnlp.dns_name
    zone_id                = aws_lb.efnlp.zone_id
    evaluate_target_health = true
  }
}
