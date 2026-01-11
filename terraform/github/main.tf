locals {
  # Provider schema for reviewers has changed across major versions.
  # To keep this workspace robust, reviewers are implemented using IDs where possible.
  # If your plan/API doesn't support required reviewers, apply will fail with an API error.
}

data "github_user" "reviewers" {
  for_each = toset(var.reviewer_users)
  username = each.value
}

data "github_team" "reviewers" {
  for_each = toset(var.reviewer_teams)
  slug     = each.value
}

resource "github_repository_environment" "env" {
  repository  = var.repository
  environment = var.environment_name

  deployment_branch_policy {
    protected_branches     = var.protected_branches_only
    custom_branch_policies = var.custom_branch_policies
  }

  dynamic "reviewers" {
    for_each = (length(var.reviewer_users) + length(var.reviewer_teams)) > 0 ? [1] : []
    content {
      users = [for u in data.github_user.reviewers : u.id]
      teams = [for t in data.github_team.reviewers : t.id]
    }
  }
}
