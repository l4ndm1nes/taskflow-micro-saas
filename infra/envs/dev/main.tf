terraform {
  backend "s3" {
    bucket         = "tf-state-taskflow-s3"
    key            = "envs/dev/terraform.tfstate"
    region         = "eu-central-1"
    dynamodb_table = "tf-lock-taskflow"
    encrypt        = true
    profile        = "terraform-dev"
  }
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 5.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.5" }
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
}
