
resource aws_iam_role ecs_task_exec {

  name = "efnlp-ecs"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        },
        Effect = "Allow"
        Sid    = "required"
      }
    ]
  })

}

resource aws_iam_role ecs_task {

  name = "efnlp-ecs-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        },
        Effect = "Allow"
        Sid    = "required"
      }
    ]
  })
  
}

resource aws_iam_role_policy_attachment ecs_task_exec {
  role       = aws_iam_role.ecs_task_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# resource aws_iam_role_policy_attachment ecs_task_exec {
#   role       = aws_iam_role.ecs_task_exec.name
#   policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceRole"
# }

resource aws_iam_role_policy_attachment ecs_task_s3 {
  role       = aws_iam_role.ecs_task.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
}
