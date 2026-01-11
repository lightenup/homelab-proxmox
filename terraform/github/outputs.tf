output "environment" {
  value       = github_repository_environment.env.environment
  description = "The environment name managed by this workspace"
}
