output "http_api_url" {
  value = "${aws_apigatewayv2_api.http.api_endpoint}/${aws_apigatewayv2_stage.dev.name}"
}


output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.this.id
}

output "cognito_client_id" {
  value = aws_cognito_user_pool_client.app.id
}

output "cognito_domain" {
  value = aws_cognito_user_pool_domain.domain.domain
}

output "s3_bucket_name" {
  value = aws_s3_bucket.files.bucket
}

output "sqs_queue_url" {
  value = aws_sqs_queue.tasks.id
}

output "sns_alerts_topic_arn" {
  value = aws_sns_topic.alerts.arn
}

output "frontend_bucket_name" {
  value = aws_s3_bucket.frontend.bucket
}

output "cloudfront_domain" {
  value = aws_cloudfront_distribution.frontend.domain_name
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.frontend.id
}

output "frontend_url" {
  value = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}