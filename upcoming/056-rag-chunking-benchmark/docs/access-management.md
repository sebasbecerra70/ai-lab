# Access Management

Access to production systems follows least privilege. Every grant has an owner, a reason and an expiry, and is recorded in the access request system.

## Requesting access

Engineers request access through the access request system, choosing a role rather than individual permissions. The request is approved by the system owner listed in the service catalog. Standard roles are granted for 90 days and must be renewed after that. Requests for admin roles also require approval from the security team.

## Break-glass access

Break-glass accounts exist for emergencies when the normal approval path is too slow, for example during a SEV1. Using a break-glass account triggers an immediate alert to the security team. The session is recorded and the credentials are rotated automatically within 1 hour after use. The engineer must file a justification ticket within 24 hours.

## Access reviews

System owners review all access to their systems every quarter. Grants that are not confirmed during the review are revoked automatically 7 days after the review closes. Results are exported for the SOC 2 auditors.

## Offboarding

When an employee leaves, HR triggers offboarding in the identity provider. All production access is revoked within 4 hours of the termination time. Personal API tokens are revoked at the same time, and shared secrets the person had access to are rotated within 5 business days.

## Service accounts

Service accounts are owned by a team, never an individual. Keys for service accounts are rotated every 90 days. Service accounts must not be used for interactive logins, and any interactive login attempt is blocked and alerted.
