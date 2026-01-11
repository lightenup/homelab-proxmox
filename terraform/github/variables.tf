variable "github_owner" {
  type        = string
  description = "GitHub org/user owner of the repository"
}

variable "repository" {
  type        = string
  description = "Repository name (without owner), e.g. homelab-proxmox"
}

variable "environment_name" {
  type        = string
  description = "Environment name to manage"
  default     = "prod"
}

variable "protected_branches_only" {
  type        = bool
  description = "If true, only protected branches can deploy to this environment"
  default     = true
}

variable "custom_branch_policies" {
  type        = bool
  description = "If true, allow custom branch policies (naming patterns)"
  default     = false
}

variable "reviewer_users" {
  type        = list(string)
  description = "Optional list of GitHub usernames to require as reviewers for this environment (if your GitHub plan supports it)"
  default     = []
}

variable "reviewer_teams" {
  type        = list(string)
  description = "Optional list of GitHub team slugs to require as reviewers for this environment (if your GitHub plan supports it)"
  default     = []
}
