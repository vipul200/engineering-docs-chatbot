# On-call Guide

## Rotation
On-call is a weekly rotation that starts Monday 10:00 CET. Each team has a primary and a secondary. The schedule lives in PagerDuty under the "Platform" escalation policy.

## Severity levels
- SEV1: customer-facing outage or data loss. Acknowledge within 5 minutes, open an incident channel `#inc-<date>-<name>`, page the incident commander.
- SEV2: major feature degraded for many customers. Acknowledge within 15 minutes.
- SEV3: minor issue or single-customer impact. Handle in business hours.

## After an incident
A blameless postmortem is required for every SEV1 and SEV2 within 5 business days, using the template in Confluence space ENG/Postmortems.

## Compensation
On-call engineers receive a fixed weekly allowance plus time off in lieu for any page handled between 22:00 and 07:00.
