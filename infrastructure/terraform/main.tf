# ---------------------------
# main.tf
# Provider + Recursos (S3, SNS, IAM, EventBridge, CloudWatch, Step Functions)
# ---------------------------

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.profile
}

# ---------------------------
# S3: Bucket de dados
# ---------------------------

locals {
  bucket_final_name = "${var.bucket_name}-${var.suffix}"
  bucket_uri        = "s3://${local.bucket_final_name}"
}

resource "aws_s3_bucket" "data_bucket" {
  bucket = local.bucket_final_name
}

resource "aws_s3_bucket_versioning" "data_bucket_versioning" {
  bucket = aws_s3_bucket.data_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_bucket_encryption" {
  bucket = aws_s3_bucket.data_bucket.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data_bucket_block_public" {
  bucket                  = aws_s3_bucket.data_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "data_bucket_lifecycle" {
  bucket = aws_s3_bucket.data_bucket.id
  rule {
    id     = "expire-old-logs"
    status = "Enabled"
    filter {}
    expiration {
      days = 90
    }
  }
}

# ---------------------------
# SNS: Alertas
# ---------------------------

resource "aws_sns_topic" "alerts" {
  name = "shopflow-alerts"
}

resource "aws_sns_topic_subscription" "alerts_email" {
  count     = length(var.alert_email) > 0 ? 1 : 0
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ---------------------------
# Step Functions: IAM Role + Policy
# ---------------------------

data "aws_iam_policy_document" "sfn_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"                # 'Service' com S maiúsculo
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sfn_role" {
  name               = "shopflow-sfn-role"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume_role.json
}

data "aws_iam_policy_document" "sfn_policy" {
  statement {
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["*"]
  }

  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = ["*"] # Restringe mais tarde quando tiveres as Lambdas
  }
}

resource "aws_iam_policy" "sfn_policy" {
  name   = "shopflow-sfn-policy"
  policy = data.aws_iam_policy_document.sfn_policy.json
}

resource "aws_iam_role_policy_attachment" "sfn_role_attach" {
  role       = aws_iam_role.sfn_role.name
  policy_arn = aws_iam_policy.sfn_policy.arn
}

# ---------------------------
# Step Function (State Machine)
# ---------------------------

resource "aws_sfn_state_machine" "shopflow_main" {
  name     = "shopflow-main"
  role_arn = aws_iam_role.sfn_role.arn

  definition = jsonencode({
    Comment = "ShopFlow simple state machine"
    StartAt = "FirstStep"
    States = {
      "FirstStep" = {
        Type   = "Pass"
        Result = "Hello from Step Functions!"
        End    = true
      }
    }
  })
}

# ---------------------------
# IAM: Role e Policy para o EventBridge iniciar a Step Function
# ---------------------------

data "aws_iam_policy_document" "events_to_sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"                 # 'Service' com S maiúsculo
      identifiers = ["events.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "events_to_sfn_policy" {
  statement {
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.shopflow_main.arn]
  }
}

resource "aws_iam_role" "events_to_sfn" {
  name               = "shopflow-events-to-sfn"
  assume_role_policy = data.aws_iam_policy_document.events_to_sfn_assume.json
}

resource "aws_iam_policy" "events_to_sfn" {
  name   = "shopflow-events-to-sfn"
  policy = data.aws_iam_policy_document.events_to_sfn_policy.json
}

resource "aws_iam_role_policy_attachment" "events_to_sfn" {
  role       = aws_iam_role.events_to_sfn.name
  policy_arn = aws_iam_policy.events_to_sfn.arn
}

# ---------------------------
# EventBridge: regra diária que dispara a Step Function
# ---------------------------

resource "aws_cloudwatch_event_rule" "daily" {
  name                = "shopflow-daily-schedule"
  schedule_expression = "cron(0 2 * * ? *)" # 02:00 UTC
  description         = "Trigger ShopFlow Step Function daily"
}

# 👇 Só cria o target quando create_events_target=true
resource "aws_cloudwatch_event_target" "daily_target" {
  count     = var.create_events_target ? 1 : 0
  rule      = aws_cloudwatch_event_rule.daily.name
  target_id = "sfn-start"
  arn       = aws_sfn_state_machine.shopflow_main.arn
  role_arn  = aws_iam_role.events_to_sfn.arn

  input = jsonencode({
    etlFunctionArn = "REPLACE_WITH_ETL_LAMBDA_ARN"
    dqFunctionArn  = "REPLACE_WITH_DQ_LAMBDA_ARN"
    notifyTopicArn = aws_sns_topic.alerts.arn
  })
}

# ---------------------------
# CloudWatch: Alarmes e Dashboard
# ---------------------------

resource "aws_cloudwatch_metric_alarm" "sfn_failures" {
  alarm_name          = "shopflow-state-machine-failures"
  alarm_description   = "Alerts when Step Functions executions fail"
  namespace           = "AWS/States"
  metric_name         = "ExecutionsFailed"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.shopflow_main.arn
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "ShopFlow-Pipeline"
  dashboard_body = file("${path.module}/../../monitoring/cloudwatch_dashboard.json")
}

# ---------------------------
# GitHub OIDC + Role usada pelo GitHub Actions
# ---------------------------

resource "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"

  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]

  lifecycle { prevent_destroy = true }
}

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "gh_trust" {
  statement {
    sid     = "AllowGitHubOIDC"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:iss"
      values   = ["https://token.actions.githubusercontent.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:data-academy/shopflow-pipeline:refs/heads/main"]
    }

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "github-actions-deploy-role"
  description        = "Role assumida pelo GitHub Actions (OIDC) para aplicar Terraform."
  assume_role_policy = data.aws_iam_policy_document.gh_trust.json

  # 👇 EVITA que um plan futuro tente atualizar a trust policy (e leve AccessDenied)
  lifecycle {
    ignore_changes = [assume_role_policy]
  }
}

resource "aws_iam_role_policy_attachment" "github_poweruser" {
  role       = aws_iam_role.github_actions.name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}

# Inline policy para o Actions poder fazer iam:PassRole só nesta role de EventBridge
data "aws_iam_policy_document" "github_allow_passrole_doc" {
  statement {
    sid     = "AllowPassRoleToEventsToSfn"
    actions = ["iam:PassRole"]
    resources = [aws_iam_role.events_to_sfn.arn]
  }
}

resource "aws_iam_role_policy" "github_allow_passrole" {
  name   = "github-allow-passrole-events-to-sfn"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_allow_passrole_doc.json
}
