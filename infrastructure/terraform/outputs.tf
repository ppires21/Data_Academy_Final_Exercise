# ---------------------------
# outputs.tf
# Valores úteis após o apply
# ---------------------------

output "bucket_name" {                             # Nome do bucket
  description = "Final S3 bucket name"
  value       = aws_s3_bucket.data_bucket.bucket
}

output "bucket_uri" {                              # URI do bucket
  description = "S3 URI for the data bucket"
  value       = local.bucket_uri
}

output "bucket_arn" {                              # ARN do bucket
  description = "ARN of the data bucket"
  value       = aws_s3_bucket.data_bucket.arn
}

output "sns_topic_arn" {                           # ARN do SNS de alertas
  description = "SNS topic ARN for alerts"
  value       = aws_sns_topic.alerts.arn
}

output "event_rule_name" {                         # Nome da regra de agendamento
  description = "Name of the daily EventBridge rule"
  value       = aws_cloudwatch_event_rule.daily.name
}

output "events_to_sfn_role_arn" {                  # ARN da role usada pelo EventBridge
  description = "IAM role ARN used by EventBridge to start SFN"
  value       = aws_iam_role.events_to_sfn.arn
}

output "sfn_alarm_name" {                          # Nome do alarme de falhas SFN
  description = "CloudWatch alarm name for Step Functions failures"
  value       = aws_cloudwatch_metric_alarm.sfn_failures.alarm_name
}

output "dashboard_name" {                          # Nome do dashboard
  description = "CloudWatch dashboard name"
  value       = aws_cloudwatch_dashboard.main.dashboard_name
}

output "state_machine_arn" {                       # ARN da Step Function criada
  description = "ARN of the Step Function created"
  value       = aws_sfn_state_machine.shopflow_main.arn
}

# ---------------------------
# (NOVO) ARN da role assumida pelo GitHub Actions (para meteres no secret)
# ---------------------------

output "github_actions_role_arn" {                 # ARN da IAM Role do Actions
  description = "ARN of the IAM Role assumed by GitHub Actions via OIDC"
  value       = aws_iam_role.github_actions.arn
}
