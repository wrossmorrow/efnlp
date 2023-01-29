
data aws_region current {}

resource aws_ecs_cluster efnlp {
  name = "efnlp"

  # any more?
}

resource aws_ecs_cluster_capacity_providers efnlp {
  cluster_name = aws_ecs_cluster.efnlp.name

  capacity_providers = ["FARGATE_SPOT"] # save $$$ for availability

  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = "FARGATE_SPOT"
  }
}

resource aws_cloudwatch_log_group efnlp {
  name = "efnlp"
}

resource aws_ecs_task_definition efnlp {

  family = "efnlp"

  container_definitions = jsonencode([
    {
      name      = "service"
      image     = "${aws_ecr_repository.efnlp.repository_url}:${var.image_tag}"
      cpu       = 512
      memory    = 4096
      essential = true
      portMappings = [
        {
          containerPort = 50051
          hostPort      = 50051
        }
      ]
      command = [
        "efnlp",
        "-language",
        "s3://efnlp-private/language.proto.bin.gz",
        "-model",
        "s3://efnlp-private/model.proto.bin.gz",
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group = aws_cloudwatch_log_group.efnlp.name
          awslogs-region = data.aws_region.current.name
          awslogs-stream-prefix = "ecs"
        }
      }
      healthCheck = {
        command = [ "CMD-SHELL", "/bin/grpc_health_probe -addr=:50051" ]
        startPeriod = 30
        timeout = 2
        retries = 3
        interval = 10
      }
      
    },
  ])

  # ECS role, followed by running container IAM role
  execution_role_arn = aws_iam_role.ecs_task_exec.arn
  task_role_arn      = aws_iam_role.ecs_task.arn

  requires_compatibilities = ["FARGATE"]
  cpu                      = 512  # "CPU units"
  memory                   = 4096 # MiB

  network_mode = "awsvpc"

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

}

resource aws_ecs_service efnlp {
  name            = "efnlp"
  cluster         = aws_ecs_cluster.efnlp.id
  launch_type     = "FARGATE"
  task_definition = aws_ecs_task_definition.efnlp.arn
  desired_count   = 1
  depends_on      = [
    aws_iam_role_policy_attachment.ecs_task_s3,
  ]

  network_configuration { # required
    subnets = [
      for psn in aws_subnet.private: psn.id
    ]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.efnlp.arn
    container_name   = "service"
    container_port   = 50051
  }


  # ordered_placement_strategy {
  #   type  = "binpack"
  #   field = "cpu"
  # }

  # placement_constraints {
  #   type       = "memberOf"
  #   expression = "attribute:ecs.availability-zone in [us-west-2a, us-west-2b]"
  # }

  lifecycle {
    ignore_changes = [desired_count]
  }

}

# # needed? confused. 
# resource "aws_ecs_task_set" "example" {
#   service         = aws_ecs_service.efnlp.id
#   cluster         = aws_ecs_cluster.efnlp.id
#   task_definition = aws_ecs_task_definition.efnlp.arn

#   load_balancer {
#     target_group_arn = aws_lb_target_group.efnlp.arn
#     container_name   = "efnlp"
#     container_port   = 50051
#   }
# }