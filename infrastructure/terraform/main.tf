# ====================================================================================
# main.tf
# Provider + S3 + SNS + Step Functions + EventBridge + GitHub OIDC + IAM Roles
# (totalmente comentado, sem tags em IAM para evitar permissões adicionais)
# ====================================================================================

terraform {
  required_version = ">= 1.5.0"         # Versão mínima do Terraform
  required_providers {
    aws = {
      source  = "hashicorp/aws"         # Fonte oficial do provider AWS
      version = ">= 5.0"                # Versão mínima do provider AWS
    }
  }
}

# ------------------------------------------------------------------------------
# Provider AWS: usa as variáveis definidas no variables.tf (region/profile)
#   var.aws_region  -> região (ex.: eu-central-1)
#   var.profile     -> perfil local (~/.aws/credentials). No GitHub Actions
#                      isto é ignorado porque usamos OIDC (assumeRole).
# ------------------------------------------------------------------------------
provider "aws" {
  region  = var.aws_region
  profile = var.profile
}

# ------------------------------------------------------------------------------
# Locais: nomes derivados das variáveis (bucket final e URI)
# ------------------------------------------------------------------------------
locals {
  bucket_final_name = "${var.bucket_name}-${var.suffix}"  # Ex.: shopflow-ctw04557
  bucket_uri        = "s3://${local.bucket_final_name}"   # Ex.: s3://shopflow-ctw04557
}

# ------------------------------------------------------------------------------
# S3: bucket + versioning + encriptação + bloqueio de acesso público + lifecycle
# ------------------------------------------------------------------------------
resource "aws_s3_bucket" "data_bucket" {
  bucket = local.bucket_final_name   # Nome único global do bucket
}

resource "aws_s3_bucket_versioning" "data_bucket_versioning" {
  bucket = aws_s3_bucket.data_bucket.id
  versioning_configuration {
    status = "Enabled"               # Liga controlo de versões
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_bucket_encryption" {
  bucket = aws_s3_bucket.data_bucket.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"       # Encriptação SSE-S3
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data_bucket_block_public" {
  bucket                  = aws_s3_bucket.data_bucket.id
  block_public_acls       = true     # Bloqueia ACLs públicas
  block_public_policy     = true     # Bloqueia policies públicas
  ignore_public_acls      = true     # Ignora ACLs públicas existentes
  restrict_public_buckets = true     # Restringe completamente acesso público
}

resource "aws_s3_bucket_lifecycle_configuration" "data_bucket_lifecycle" {
  bucket = aws_s3_bucket.data_bucket.id
  rule {
    id     = "expire-old-logs"       # Nome da regra de ciclo de vida
    status = "Enabled"               # Ativa a regra
    filter {}                        # Sem filtro => aplica a tudo
    expiration {
      days = 90                      # Apaga objetos com > 90 dias
    }
  }
}

# ------------------------------------------------------------------------------
# SNS: Tópico de alertas + (opcional) subscrição por e-mail
#   var.alert_email -> se vazio, não cria a subscrição
# ------------------------------------------------------------------------------
resource "aws_sns_topic" "alerts" {
  name = "shopflow-alerts"           # Nome do tópico SNS
}

resource "aws_sns_topic_subscription" "alerts_email" {
  count     = length(var.alert_email) > 0 ? 1 : 0  # Cria apenas se há email
  topic_arn = aws_sns_topic.alerts.arn            # ARN do tópico
  protocol  = "email"                              # Tipo: e-mail
  endpoint  = var.alert_email                      # Endereço de e-mail
}

# ------------------------------------------------------------------------------
# IAM para Step Functions (role que a State Machine usa para executar)
#   - assume_role_policy: permite ao serviço "states" assumir a role
#   - policy: permitir logs e (no futuro) invocar Lambdas
# ------------------------------------------------------------------------------
data "aws_iam_policy_document" "sfn_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]        # Ação de assumir a role
    principals {
      type        = "Service"           # Principal é um serviço AWS
      identifiers = ["states.amazonaws.com"]  # Step Functions
    }
  }
}

resource "aws_iam_role" "sfn_role" {
  name               = "shopflow-sfn-role"                      # Nome da role
  assume_role_policy = data.aws_iam_policy_document.sfn_assume_role.json  # Trust policy
  # (Sem tags para evitar necessidade de iam:TagRole)
}

