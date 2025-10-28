# ---------------------------
# variables.tf
# Declaração de todas as variáveis usadas no projeto
# ---------------------------

variable "aws_region" {                            # Região AWS a usar
  type        = string
  description = "AWS region for all resources"
  default     = "eu-central-1"
}

variable "profile" {                               
  type        = string
  description = "AWS named profile from ~/.aws/credentials"
  default     = "data-academy"
}

variable "environment" {                           
  type        = string
  description = "Deployment environment (dev, demo, prod, ...)"
  default     = "demo"
}

variable "bucket_name" {                           
  type        = string
  description = "Base name for the S3 bucket (a suffix will be appended)"
  default     = "shopflow"
}

variable "suffix" {                                
  type        = string
  description = "Suffix to ensure global uniqueness of names"
  default     = "ctw04557"
}

variable "alert_email" {                           
  type        = string
  description = "Email to receive alerts via SNS (leave empty to disable)"
  default     = ""
}

# 👇 NOVO: controla se o EventBridge Target é criado neste apply
variable "create_events_target" {
  type        = bool
  description = "Create EventBridge target that needs iam:PassRole. Set false locally; true in CI/CD."
  default     = false
}
