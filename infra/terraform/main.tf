terraform {
  required_version = ">= 1.5.0"

  required_providers {
    railway = {
      source  = "terraform-community-providers/railway"
      version = "~> 0.5"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.30"
    }
  }
}

provider "railway" {
  token = var.railway_token
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

############################
# Cloudflare R2 (image bucket)
############################

resource "cloudflare_r2_bucket" "images" {
  account_id = var.cloudflare_account_id
  name       = var.r2_bucket_name
  location   = "ENAM"
}

############################
# Railway project + services
############################

resource "railway_project" "dermscan" {
  name        = var.project_name
  description = "AI skin lesion screening web app"
  team_id     = var.railway_team_id
}

resource "railway_environment" "production" {
  name       = "production"
  project_id = railway_project.dermscan.id
}

resource "railway_service" "postgres" {
  name           = "postgres"
  project_id     = railway_project.dermscan.id
  source_image   = "postgres:16-alpine"
  config_path    = null
}

resource "railway_service" "redis" {
  name         = "redis"
  project_id   = railway_project.dermscan.id
  source_image = "redis:7-alpine"
}

resource "railway_service" "api" {
  name       = "api"
  project_id = railway_project.dermscan.id
  source_repo = {
    repo   = var.github_repo
    branch = "main"
  }
  root_directory = "/backend"
}

resource "railway_service" "worker" {
  name       = "worker"
  project_id = railway_project.dermscan.id
  source_repo = {
    repo   = var.github_repo
    branch = "main"
  }
  root_directory = "/backend"
}

resource "railway_service" "frontend" {
  name       = "frontend"
  project_id = railway_project.dermscan.id
  source_repo = {
    repo   = var.github_repo
    branch = "main"
  }
  root_directory = "/frontend"
}
