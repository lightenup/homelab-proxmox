# Terraform: GitHub repo settings

This folder is a separate Terraform workspace for managing GitHub repository configuration that is *project setup* (not Proxmox/LXC infrastructure).

Currently it manages a single GitHub Environment (default: `prod`) that can be used by GitHub Actions for deployment gating.

## Why this exists

GitHub Actions “interactive approvals” are only enforced when the workflow targets a GitHub Environment (`environment: prod`) **and** that environment has protection rules (e.g. required reviewers). This workspace lets you manage those environment rules as IaC.

Note: If your GitHub plan/API does not support required reviewers for private repos, Terraform will not be able to enable it either.

## Prerequisites

- Terraform installed
- A GitHub token with repo admin permissions:
  - `export GITHUB_TOKEN=...`

## Usage

From repo root:

- `cd terraform/github`
- `cp github.tfvars.example github.tfvars`
- Edit `github.tfvars`
- `terraform init`
- `terraform plan -var-file=github.tfvars`
- `terraform apply -var-file=github.tfvars`

## Inputs

- `github_owner`: repo owner/org
- `repository`: repo name
- `environment_name`: defaults to `prod`
- `reviewer_users` / `reviewer_teams`: optional (only works if supported by your plan)

## What this does not manage

- GitHub Actions secrets in this repo (those often need a separate secrets-management approach)
- Proxmox / Terraform state on PVE (handled elsewhere in this repository)
