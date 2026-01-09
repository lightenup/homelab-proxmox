#!/usr/bin/env bash
set -euo pipefail

# Destructive confirmation tokens (Spec 025)
APPLY_LAB_DESTRUCTIVE_TOKEN="apply-lab-destructive"
DEPLOY_PROD_DESTRUCTIVE_TOKEN="deploy-prod-destructive"

promotion_token_for_environment() {
    local environment="${1:?environment required}"

    case "${environment}" in
        lab)
            echo "${APPLY_LAB_DESTRUCTIVE_TOKEN}"
            ;;
        prod)
            echo "${DEPLOY_PROD_DESTRUCTIVE_TOKEN}"
            ;;
        *)
            echo "" >&2
            return 1
            ;;
    esac
}