data "aws_iam_policy_document" "sfn_policy" {
  statement {
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]  # Permissões de logs
    resources = ["*"]                                                                  # Simplificado (podes restringir depois)
  }
  statement {
    actions   = ["lambda:InvokeFunction"]   # Permite invocar Lambdas (se/ quando existirem)
    resources = ["*"]                       # Restringe a ARNs concretos quando tiveres as Lambdas
  }
}

resource "aws_iam_policy" "sfn_policy" {
  name   = "shopflow-sfn-policy"                               # Nome da policy gerida
  policy = data.aws_iam_policy_document.sfn_policy.json        # JSON da policy
}

resource "aws_iam_role_policy_attachment" "sfn_role_attach" {
  role       = aws_iam_role.sfn_role.name                      # Role alvo
  policy_arn = aws_iam_policy.sfn_policy.arn                   # Policy a anexar
}

# ------------------------------------------------------------------------------
# Step Function (State Machine) – definição mínima de exemplo
# ------------------------------------------------------------------------------
resource "aws_sfn_state_machine" "shopflow_main" {
  name     = "shopflow-main"                 # Nome da state machine
  role_arn = aws_iam_role.sfn_role.arn      # Role que a SFN usa

  # Definição em Amazon States Language (aqui jsonencode de um mapa HCL)
  definition = jsonencode({
    Comment = "ShopFlow simple state machine"   # Comentário descritivo
    StartAt = "FirstStep"                       # Estado inicial
    States = {
      "FirstStep" = {                           # Um único estado "Pass"
        Type   = "Pass"                         # Tipo "Pass" (faz nada e passa)
        Result = "Hello from Step Functions!"   # Resultado devolvido
        End    = true                           # Marca fim do fluxo
      }
    }
  })
}

# ------------------------------------------------------------------------------
# IAM para EventBridge iniciar a Step Function (role + policy + attachment)
# ------------------------------------------------------------------------------
data "aws_iam_policy_document" "events_to_sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]           # EventBridge assumirá esta role
    principals {
      type        = "Service"              # Serviço AWS
      identifiers = ["events.amazonaws.com"]  # EventBridge
    }
  }
}

data "aws_iam_policy_document" "events_to_sfn_policy" {
  statement {
    actions   = ["states:StartExecution"]             # Permite arrancar execuções
    resources = [aws_sfn_state_machine.shopflow_main.arn]  # Apenas na nossa SFN
  }
}

resource "aws_iam_role" "events_to_sfn" {
  name               = "shopflow-events-to-sfn"                     # Nome da role
  assume_role_policy = data.aws_iam_policy_document.events_to_sfn_assume.json  # Trust policy
}

resource "aws_iam_policy" "events_to_sfn" {
  name   = "shopflow-events-to-sfn"                    # Nome da policy
  policy = data.aws_iam_policy_document.events_to_sfn_policy.json  # JSON
}

resource "aws_iam_role_policy_attachment" "events_to_sfn" {
  role       = aws_iam_role.events_to_sfn.name   # Role alvo
  policy_arn = aws_iam_policy.events_to_sfn.arn  # Policy a anexar
}

# ------------------------------------------------------------------------------
# EventBridge: regra diária (cron 02:00 UTC) que chama a Step Function
# ------------------------------------------------------------------------------
resource "aws_cloudwatch_event_rule" "daily" {
  name                = "shopflow-daily-schedule"   # Nome da regra
  schedule_expression = "cron(0 2 * * ? *)"         # Cron 02:00 UTC
  description         = "Trigger ShopFlow Step Function daily"
}

resource "aws_cloudwatch_event_target" "daily_target" {
  rule      = aws_cloudwatch_event_rule.daily.name   # Nome da regra
  target_id = "sfn-start"                            # ID do target (label)
  arn       = aws_sfn_state_machine.shopflow_main.arn  # Alvo: a nossa SFN
  role_arn  = aws_iam_role.events_to_sfn.arn         # Role que o EventBridge assume

  # Payload opcional entregue à SFN no input (exemplo com placeholders)
  input = jsonencode({
    etlFunctionArn = "REPLACE_WITH_ETL_LAMBDA_ARN"   # Substitui quando tiveres Lambda
    dqFunctionArn  = "REPLACE_WITH_DQ_LAMBDA_ARN"    # Substitui quando tiveres Lambda
    notifyTopicArn = aws_sns_topic.alerts.arn        # ARN do SNS para notificar
  })
}

