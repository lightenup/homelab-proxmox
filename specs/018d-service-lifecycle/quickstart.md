# Quickstart: Service Lifecycle Tools

**Feature**: `018d-service-lifecycle`

## Overview

This feature introduces "Golden Paths" for managing services. Use the helper scripts to ensure consistency.

## Scripts

### 1. Add a Service
**Script**: `scripts/lifecycle/add_service.sh`
**Usage**: `./scripts/lifecycle/add_service.sh <service_name>`
**Description**: Creates a new host_vars file from the template and adds the host to the inventory.

### 2. Remove a Service
**Script**: `scripts/lifecycle/remove_service.sh`
**Usage**: `./scripts/lifecycle/remove_service.sh <service_name>`
**Description**: Removes the host from inventory and cleans up artifacts. **Does not destroy Terraform infra** (must be done manually).

### 3. Verify Service
**Script**: `scripts/lifecycle/verify_service.sh`
**Usage**: `./scripts/lifecycle/verify_service.sh <service_name>`
**Description**: Runs the healthcheck for a specific service immediately.

### 4. Check Drift
**Script**: `scripts/healthcheck/healthcheck.py --check-drift`
**Usage**: `python3 scripts/healthcheck/healthcheck.py --check-drift`
**Description**: Validates inventory schema and checks for "zombie" services.

## Manual Steps (Golden Path)

See [Golden Paths Runbook](../../docs/operations/golden-paths-service-lifecycle.md) for the full procedure.
