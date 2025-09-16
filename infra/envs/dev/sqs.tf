resource "aws_sqs_queue" "tasks_dlq" {
  name                      = "${var.project_name}-${var.stage}-tasks-dlq"
  message_retention_seconds = var.sqs_message_retention_seconds
  tags                      = var.tags
}

resource "aws_sqs_queue" "tasks" {
  name                       = "${var.project_name}-${var.stage}-tasks-queue"
  visibility_timeout_seconds = var.sqs_visibility_timeout_seconds
  redrive_policy = jsonencode({
    maxReceiveCount     = var.sqs_max_receive_count
    deadLetterTargetArn = aws_sqs_queue.tasks_dlq.arn
  })
  tags = var.tags
}

data "aws_iam_policy_document" "lambda_sqs_send" {
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.tasks.arn]
  }
}

resource "aws_iam_policy" "lambda_sqs_policy" {
  name   = "${var.project_name}-${var.stage}-lambda-sqs-send"
  policy = data.aws_iam_policy_document.lambda_sqs_send.json
  tags   = var.tags
}

resource "aws_iam_role_policy_attachment" "lambda_sqs_attach" {
  role       = aws_iam_role.api_lambda_role.name
  policy_arn = aws_iam_policy.lambda_sqs_policy.arn
}

output "sqs_queue_url" {
  value = aws_sqs_queue.tasks.id
}
