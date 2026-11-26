# Database Guide

## Engines
The primary datastore is PostgreSQL 16 on Amazon RDS (Multi-AZ). Redis 7 (ElastiCache) is used for caching and rate limiting. Analytics data is in ClickHouse.

## Migrations
Migrations are written with Alembic and must be backward compatible (expand/contract pattern): add the new column, deploy code that writes both, backfill, then remove the old column in a later release. Migrations run as a pre-deploy Kubernetes Job. Never drop a column in the same release that stops using it.

## Access
Engineers do not have write access to production databases. Read-only access to a replica is requested through the `db-access` Slack workflow and expires after 8 hours. All queries are audited.

## Backups
RDS takes automated snapshots daily with 35 days of retention, plus point-in-time recovery. Restore drills are run quarterly by the platform team.
