# ---------------------------
# main.tf
# Provider + Recursos (S3, SNS, IAM, EventBridge, CloudWatch, Step Functions)
# + GitHub OIDC trust policy ajustada para:
#   repo: ppires21/Data_Academy_Final_Exercise  | branch: main
# ---------------------------

terraform {                                   # Bloco de configuração do Terraform
  required_version = ">= 1.5.0"               # Versão mínima do Terraform
  required_providers {                        # Provedores necessários
    aws = {                                   # Provedor AWS
      source  = "hashicorp/aws"               # Origem do provider
      version = ">= 5.0"                      # Versão mínima do provider AWS
    }
  }
}

provider "aws" {                              # Configuração do provider AWS
  region  = var.aws_region                    # Região (vem de variables.tf)
  profile = var.profile                       # Profile local (não usado no GitHub Actions)
}

# ---------------------------
# S3: Bucket de dados
# ---------------------------

locals {                                      # Variáveis locais úteis
  bucket_final_name = "${var.bucket_name}-${var.suffix}"  # Nome final único do bucket
  bucket_uri        = "s3://${local.bucket_final_name}"   # URI do bucket em S3
}

resource "aws_s3_bucket" "data_bucket" {      # Bucket S3
  bucket = local.bucket_final_name            # Nome do bucket
}

