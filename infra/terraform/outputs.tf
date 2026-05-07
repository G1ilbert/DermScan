output "railway_project_id" {
  description = "Railway project ID"
  value       = railway_project.dermscan.id
}

output "railway_api_service_id" {
  value = railway_service.api.id
}

output "railway_worker_service_id" {
  value = railway_service.worker.id
}

output "railway_frontend_service_id" {
  value = railway_service.frontend.id
}

output "r2_bucket_name" {
  description = "Cloudflare R2 bucket for scan images"
  value       = cloudflare_r2_bucket.images.name
}
