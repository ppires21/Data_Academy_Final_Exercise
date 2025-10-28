# ---------------------------
# main.tf
# Provider + Recursos (S3, SNS, IAM, EventBridge, CloudWatch, Step Functions)
# ---------------------------

terraform {
  required_version = ">= 1.5.0"                # versão mínima do Terraform
  required_providers {                         # providers necessários
    aws = {
      source  = "hashicorp/aws"                # origem do provider AWS
      version = ">= 5.0"                       # versão mínima do provider AWS
    }
  }
}

provider "aws" {
  region  = var.aws_region                     # região AWS (definida em variables.tf / tfvars)
  profile = var.profile                        # profile local (para execuções fora do Actions)
}

# ---------------------------
# S3: Bucket de dados
# ---------------------------

locals {
  bucket_final_name = "${var.bucket_name}-${var.suffix}"  # nome globalmente único do bucket
  bucket_uri        = "s3://${local.bucket_final_name}"   # URI útil para outputs
}

resource "aws_s3_bucket" "data_bucket" {
  bucket = local.bucket_final_name              # nome do bucket
}

resource "aws_s3_bucket_versioning" "data_bucket_versioning" {
  bucket = aws_s3_bucket.data_bucket.id         # id do bucket acima
  versioning_configuration {
    status = "Enabled"                          # ativa versionamento
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_bucket_encryption" {
  bucket = aws_s3_bucket.data_bucket.id         # id do bucket
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"                  # encriptação no lado do servidor
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data_bucket_block_public" {
  bucket                  = aws_s3_bucket.data_bucket.id  # id do bucket
  block_public_acls       = true                          # bloqueia ACLs públicas
  block_public_policy     = true                          # bloqueia policies públicas
  ignore_public_acls      = true                          # ignora ACLs públicas
  restrict_public_buckets = true                          # restringe buckets públicos
}

resource "aws_s3_bucket_lifecycle_configuration" "data_bucket_lifecycle" {
  bucket = aws_s3_bucket.data_bucket.id         # id do bucket
  rule {
    id     = "expire-old-logs"                  # id da regra
    status = "Enabled"                          # ativa a regra
    filter {}                                   # sem filtro (aplica a tudo)
    expiration {
      days = 90                                 # expira objetos com >90 dias
    }
  }
}

# ---------------------------
# SNS: Alertas
# ---------------------------

resource "aws_sns_topic" "alerts" {
  name = "shopflow-alerts"                      # nome do tópico SNS
}

resource "aws_sns_topic_subscription" "alerts_email" {
  count     = length(var.alert_email) > 0 ? 1 : 0  # cria só se existir email
  topic_arn = aws_sns_topic.alerts.arn             # ARN do tópico SNS
  protocol  = "email"                               # protocolo de subscrição
  endpoint  = var.alert_email                       # email que recebe alertas
}

# ---------------------------
# Step Functions: IAM Role + Policy
# ---------------------------

data "aws_iam_policy_document" "sfn_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]                # permite a assunção da role
    principals {
      type        = "Service"                   # principal é um serviço AWS
      identifiers = ["states.amazonaws.com"]    # serviço Step Functions
    }
  }
}

resource "aws_iam_role" "sfn_role" {
  name               = "shopflow-sfn-role"      # nome da role de execução da SFN
  assume_role_policy = data.aws_iam_policy_document.sfn_assume_role.json  # trust policy
  # (sem tags para não exigir iam:TagRole)
}

