# ===================================================================
# main.tf — Provider + S3 + SNS + IAM + EventBridge + SFN + OIDC
# ===================================================================

terraform {                                   # Bloco raiz de configuração do Terraform
  required_version = ">= 1.5.0"               # Versão mínima do Terraform
  required_providers {                        # Provedores necessários
    aws = {                                   # Provider AWS
      source  = "hashicorp/aws"               # Origem do provider
      version = ">= 5.0"                      # Versão mínima
    }
  }
}

provider "aws" {                              # Provider AWS (autenticação/region)
  region  = var.aws_region                    # Região (ex.: eu-central-1) — vem de variables.tf
  profile = var.profile                       # Profile local (só usado se correres localmente)
}

# ---------------------------
# S3: Bucket de dados
# ---------------------------

locals {                                      # Variáveis locais
  bucket_final_name = "${var.bucket_name}-${var.suffix}" # Nome único do bucket
  bucket_uri        = "s3://${local.bucket_final_name}"  # URI do bucket
}

resource "aws_s3_bucket" "data_bucket" {      # Recurso Bucket S3
  bucket = local.bucket_final_name            # Nome do bucket
}

resource "aws_s3_bucket_versioning" "data_bucket_versioning" {  # Versioning
  bucket = aws_s3_bucket.data_bucket.id       # ID do bucket
  versioning_configuration {
    status = "Enabled"                         # Ativa versioning
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_bucket_encryption" { # SSE
  bucket = aws_s3_bucket.data_bucket.id       # ID do bucket
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"                # Criptografia SSE-S3
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data_bucket_block_public" { # Bloqueio público
  bucket                  = aws_s3_bucket.data_bucket.id  # ID do bucket
  block_public_acls       = true               # Bloqueia ACLs públicas
  block_public_policy     = true               # Bloqueia policies públicas
  ignore_public_acls      = true               # Ignora ACLs públicas
  restrict_public_buckets = true               # Restringe buckets públicos
}

resource "aws_s3_bucket_lifecycle_configuration" "data_bucket_lifecycle" { # Lifecycle
  bucket = aws_s3_bucket.data_bucket.id       # ID do bucket
  rule {
    id     = "expire-old-logs"                # ID da regra
    status = "Enabled"                        # Ativa a regra
    filter {}                                 # Sem filtro (aplica a tudo)
    expiration { days = 90 }                  # Expira objetos com 90 dias
  }
}

# ---------------------------
# SNS: Alertas
# ---------------------------

resource "aws_sns_topic" "alerts" {           # Tópico SNS para alertas
  name = "shopflow-alerts"                    # Nome do tópico
}

resource "aws_sns_topic_subscription" "alerts_email" { # Subscrição por email (opcional)
  count     = length(var.alert_email) > 0 ? 1 : 0      # Cria só se foi definido email
  topic_arn = aws_sns_topic.alerts.arn        # ARN do tópico
  protocol  = "email"                          # Protocolo email
  endpoint  = var.alert_email                  # Email destino
}

# ---------------------------
# Step Functions: IAM Role + Policy
# ---------------------------

data "aws_iam_policy_document" "sfn_assume_role" { # Trust policy da role de execução da SFN
  statement {
    actions = ["sts:AssumeRole"]              # Permite STS:AssumeRole
    principals {
      type        = "Service"                 # Tipo principal = Service
      identifiers = ["states.amazonaws.com"]  # Serviço Step Functions
    }
  }
}

resource "aws_iam_role" "sfn_role" {          # Role de execução da Step Function
  name               = "shopflow-sfn-role"    # Nome da role
  assume_role_policy = data.aws_iam_policy_document.sfn_assume_role.json # Trust policy
}

data "aws_iam_policy_document" "sfn_policy" { # Policy com permissões da SFN
  statement {
    actions   = ["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents"] # Logs
    resources = ["*"]                          # (podes restringir a grupos específicos)
  }
  statement {
    actions   = ["lambda:InvokeFunction"]      # Permite invocar Lambdas (placeholder)
    resources = ["*"]                          # (restringe aos ARNs quando existirem)
  }
}

resource "aws_iam_policy" "sfn_policy" {      # Política gerida para a SFN
  name   = "shopflow-sfn-policy"               # Nome da policy
  policy = data.aws_iam_policy_document.sfn_policy.json # Documento JSON
}

resource "aws_iam_role_policy_attachment" "sfn_role_attach" { # Anexa policy à role
  role       = aws_iam_role.sfn_role.name      # Nome da role SFN
  policy_arn = aws_iam_policy.sfn_policy.arn   # ARN da policy
}

# ---------------------------
# Step Function (State Machine)
# ---------------------------

resource "aws_sfn_state_machine" "shopflow_main" { # State Machine SFN
  name     = "shopflow-main"               # Nome da SFN
  role_arn = aws_iam_role.sfn_role.arn     # Role de execução
  definition = jsonencode({                 # Definição em ASL (JSON)
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

data "aws_iam_policy_document" "events_to_sfn_assume" { # Trust policy da role usada pelo EventBridge
  statement {
    actions = ["sts:AssumeRole"]             # EventBridge assume esta role
    principals {
      type        = "Service"                # Tipo principal = Service
      identifiers = ["events.amazonaws.com"] # Serviço EventBridge
    }
  }
}

data "aws_iam_policy_document" "events_to_sfn_policy" {  # Permissões: EventBridge -> StartExecution
  statement {
    actions   = ["states:StartExecution"]    # Pode arrancar execuções da SFN
    resources = [aws_sfn_state_machine.shopflow_main.arn] # Só esta SFN
  }
}

resource "aws_iam_role" "events_to_sfn" {    # Role que o EventBridge usa para invocar a SFN
  name               = "shopflow-events-to-sfn"           # Nome da role
  assume_role_policy = data.aws_iam_policy_document.events_to_sfn_assume.json # Trust policy
}

resource "aws_iam_policy" "events_to_sfn" {  # Policy anexada à role do EventBridge
  name   = "shopflow-events-to-sfn"          # Nome da policy
  policy = data.aws_iam_policy_document.events_to_sfn_policy.json # Documento JSON
}

resource "aws_iam_role_policy_attachment" "events_to_sfn" { # Anexa a policy à role
  role       = aws_iam_role.events_to_sfn.name   # Nome da role
  policy_arn = aws_iam_policy.events_to_sfn.arn  # ARN da policy
}

# ---------------------------
# EventBridge: regra diária que dispara a Step Function
# ---------------------------

resource "aws_cloudwatch_event_rule" "daily" { # Regra EventBridge com cron diário
  name                = "shopflow-daily-schedule"  # Nome da regra
  schedule_expression = "cron(0 2 * * ? *)"       # 02:00 UTC todos os dias
  description         = "Trigger ShopFlow Step Function daily" # Descrição
}

resource "aws_cloudwatch_event_target" "daily_target" { # Alvo da regra: a SFN
  rule      = aws_cloudwatch_event_rule.daily.name      # Nome da regra
  target_id = "sfn-start"                               # ID do alvo
  arn       = aws_sfn_state_machine.shopflow_main.arn   # ARN da SFN
  role_arn  = aws_iam_role.events_to_sfn.arn            # Role que o EventBridge irá assumir

  input = jsonencode({                                   # Exemplo de input (placeholders)
    etlFunctionArn = "REPLACE_WITH_ETL_LAMBDA_ARN"
    dqFunctionArn  = "REPLACE_WITH_DQ_LAMBDA_ARN"
    notifyTopicArn = aws_sns_topic.alerts.arn
  })
}

# ---------------------------
# CloudWatch: Alarmes e Dashboard
# ---------------------------

resource "aws_cloudwatch_metric_alarm" "sfn_failures" { # Alarme para falhas da SFN
  alarm_name          = "shopflow-state-machine-failures"     # Nome do alarme
  alarm_description   = "Alerts when Step Functions executions fail" # Descrição
  namespace           = "AWS/States"                           # Namespace métrica
  metric_name         = "ExecutionsFailed"                     # Métrica
  statistic           = "Sum"                                  # Estatística
  period              = 300                                    # Janela 5 min
  evaluation_periods  = 1                                      # Nº períodos
  threshold           = 1                                      # Threshold
  comparison_operator = "GreaterThanOrEqualToThreshold"        # Condição

  dimensions = {                                              # Dimensão: SFN alvo
    StateMachineArn = aws_sfn_state_machine.shopflow_main.arn
  }

  alarm_actions = [aws_sns_topic.alerts.arn]                  # Notifica SNS quando alarma
  ok_actions    = [aws_sns_topic.alerts.arn]                  # Notifica SNS quando OK
}

resource "aws_cloudwatch_dashboard" "main" { # Dashboard (ficheiro JSON externo)
  dashboard_name = "ShopFlow-Pipeline"       # Nome do dashboard
  dashboard_body = file("${path.module}/../../monitoring/cloudwatch_dashboard.json") # Caminho
}

# ---------------------------
# GitHub OIDC + Role usada pelo GitHub Actions (corrigido)
# ---------------------------

resource "aws_iam_openid_connect_provider" "github" {   # Provedor OIDC do GitHub
  url = "https://token.actions.githubusercontent.com"   # URL do emissor OIDC (tem de ter https://)

  client_id_list  = ["sts.amazonaws.com"]               # Audience aceitável
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"] # Thumbprint do cert

  lifecycle { prevent_destroy = true }                  # Evita destruição acidental
}

data "aws_caller_identity" "current" {}                 # Dados da conta (opcional, útil noutros outputs)

data "aws_iam_policy_document" "gh_trust" {             # Trust policy para a role assumida pelo Actions
  statement {
    sid     = "AllowGitHubOIDC"                         # Identificador do statement
    actions = ["sts:AssumeRoleWithWebIdentity"]         # Ação necessária para OIDC

    principals {
      type        = "Federated"                         # Tipo principal federado
      identifiers = [aws_iam_openid_connect_provider.github.arn] # OIDC provider acima
    }

    # Emissor e audience do token OIDC devem corresponder
    condition {
      test     = "StringEquals"                         # Comparação exata
      variable = "token.actions.githubusercontent.com:iss"
      values   = ["https://token.actions.githubusercontent.com"]
    }
    condition {
      test     = "StringEquals"                         # Comparação exata
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # SUBJECT do token deve corresponder ao TEU repositório/branch
    condition {
      test     = "StringLike"                           # Aceita padrões com wildcard
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:ppires21/Data_Academy_Final_Exercise:ref:refs/heads/main",  # branch main
        "repo:ppires21/Data_Academy_Final_Exercise:ref:refs/heads/*",     # (opcional) outras branches
        "repo:ppires21/Data_Academy_Final_Exercise:ref:refs/pull/*/merge" # (opcional) PRs
      ]
    }
  }
}

resource "aws_iam_role" "github_actions" {              # Role que o GitHub Actions vai assumir
  name               = "github-actions-deploy-role"     # Nome da role
  description        = "Role assumida pelo GitHub Actions (OIDC) para aplicar Terraform."
  assume_role_policy = data.aws_iam_policy_document.gh_trust.json # Trust policy acima
}

resource "aws_iam_role_policy_attachment" "github_poweruser" { # Dá permissões de trabalho
  role       = aws_iam_role.github_actions.name         # Nome da role
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess" # Política gerida (podes restringir depois)
}

# Permite ao Actions fazer iam:PassRole SÓ para a role que o EventBridge usa
data "aws_iam_policy_document" "github_allow_passrole_doc" {
  statement {
    sid       = "AllowPassRoleToEventsToSfn"            # ID do statement
    actions   = ["iam:PassRole"]                        # Ação PassRole
    resources = [aws_iam_role.events_to_sfn.arn]        # Limita à role do EventBridge
  }
}

resource "aws_iam_role_policy" "github_allow_passrole" { # Policy inline anexada à role do Actions
  name   = "github-allow-passrole-events-to-sfn"         # Nome da policy
  role   = aws_iam_role.github_actions.id                # Role alvo
  policy = data.aws_iam_policy_document.github_allow_passrole_doc.json # Documento JSON
}
