# =========================================
# File: infrastructure/terraform/iac_iteration4.tf
# Purpose: Provision infra for Iteration 4
#   - SNS topic for failure notifications
#   - IAM roles for EventBridge → Step Functions start, and Step Functions execution
#   - CloudWatch Alarm on Step Functions failures
#   - EventBridge schedule to trigger daily batch
#   - CloudWatch Dashboard loaded from external JSON file
# Notes:
#   - We DO NOT create the state machine here (CD step does),
#     but we wire alarms/schedule to its ARN via variables.
# =========================================

terraform {
  required_version = ">= 1.5.0"                               # Require TF version
  required_providers {                                        # Declare providers used
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region                                     # Use region variable
}

# -----------------------
# Variables
# -----------------------

variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "eu-central-1"
}

variable "alert_email" {
  description = "Email address to subscribe to SNS notifications (optional)"
  type        = string
  default     = ""                                            # Empty means no subscription
}

variable "state_machine_arn" {
  description = "ARN of the Step Functions state machine (created by CD)"
  type        = string
}

# -----------------------
# SNS for notifications
# -----------------------

resource "aws_sns_topic" "alerts" {
  name = "shopflow-alerts"                                    # SNS topic name
}

resource "aws_sns_topic_subscription" "alerts_email" {
  count     = length(var.alert_email) > 0 ? 1 : 0             # Create only if email provided
  topic_arn = aws_sns_topic.alerts.arn                        # Topic to subscribe
  protocol  = "email"                                         # Email protocol
  endpoint  = var.alert_email                                 # Recipient email
}

# -----------------------
# IAM role to allow EventBridge to start Step Functions executions
# -----------------------

data "aws_iam_policy_document" "events_to_sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]                              # Allow STS assume role
    principals {
      type        = "service"                                 # Principal service
      identifiers = ["events.amazonaws.com"]                  # EventBridge service
    }
  }
}

resource "aws_iam_role" "events_to_sfn" {
  name               = "shopflow-events-to-sfn-role"          # Role name
  assume_role_policy = data.aws_iam_policy_document.events_to_sfn_assume.json
}

data "aws_iam_policy_document" "events_to_sfn_policy" {
  statement {
    actions   = ["states:StartExecution"]                     # Permission to start sfn
    resources = [var.state_machine_arn]                       # Only our state machine
  }
}

resource "aws_iam_role_policy" "events_to_sfn_inline" {
  name   = "events-start-sfn"                                 # Inline policy name
  role   = aws_iam_role.events_to_sfn.id                      # Attach to role
  policy = data.aws_iam_policy_document.events_to_sfn_policy.json
}

# -----------------------
# EventBridge Schedule (daily at 02:00 UTC)
# -----------------------

resource "aws_cloudwatch_event_rule" "daily" {
  name                = "shopflow-daily-schedule"             # Rule name
  schedule_expression = "cron(0 2 * * ? *)"                   # 02:00 UTC daily
  description         = "Trigger ShopFlow Step Function daily"
}

resource "aws_cloudwatch_event_target" "daily_target" {
  rule      = aws_cloudwatch_event_rule.daily.name            # Attach to daily rule
  target_id = "sfn-start"                                     # Target id label
  arn       = var.state_machine_arn                           # Start this state machine
  role_arn  = aws_iam_role.events_to_sfn.arn                  # Use role that can start sfn

  input = jsonencode({                                        # Provide input required by state machine
    etlFunctionArn  = "REPLACE_WITH_ETL_LAMBDA_ARN"           # CI/CD can replace dynamically
    dqFunctionArn   = "REPLACE_WITH_DQ_LAMBDA_ARN"            # CI/CD can replace dynamically
    notifyTopicArn  = aws_sns_topic.alerts.arn                # SNS topic for failures
  })
}

# -----------------------
# CloudWatch Alarm on Step Functions Failures
# -----------------------

resource "aws_cloudwatch_metric_alarm" "sfn_failures" {
  alarm_name          = "shopflow-state-machine-failures"     # Alarm name
  alarm_description   = "Alerts when Step Functions executions fail"
  comparison_operator = "GreaterThanThreshold"                # Trigger if > threshold
  evaluation_periods  = 1                                     # 1 period enough
  metric_name         = "ExecutionsFailed"                    # SFN metric name
  namespace           = "AWS/States"                          # SFN metric namespace
  period              = 300                                   # 5 minutes period
  statistic           = "Sum"                                 # Sum over the period
  threshold           = 0                                     # >0 failures => alarm
  treat_missing_data  = "notBreaching"                        # Don't alarm if metric absent

  dimensions = {                                              # Dimension filter
    StateMachineArn = var.state_machine_arn
  }

  alarm_actions = [aws_sns_topic.alerts.arn]                  # Send to SNS on alarm
  ok_actions    = [aws_sns_topic.alerts.arn]                  # Notify when ok again
}

# -----------------------
# CloudWatch Dashboard (loaded from JSON file)
# -----------------------

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "ShopFlow-Pipeline"                        # Dashboard name
  dashboard_body = file("${path.module}/../../monitoring/cloudwatch_dashboard.json")
                                                             # Load JSON from repo
}
