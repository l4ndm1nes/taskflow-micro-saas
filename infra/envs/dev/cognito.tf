# infra/envs/dev/cognito.tf

data "aws_region" "current" {}

resource "aws_cognito_user_pool" "this" {
  name                     = "${var.project_name}-${var.stage}-users"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  admin_create_user_config {
    allow_admin_create_user_only = false
  }

  password_policy {
    minimum_length    = var.cognito_password_minimum_length
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = true
  }

  tags = var.tags
}

resource "aws_cognito_user_pool_client" "app" {
  name         = "${var.project_name}-${var.stage}-app"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret = false

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]

  callback_urls = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://${aws_cloudfront_distribution.frontend.domain_name}/",
  ]
  logout_urls = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://${aws_cloudfront_distribution.frontend.domain_name}/",
  ]

  # Keep for CLI flows you already use
  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_ADMIN_USER_PASSWORD_AUTH"
  ]

  # Token lifetimes (numbers + lowercase units)
  refresh_token_validity = 30
  access_token_validity  = 60
  id_token_validity      = 60
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  # Uniform error for "user not found" vs "wrong password"
  prevent_user_existence_errors = "ENABLED"
}

resource "random_id" "cog" {
  byte_length = 2
}

resource "aws_cognito_user_pool_domain" "domain" {
  domain       = "taskflow-dev-${random_id.cog.hex}"
  user_pool_id = aws_cognito_user_pool.this.id
}

# HTTP API JWT Authorizer (uses Cognito as issuer)
resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id           = aws_apigatewayv2_api.http.id
  name             = "cognito-jwt"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.app.id]
    issuer   = "https://cognito-idp.${data.aws_region.current.name}.amazonaws.com/${aws_cognito_user_pool.this.id}"
  }
}
