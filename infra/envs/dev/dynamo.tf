resource "aws_dynamodb_table" "tasks" {
  name         = "${var.project_name}-${var.stage}-tasks"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "pk" # tenant_id#user_id
  range_key = "sk" # task_id

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  attribute {
    name = "task_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  global_secondary_index {
    name            = "by_task"
    hash_key        = "task_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "by_user_created"
    hash_key        = "pk"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = var.tags
}

data "aws_iam_policy_document" "lambda_tasks_access" {
  statement {
    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
    ]
    resources = [
      aws_dynamodb_table.tasks.arn,
      "${aws_dynamodb_table.tasks.arn}/index/*",
    ]
  }
}

resource "aws_iam_policy" "lambda_tasks_policy" {
  name   = "${var.project_name}-${var.stage}-lambda-tasks"
  policy = data.aws_iam_policy_document.lambda_tasks_access.json
  tags   = var.tags
}

resource "aws_iam_role_policy_attachment" "lambda_tasks_attach" {
  role       = aws_iam_role.api_lambda_role.name
  policy_arn = aws_iam_policy.lambda_tasks_policy.arn
}