#!/usr/bin/env bash
set -euo pipefail

# Basic Terraform hygiene checks for this repo.
# Intended to be fast and safe to run in CI (no backend access).

terraform fmt -check -recursive terraform/

terraform -chdir=terraform init -backend=false -input=false
terraform -chdir=terraform validate
