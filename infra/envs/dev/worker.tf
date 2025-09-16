data "archive_file" "worker_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../services/worker"
  output_path = "${path.module}/../../../services/worker/dist_worker.zip"
}

data "aws_iam_policy_document" "worker_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "worker_role" {
  name               = "${var.project_name}-${var.stage}-worker-role"
  assume_role_policy = data.aws_iam_policy_document.worker_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "worker_policy_doc" {
  statement {
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility"]
    resources = [aws_sqs_queue.tasks.arn]
  }

  statement {
    actions   = ["dynamodb:UpdateItem", "dynamodb:GetItem"]
    resources = [aws_dynamodb_table.tasks.arn]
  }

  statement {
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:*:*:*"]
  }

  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.files.arn}/uploads/*"]
  }

  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.files.arn}/results/*"]
  }
}

resource "aws_iam_policy" "worker_policy" {
  name   = "${var.project_name}-${var.stage}-worker-policy"
  policy = data.aws_iam_policy_document.worker_policy_doc.json
  tags   = var.tags
}

resource "aws_iam_role_policy_attachment" "worker_attach" {
  role       = aws_iam_role.worker_role.name
  policy_arn = aws_iam_policy.worker_policy.arn
}

resource "aws_lambda_function" "worker" {
  function_name    = "${var.project_name}-${var.stage}-worker"
  role             = aws_iam_role.worker_role.arn
  runtime          = var.lambda_runtime
  handler          = "handler.handler"
  filename         = data.archive_file.worker_zip.output_path
  source_code_hash = data.archive_file.worker_zip.output_base64sha256
  timeout          = 30
  memory_size      = var.lambda_memory_size

  environment {
    variables = {
      STAGE       = var.stage
      TABLE_NAME  = aws_dynamodb_table.tasks.name
      BUCKET_NAME = aws_s3_bucket.files.bucket
    }
  }

  tracing_config {
    mode = "Active"
  }
  tags = var.tags
}

resource "aws_lambda_event_source_mapping" "worker_sqs" {
  event_source_arn = aws_sqs_queue.tasks.arn
  function_name    = aws_lambda_function.worker.arn
  batch_size       = 5
  enabled          = true
}
