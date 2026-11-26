# Local Development Setup

## Prerequisites
Install Docker Desktop, Python 3.12, Node.js 20 and the `devbox` CLI. Request access to the GitHub organisation and to AWS SSO (profile `dev`) through the IT portal.

## Getting started
1. Clone the monorepo: `git clone git@github.com:example/platform.git`.
2. Run `devbox up` to start PostgreSQL, Redis and LocalStack in Docker.
3. Run `make seed` to load fixture data.
4. Start a service with `make run SERVICE=<name>`.

## Secrets
Never commit secrets. Local secrets are pulled from AWS Secrets Manager with `devbox secrets pull`; the resulting `.env.local` file is git-ignored.

## Troubleshooting
If `devbox up` fails with "port 5432 already in use", stop any local PostgreSQL instance (`brew services stop postgresql`) and retry.
