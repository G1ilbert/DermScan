variable "project_name" {
  description = "Railway project name"
  type        = string
  default     = "dermscan"
}

variable "github_repo" {
  description = "GitHub repository in 'owner/name' form for Railway to deploy"
  type        = string
}

variable "railway_token" {
  description = "Railway API token"
  type        = string
  sensitive   = true
}

variable "railway_team_id" {
  description = "Railway team ID (optional)"
  type        = string
  default     = null
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token with R2 edit permission"
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID"
  type        = string
}

variable "r2_bucket_name" {
  description = "Name of the R2 bucket for scan images and heatmaps"
  type        = string
  default     = "dermscan-images"
}