data "aws_iam_policy_document" "sfn_policy" {
  statement {
    actions = [                                 # permissões de logs
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["*"]                           # pode ser afinado mais tarde
  }

  statement {
    actions   = ["lambda:InvokeFunction"]       # permitir invocar Lambdas
    resources = ["*"]                           # restringe mais tarde às tuas Lambdas
  }
}

resource "aws_iam_policy" "sfn_policy" {
  name   = "shopflow-sfn-policy"                # nome da policy gerida
  policy = data.aws_iam_policy_document.sfn_policy.json  # JSON da policy
}

resource "aws_iam_role_policy_attachment" "sfn_role_attach" {
  role       = aws_iam_role.sfn_role.name       # role de execução da SFN
  policy_arn = aws_iam_policy.sfn_policy.arn    # anexa a policy acima
}

# ---------------------------
# Step Function (State Machine)
# ---------------------------

resource "aws_sfn_state_machine" "shopflow_main" {
  name     = "shopflow-main"                    # nome da state machine
  role_arn = aws_iam_role.sfn_role.arn          # role de execução da SFN

  definition = jsonencode({                      # definição ASL (simples Pass)
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
    actions = ["sts:AssumeRole"]                # EventBridge assume esta role
    principals {
      type        = "Service"                   # serviço AWS
      identifiers = ["events.amazonaws.com"]    # EventBridge
    }
  }
}

data "aws_iam_policy_document" "events_to_sfn_policy" {
  statement {
    actions   = ["states:StartExecution"]       # permite iniciar execuções
    resources = [aws_sfn_state_machine.shopflow_main.arn]  # apenas esta SFN
  }
}

resource "aws_iam_role" "events_to_sfn" {
  name               = "shopflow-events-to-sfn" # role usada pelo EventBridge Target
  assume_role_policy = data.aws_iam_policy_document.events_to_sfn_assume.json
  # (sem tags para não exigir iam:TagRole)
}

resource "aws_iam_policy" "events_to_sfn" {
  name   = "shopflow-events-to-sfn"             # nome da policy
  policy = data.aws_iam_policy_document.events_to_sfn_policy.json
}

resource "aws_iam_role_policy_attachment" "events_to_sfn" {
  role       = aws_iam_role.events_to_sfn.name  # role acima
  policy_arn = aws_iam_policy.events_to_sfn.arn # anexa policy de StartExecution
}

# ---------------------------
# EventBridge: regra diária que dispara a Step Function
# ---------------------------

resource "aws_cloudwatch_event_rule" "daily" {
  name                = "shopflow-daily-schedule"   # nome da regra
  schedule_expression = "cron(0 2 * * ? *)"         # 02:00 UTC diário
  description         = "Trigger ShopFlow Step Function daily"
}

resource "aws_cloudwatch_event_target" "daily_target" {
  rule      = aws_cloudwatch_event_rule.daily.name  # liga à regra acima
  target_id = "sfn-start"                           # id do target
  arn       = aws_sfn_state_machine.shopflow_main.arn  # alvo = SFN
  role_arn  = aws_iam_role.events_to_sfn.arn        # role que o target assume

  input = jsonencode({                               # payload de exemplo
    etlFunctionArn = "REPLACE_WITH_ETL_LAMBDA_ARN"   # placeholder ETL
    dqFunctionArn  = "REPLACE_WITH_DQ_LAMBDA_ARN"    # placeholder DQ
    notifyTopicArn = aws_sns_topic.alerts.arn        # envia ARN do SNS
  })
}

# ---------------------------
# CloudWatch: Alarmes e Dashboard
# ---------------------------

resource "aws_cloudwatch_metric_alarm" "sfn_failures" {
  alarm_name          = "shopflow-state-machine-failures"     # nome do alarme
  alarm_description   = "Alerts when Step Functions executions fail"
  namespace           = "AWS/States"                          # namespace métrica
  metric_name         = "ExecutionsFailed"                    # métrica de falhas
  statistic           = "Sum"                                 # sumariza falhas
  period              = 300                                   # janela 5 min
  evaluation_periods  = 1                                     # 1 período
  threshold           = 1                                     # >=1 falha
  comparison_operator = "GreaterThanOrEqualToThreshold"       # operador

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.shopflow_main.arn # dimensão = SFN
  }

  alarm_actions = [aws_sns_topic.alerts.arn]                  # envia alerta
  ok_actions    = [aws_sns_topic.alerts.arn]                  # notifica OK
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "ShopFlow-Pipeline"                        # nome do dashboard
  dashboard_body = file("${path.module}/../../monitoring/cloudwatch_dashboard.json")  # JSON externo
}

# ---------------------------
# GitHub OIDC + Role usada pelo GitHub Actions (CORRIGIDO)
# ---------------------------

# Lê o OIDC Provider público do GitHub (não cria/alterar — evita 403)
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"  # URL do emissor OIDC
}

# Trust policy para o GitHub Actions (subject alinhado ao teu repo/branch)
data "aws_iam_policy_document" "gh_trust" {
  statement {
    sid     = "AllowGitHubOIDC"                   # identificador da regra
    actions = ["sts:AssumeRoleWithWebIdentity"]   # permite AssumeRole via OIDC

    condition {
      test     = "StringEquals"                   # emissor tem de ser este URL
      variable = "token.actions.githubusercontent.com:iss"
      values   = ["https://token.actions.githubusercontent.com"]
    }

    condition {
      test     = "StringEquals"                   # audiência tem de ser STS
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # SUBJECT CORRETO para ESTE repositório e branch main:
    # formato: repo:OWNER/REPO:ref:refs/heads/BRANCH
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:ppires21/Data_Academy_Final_Exercise:ref:refs/heads/main"]
    }

    principals {
      type        = "Federated"                   # principal federado (OIDC)
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]  # ARN do provider lido acima
    }
  }
}

# Role que o GitHub Actions vai assumir
resource "aws_iam_role" "github_actions" {
  name               = "github-actions-deploy-role"   # nome da role
  description        = "Role assumida pelo GitHub Actions (OIDC) para aplicar Terraform."
  assume_role_policy = data.aws_iam_policy_document.gh_trust.json  # trust policy construída acima
}

# Dá permissões amplas (podes afinar mais tarde)
resource "aws_iam_role_policy_attachment" "github_poweruser" {
  role       = aws_iam_role.github_actions.name       # role do Actions
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"  # política gerida da AWS
}

# Permite ao Actions fazer iam:PassRole na role usada pelo EventBridge Target
data "aws_iam_policy_document" "github_allow_passrole_doc" {
  statement {
    sid       = "AllowPassRoleToEventsToSfn"          # id da regra
    actions   = ["iam:PassRole"]                      # ação necessária
    resources = [aws_iam_role.events_to_sfn.arn]      # restrito à role events_to_sfn
  }
}

resource "aws_iam_role_policy" "github_allow_passrole" {
  name   = "github-allow-passrole-events-to-sfn"      # nome da policy inline
  role   = aws_iam_role.github_actions.id             # associa à role do Actions
  policy = data.aws_iam_policy_document.github_allow_passrole_doc.json  # JSON da policy
}
