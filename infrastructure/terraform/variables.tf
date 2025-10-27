# ---------------------------
# variables.tf
# Declaração de todas as variáveis usadas no projeto
# ---------------------------

variable "aws_region" {                            # Região AWS a usar
  type        = string                             # Tipo string
  description = "AWS region for all resources"     # Descrição
  default     = "eu-central-1"                     # Valor por defeito (ex.: Frankfurt)
}

variable "profile" {                               # Nome do profile AWS (credentials)
  type        = string                             # Tipo string
  description = "AWS named profile from ~/.aws/credentials"
  default     = "data-academy"                          # Podes ajustar para o teu profile
}

variable "environment" {                           # Ambiente (ex.: dev, demo, prod)
  type        = string                             # Tipo string
  description = "Deployment environment (dev, demo, prod, ...)"
  default     = "demo"                             # Valor por defeito
}

variable "bucket_name" {                           # Prefixo base do bucket
  type        = string                             # Tipo string
  description = "Base name for the S3 bucket (a suffix will be appended)"
  default     = "shopflow"             # Nome base do bucket
}

variable "suffix" {                                # Sufixo para garantir unicidade
  type        = string                             # Tipo string
  description = "Suffix to ensure global uniqueness of names"
  default     = "ctw04557"                          
}

variable "alert_email" {                           # Email para subscrição SNS
  type        = string                             # Tipo string
  description = "Email to receive alerts via SNS (leave empty to disable)"
  default     = ""                                 # Vazio desativa subscrição
}

