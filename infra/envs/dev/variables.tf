variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "eu-central-1"
}


variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "taskflow"
}

variable "stage" {
  description = "Environment stage (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "backend_bucket" {
  description = "S3 bucket for Terraform state"
  type        = string
  default     = "tf-state-taskflow-s3"
}

variable "backend_dynamodb_table" {
  description = "DynamoDB table for Terraform state locking"
  type        = string
  default     = "tf-lock-taskflow"
}

variable "lambda_runtime" {
  description = "Lambda runtime version"
  type        = string
  default     = "python3.11"
}

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 10
}

variable "lambda_memory_size" {
  description = "Lambda function memory size in MB"
  type        = number
  default     = 256
}

variable "api_throttling_rate_limit" {
  description = "API Gateway throttling rate limit (requests per second)"
  type        = number
  default     = 100
}

variable "api_throttling_burst_limit" {
  description = "API Gateway throttling burst limit"
  type        = number
  default     = 200
}

variable "log_retention_days" {
  description = "CloudWatch logs retention in days"
  type        = number
  default     = 14
}

variable "task_ttl_days" {
  description = "Task TTL in days"
  type        = number
  default     = 7
}

variable "cors_allowed_origins" {
  description = "CORS allowed origins"
  type        = list(string)
  default = [
    "http://localhost:5173",
    "http://127.0.0.1:5500",
    "http://localhost:8080",
    "*"
  ]
}

variable "s3_lifecycle_uploads_expiration_days" {
  description = "S3 uploads expiration in days"
  type        = number
  default     = 30
}

variable "s3_lifecycle_results_expiration_days" {
  description = "S3 results expiration in days"
  type        = number
  default     = 90
}

variable "s3_lifecycle_tmp_expiration_days" {
  description = "S3 tmp uploads expiration in days"
  type        = number
  default     = 1
}

variable "s3_transition_to_ia_days" {
  description = "Days after which objects transition to IA storage class"
  type        = number
  default     = 30
}

variable "s3_transition_to_glacier_days" {
  description = "Days after which objects transition to Glacier storage class"
  type        = number
  default     = 90
}

variable "sqs_visibility_timeout_seconds" {
  description = "SQS visibility timeout in seconds"
  type        = number
  default     = 300
}

variable "sqs_message_retention_seconds" {
  description = "SQS message retention in seconds"
  type        = number
  default     = 1209600
}

variable "sqs_max_receive_count" {
  description = "Maximum number of receives before moving to DLQ"
  type        = number
  default     = 3
}

variable "cognito_password_minimum_length" {
  description = "Cognito password minimum length"
  type        = number
  default     = 8
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default = {
    Project     = "TaskFlow"
    Environment = "dev"
    ManagedBy   = "Terraform"
  }
}