# ------------------------------------------------------------------------------
# CloudWatch: alarme de falhas da Step Function + dashboard (ficheiro externo)
# ------------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "sfn_failures" {
  alarm_name          = "shopflow-state-machine-failures"  # Nome do alarme
  alarm_description   = "Alerts when Step Functions executions fail"
  namespace           = "AWS/States"                       # Namespace de métricas SFN
  metric_name         = "ExecutionsFailed"                 # Métrica alvo
  statistic           = "Sum"                              # Agregação
  period              = 300                                # Janela 5 min
  evaluation_periods  = 1                                  # Nº de janelas para avaliar
  threshold           = 1                                  # >=1 falha dispare alarme
  comparison_operator = "GreaterThanOrEqualToThreshold"    # Condição

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.shopflow_main.arn  # Métrica por SFN
  }

  alarm_actions = [aws_sns_topic.alerts.arn]   # Para onde enviar alarme
  ok_actions    = [aws_sns_topic.alerts.arn]   # Notificar quando voltar a OK
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "ShopFlow-Pipeline"                                        # Nome
  dashboard_body = file("${path.module}/../../monitoring/cloudwatch_dashboard.json")  # JSON do dashboard
}

# ------------------------------------------------------------------------------
# GitHub OIDC: provider + role que o GitHub Actions vai assumir
#   - OIDC provider aponta para o emissor do GitHub
#   - Role "github-actions-deploy-role" com trust policy para o teu repositório
#   - Anexamos PowerUserAccess (simples para demo) + policy inline de PassRole
# ------------------------------------------------------------------------------
resource "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"  # URL do emissor OIDC

  client_id_list  = ["sts.amazonaws.com"]             # Audiência esperada
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]  # Thumbprint raiz

  lifecycle { prevent_destroy = true }                # Evita destruição acidental
}

# Só para obter o ID da conta e poderes referenciar se precisares
data "aws_caller_identity" "current" {}

# ---- TRUST POLICY para a role que o Actions vai assumir (com OIDC)
#      ATENÇÃO ao valor do repositório/refs abaixo!
data "aws_iam_policy_document" "gh_trust" {
  statement {
    sid     = "AllowGitHubOIDC"                        # Identificador da regra
    actions = ["sts:AssumeRoleWithWebIdentity"]        # Ação via OIDC

    principals {
      type        = "Federated"                        # Principal federado (OIDC)
      identifiers = [aws_iam_openid_connect_provider.github.arn]  # OIDC provider
    }

    # Emissor do token do GitHub (tem de bater certo)
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:iss"
      values   = ["https://token.actions.githubusercontent.com"]
    }

    # Audiência do token – o Actions usa "sts.amazonaws.com"
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # *** MUDA AQUI se o repo/branch for diferente! ***
    # Autoriza:
    #  - main
    #  - quaisquer outras branches (*)
    #  - merges de PRs (refs/pull/*:merge)
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:ppires21/Data_Academy_Final_Exercise:ref:refs/heads/main",
        "repo:ppires21/Data_Academy_Final_Exercise:ref:refs/heads/*",
        "repo:ppires21/Data_Academy_Final_Exercise:ref:refs/pull/*:merge"
      ]
    }
  }
}

# Role que o GitHub Actions vai assumir via OIDC
resource "aws_iam_role" "github_actions" {
  name               = "github-actions-deploy-role"             # Nome da role
  description        = "Role assumida pelo GitHub Actions (OIDC) para aplicar Terraform."
  assume_role_policy = data.aws_iam_policy_document.gh_trust.json  # Trust policy OIDC
  # (Sem tags para evitar necessidade de iam:UpdateAssumeRolePolicy/TagRole adicionais)
}

# Para simplificar a demo: permissões amplas. Em produção, reduzir!
resource "aws_iam_role_policy_attachment" "github_poweruser" {
  role       = aws_iam_role.github_actions.name                 # Role alvo
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"        # Managed policy
}

# Permite ao GitHub Actions fazer "iam:PassRole" na role usada pelo EventBridge
data "aws_iam_policy_document" "github_allow_passrole_doc" {
  statement {
    sid      = "AllowPassRoleToEventsToSfn"                     # Identificador
    actions  = ["iam:PassRole"]                                 # PassRole
    resources = [aws_iam_role.events_to_sfn.arn]                # Só nesta role
  }
}

resource "aws_iam_role_policy" "github_allow_passrole" {
  name   = "github-allow-passrole-events-to-sfn"                # Nome da policy inline
  role   = aws_iam_role.github_actions.id                       # Role onde anexar
  policy = data.aws_iam_policy_document.github_allow_passrole_doc.json  # JSON
}
