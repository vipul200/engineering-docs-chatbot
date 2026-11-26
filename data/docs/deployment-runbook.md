# Deployment Runbook

## Overview
All backend services are deployed to Kubernetes (EKS, region eu-west-1) through the `deployer` GitHub Actions pipeline. Production deploys are allowed Monday to Thursday, 09:00-16:00 CET. Friday deploys require approval from the on-call engineering manager.

## Standard deploy
1. Merge the pull request to `main`; CI builds an image tagged with the git SHA.
2. The pipeline deploys automatically to `staging` and runs the smoke test suite.
3. Promote to production with `deployer promote <service> --env prod`.
4. Production uses a canary: 10% of traffic for 15 minutes, then 100% if the error rate stays below 1%.

## Rollback
Run `deployer rollback <service> --env prod`. This redeploys the previous image tag in under 2 minutes. Database migrations are NOT rolled back automatically; follow the migration guide.

## Feature flags
Risky changes must ship behind a LaunchDarkly flag. Flags older than 90 days are reported weekly and must be cleaned up.
