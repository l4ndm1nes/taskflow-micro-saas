resource "aws_s3_bucket" "files" {
  bucket = "${var.project_name}-${var.stage}-files-${random_id.cog.hex}"
  tags   = var.tags
}

resource "aws_s3_bucket_public_access_block" "files" {
  bucket                  = aws_s3_bucket.files.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "files" {
  bucket = aws_s3_bucket.files.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "files" {
  bucket = aws_s3_bucket.files.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "files" {
  bucket = aws_s3_bucket.files.id

  # Очистка временных загрузок
  rule {
    id     = "tmp-uploads-cleanup"
    status = "Enabled"
    filter { prefix = "uploads/tmp/" }
    expiration { days = var.s3_lifecycle_tmp_expiration_days }
  }

  # Очистка старых загрузок пользователей (30 дней)
  rule {
    id     = "user-uploads-cleanup"
    status = "Enabled"
    filter { prefix = "uploads/" }
    expiration { days = var.s3_lifecycle_uploads_expiration_days }
    noncurrent_version_expiration { noncurrent_days = 7 }
  }

  # Очистка старых результатов (90 дней)
  rule {
    id     = "results-cleanup"
    status = "Enabled"
    filter { prefix = "results/" }
    expiration { days = var.s3_lifecycle_results_expiration_days }
    noncurrent_version_expiration { noncurrent_days = 30 }
  }

  # Переход в IA класс для экономии (через 30 дней)
  rule {
    id     = "transition-to-ia"
    status = "Enabled"
    filter {} # Применяется ко всем объектам
    transition {
      days          = var.s3_transition_to_ia_days
      storage_class = "STANDARD_IA"
    }
    transition {
      days          = var.s3_transition_to_glacier_days
      storage_class = "GLACIER"
    }
  }
}

resource "aws_s3_bucket_cors_configuration" "files" {
  bucket = aws_s3_bucket.files.id
  cors_rule {
    allowed_methods = ["PUT", "GET", "HEAD"]
    allowed_origins = var.cors_allowed_origins
    allowed_headers = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}

data "aws_iam_policy_document" "lambda_s3_access" {
  statement {
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:AbortMultipartUpload",
      "s3:ListBucketMultipartUploads",
      "s3:ListMultipartUploadParts"
    ]
    resources = [
      aws_s3_bucket.files.arn,
      "${aws_s3_bucket.files.arn}/*"
    ]
  }
}

resource "aws_iam_policy" "lambda_s3_policy" {
  name   = "${var.project_name}-${var.stage}-lambda-s3"
  policy = data.aws_iam_policy_document.lambda_s3_access.json
  tags   = var.tags
}

resource "aws_iam_role_policy_attachment" "lambda_s3_attach" {
  role       = aws_iam_role.api_lambda_role.name
  policy_arn = aws_iam_policy.lambda_s3_policy.arn
}

output "s3_bucket_name" {
  value = aws_s3_bucket.files.bucket
}
