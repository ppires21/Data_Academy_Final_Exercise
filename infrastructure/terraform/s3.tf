# infrastructure/terraform/s3.tf

#provider "aws" {
#  region = var.aws_region # Define region in variables
#}

resource "aws_s3_bucket" "data_bucket" {
  bucket = "ctw04557-ppires-academy-finalexercise-bucket" 
  tags = {
    Name        = "ShopFlow Data Bucket"
    Environment = var.environment
  }
}

# Enable versioning
resource "aws_s3_bucket_versioning" "data_bucket_versioning" {
  bucket = aws_s3_bucket.data_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Enable server-side encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "data_bucket_encryption" {
  bucket = aws_s3_bucket.data_bucket.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block public access
resource "aws_s3_bucket_public_access_block" "data_bucket_block_public" {
  bucket                  = aws_s3_bucket.data_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Optional: Lifecycle policy for cost optimization (per Bonus Challenges)
resource "aws_s3_bucket_lifecycle_configuration" "data_bucket_lifecycle" {
  bucket = aws_s3_bucket.data_bucket.id
  rule {
    id     = "archive-old-data"
    status = "Enabled"
    transition {
      days          = 30
      storage_class = "GLACIER"
    }
    expiration {
      days = 365
    }
  }
}

# Variables
#variable "aws_region" {
#  description = "AWS region for the S3 bucket"
#  default     = "eu-central-1"
#}

variable "environment" {
  description = "Deployment environment (dev, prod)"
  default     = "dev"
}