resource "aws_s3_bucket_versioning" "data_bucket_versioning" {  # Versionamento
  bucket = aws_s3_bucket.data_bucket.id       # ID do bucket alvo
  versioning_configuration {                  # Configuração de versionamento
    status = "Enabled"                        # Ativa versionamento
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_bucket_encryption" { # Encriptação
  bucket = aws_s3_bucket.data_bucket.id       # ID do bucket alvo
  rule {                                      # Regra de encriptação
    apply_server_side_encryption_by_default { # Encriptação por defeito
      sse_algorithm = "AES256"                # Algoritmo SSE-S3
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data_bucket_block_public" { # Bloqueio de acesso público
  bucket                  = aws_s3_bucket.data_bucket.id  # ID do bucket
  block_public_acls       = true               # Bloqueia ACLs públicas
  block_public_policy     = true               # Bloqueia políticas públicas
  ignore_public_acls      = true               # Ignora ACLs públicas
  restrict_public_buckets = true               # Restringe buckets públicos
}

resource "aws_s3_bucket_lifecycle_configuration" "data_bucket_lifecycle" { # Política de ciclo de vida
  bucket = aws_s3_bucket.data_bucket.id       # ID do bucket
  rule {                                      # Regra 1
    id     = "expire-old-logs"                # Identificador da regra
    status = "Enabled"                        # Ativa a regra
    filter {}                                 # Sem filtro (aplica a todos os objetos)
    expiration {                              # Expiração
      days = 90                               # Expira após 90 dias
    }
  }
}

# ---------------------------
# SNS: Alertas
# ---------------------------

resource "aws_sns_topic" "alerts" {           # Tópico SNS para alertas
  name = "shopflow-alerts"                    # Nome do tópico
}

resource "aws_sns_topic_subscription" "alerts_email" {        # Subscrição opcional por email
  count     = length(var.alert_email) > 0 ? 1 : 0  # Cria só se tiver email
  topic_arn = aws_sns_topic.alerts.arn        # ARN do tópico
  protocol  = "email"                          # Protocolo email
  endpoint  = var.alert_email                  # Endereço de email do destinatário
}

# ---------------------------
# Step Functions: IAM Role + Policy
# ---------------------------

data "aws_iam_policy_document" "sfn_assume_role" {  # Trust policy da role de execução da SFN
  statement {                               # Declaração da policy
    actions = ["sts:AssumeRole"]            # Ação: assumir role
    principals {                            # Quem pode assumir
      type        = "Service"               # Principal do tipo serviço
      identifiers = ["states.amazonaws.com"]# Serviço Step Functions
    }
  }
}

resource "aws_iam_role" "sfn_role" {        # Role de execução da Step Function
  name               = "shopflow-sfn-role"  # Nome da role
  assume_role_policy = data.aws_iam_policy_document.sfn_assume_role.json  # Trust policy
}

data "aws_iam_policy_document" "sfn_policy" { # Policy de permissões da SFN
  statement {                               # Declaração 1
    actions = [                             # Ações para CloudWatch Logs
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["*"]                       # Em demo deixamos "*"
  }

  statement {                               # Declaração 2
    actions   = ["lambda:InvokeFunction"]   # Permissão para invocar Lambdas
    resources = ["*"]                       # Restringir quando tiveres ARNs concretos
  }
}

resource "aws_iam_policy" "sfn_policy" {    # Recurso da policy gerida
  name   = "shopflow-sfn-policy"            # Nome da policy
  policy = data.aws_iam_policy_document.sfn_policy.json  # JSON da policy
}

resource "aws_iam_role_policy_attachment" "sfn_role_attach" { # Anexar policy à role
  role       = aws_iam_role.sfn_role.name   # Nome da role
  policy_arn = aws_iam_policy.sfn_policy.arn# ARN da policy
}

# ---------------------------
# Step Function (State Machine)
# ---------------------------

resource "aws_sfn_state_machine" "shopflow_main" {  # State Machine principal
  name     = "shopflow-main"               # Nome da state machine
  role_arn = aws_iam_role.sfn_role.arn    # Role de execução

  definition = jsonencode({                # Definição em ASL (JSON)
    Comment = "ShopFlow simple state machine"   # Comentário
    StartAt = "FirstStep"                       # Estado inicial
    States = {                                  # Conjunto de estados
      "FirstStep" = {                           # Estado "FirstStep"
        Type   = "Pass"                         # Tipo Pass (no-op)
        Result = "Hello from Step Functions!"   # Resultado de teste
        End    = true                           # Estado terminal
      }
    }
  })
}

# ---------------------------
# IAM: Role e Policy para o EventBridge iniciar a Step Function
# ---------------------------

data "aws_iam_policy_document" "events_to_sfn_assume" { # Trust policy da role usada por EventBridge
  statement {
    actions = ["sts:AssumeRole"]            # EventBridge vai assumir esta role
    principals {
      type        = "Service"               # Principal serviço
      identifiers = ["events.amazonaws.com"]# Serviço EventBridge
    }
  }
}

data "aws_iam_policy_document" "events_to_sfn_policy" { # Permissão que a role (EventBridge) terá
  statement {
    actions   = ["states:StartExecution"]   # Pode iniciar execuções da SFN
    resources = [aws_sfn_state_machine.shopflow_main.arn] # Só nesta SFN
  }
}

resource "aws_iam_role" "events_to_sfn" {  # Role que o EventBridge assume
  name               = "shopflow-events-to-sfn"                 # Nome da role
  assume_role_policy = data.aws_iam_policy_document.events_to_sfn_assume.json # Trust policy
}

resource "aws_iam_policy" "events_to_sfn" {  # Policy para permitir StartExecution
  name   = "shopflow-events-to-sfn"         # Nome da policy
  policy = data.aws_iam_policy_document.events_to_sfn_policy.json # JSON da policy
}

resource "aws_iam_role_policy_attachment" "events_to_sfn" { # Anexa a policy à role
  role       = aws_iam_role.events_to_sfn.name   # Role alvo
  policy_arn = aws_iam_policy.events_to_sfn.arn  # ARN da policy
}

# ---------------------------
# EventBridge: regra diária que dispara a Step Function
# ---------------------------

resource "aws_cloudwatch_event_rule" "daily" {    # Regra de agendamento
  name                = "shopflow-daily-schedule" # Nome da regra
  schedule_expression = "cron(0 2 * * ? *)"       # Corre às 02:00 UTC diariamente
  description         = "Trigger ShopFlow Step Function daily" # Descrição
}

resource "aws_cloudwatch_event_target" "daily_target" { # Target da regra
  rule      = aws_cloudwatch_event_rule.daily.name      # Nome da regra
  target_id = "sfn-start"                               # ID do alvo
  arn       = aws_sfn_state_machine.shopflow_main.arn   # ARN da SFN a executar
  role_arn  = aws_iam_role.events_to_sfn.arn            # Role que o EventBridge assume

  input = jsonencode({                       # Payload de exemplo para a SFN
    etlFunctionArn = "REPLACE_WITH_ETL_LAMBDA_ARN"  # Placeholder para futura Lambda
    dqFunctionArn  = "REPLACE_WITH_DQ_LAMBDA_ARN"   # Placeholder para futura Lambda de DQ
    notifyTopicArn = aws_sns_topic.alerts.arn       # ARN do SNS para notificação
  })
}

# ---------------------------
# CloudWatch: Alarmes e Dashboard
# ---------------------------

resource "aws_cloudwatch_metric_alarm" "sfn_failures" { # Alarme para falhas da SFN
  alarm_name          = "shopflow-state-machine-failures"      # Nome do alarme
  alarm_description   = "Alerts when Step Functions executions fail" # Descrição
  namespace           = "AWS/States"                            # Namespace da métrica
  metric_name         = "ExecutionsFailed"                      # Métrica
  statistic           = "Sum"                                   # Estatística
  period              = 300                                     # Janela em segundos
  evaluation_periods  = 1                                       # Nº de períodos
  threshold           = 1                                       # Limite
  comparison_operator = "GreaterThanOrEqualToThreshold"         # Operador

  dimensions = {                                   # Dimensão: a SFN específica
    StateMachineArn = aws_sfn_state_machine.shopflow_main.arn
  }

  alarm_actions = [aws_sns_topic.alerts.arn]       # Para onde enviar alarmes
  ok_actions    = [aws_sns_topic.alerts.arn]       # Para onde enviar OK
}

resource "aws_cloudwatch_dashboard" "main" {       # Dashboard de monitorização
  dashboard_name = "ShopFlow-Pipeline"             # Nome do dashboard
  dashboard_body = file("${path.module}/../../monitoring/cloudwatch_dashboard.json") # JSON do layout
}

# ---------------------------
# GitHub OIDC + Role usada pelo GitHub Actions
# ---------------------------

resource "aws_iam_openid_connect_provider" "github" { # Provedor OIDC do GitHub
  url = "https://token.actions.githubusercontent.com" # URL do emissor OIDC (com https)

  client_id_list  = ["sts.amazonaws.com"]             # AUD esperado pelo STS
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"] # Thumbprint do certificado

  lifecycle { prevent_destroy = true }                # Evita destruição acidental
}

data "aws_caller_identity" "current" {}               # Dados da conta atual (útil para outputs/policies)

data "aws_iam_policy_document" "gh_trust" {          # Trust policy que permite ao GitHub assumir a role
  statement {                                        # Única declaração
    sid     = "AllowGitHubOIDC"                      # Identificador da regra
    actions = ["sts:AssumeRoleWithWebIdentity"]      # Ação para OIDC

    condition {                                      # Condição 1: emissor correto
      test     = "StringEquals"                      # Tipo de teste
      variable = "token.actions.githubusercontent.com:iss" # Variável - emissor
      values   = ["https://token.actions.githubusercontent.com"] # Valor esperado
    }

    condition {                                      # Condição 2: audiência correta
      test     = "StringEquals"                      # Tipo de teste
      variable = "token.actions.githubusercontent.com:aud" # Variável - audiência
      values   = ["sts.amazonaws.com"]               # Valor esperado
    }

    condition {                                      # Condição 3: repo/branch autorizados
      test     = "StringLike"                        # Tipo de teste (permite wildcard)
      variable = "token.actions.githubusercontent.com:sub" # Variável - subject
      values   = [
        "repo:ppires21/Data_Academy_Final_Exercise:ref:refs/heads/main" # <- teu repo/branch
        # Se quiseres permitir todas as branches, usa:
        # "repo:ppires21/Data_Academy_Final_Exercise:ref:refs/heads/*"
      ]
    }

    principals {                                     # Quem apresenta o token OIDC
      type        = "Federated"                      # Tipo federado (OIDC)
      identifiers = [aws_iam_openid_connect_provider.github.arn] # OIDC provider do GitHub
    }
  }
}

resource "aws_iam_role" "github_actions" {           # Role que o GitHub Actions assume
  name               = "github-actions-deploy-role"  # Nome da role
  description        = "Role assumida pelo GitHub Actions (OIDC) para aplicar Terraform." # Descrição
  assume_role_policy = data.aws_iam_policy_document.gh_trust.json # Trust policy (acima)
}

resource "aws_iam_role_policy_attachment" "github_poweruser" { # Concede permissões amplas (demo)
  role       = aws_iam_role.github_actions.name     # Role alvo
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess" # Policy gerida (PowerUser)
}

# Policy inline mínima para permitir iam:PassRole especificamente na role events_to_sfn
data "aws_iam_policy_document" "github_allow_passrole_doc" {  # Documento da policy inline
  statement {                                    # Declaração
    sid      = "AllowPassRoleToEventsToSfn"      # Identificador
    actions  = ["iam:PassRole"]                  # Ação PassRole
    resources = [aws_iam_role.events_to_sfn.arn] # Apenas a role do EventBridge
  }
}

resource "aws_iam_role_policy" "github_allow_passrole" { # Anexa policy inline à role do Actions
  name   = "github-allow-passrole-events-to-sfn"   # Nome da policy inline
  role   = aws_iam_role.github_actions.id          # Role alvo
  policy = data.aws_iam_policy_document.github_allow_passrole_doc.json # JSON da policy
}
