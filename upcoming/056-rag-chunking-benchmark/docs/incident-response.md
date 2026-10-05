# Incident Response

This handbook covers how the platform team detects, declares and resolves production incidents. It applies to every service listed in the service catalog, including internal tools that other teams depend on.

## Severity levels

### SEV1
Full outage of a customer-facing service, data loss, or a security breach with confirmed exposure. The incident commander must be paged within 5 minutes of detection. Status page updates are posted every 30 minutes until resolution. The VP of Engineering is notified by phone, not chat.

### SEV2
Partial outage or a severe degradation affecting more than 10 percent of requests. Status page updates go out every 60 minutes. If it lasts longer than 4 hours it is automatically upgraded to the highest severity.

### SEV3
Minor degradation with a workaround available. Handled during business hours and tracked as a ticket with a 3 business day target.

## Roles

The incident commander owns decisions and communication, and does not debug. The operations lead runs the technical investigation and assigns work to responders. The scribe keeps a timestamped log in the incident channel so the review can be written from facts. For any SEV1 the communications lead drafts customer messages and gets them approved by the incident commander before posting.

## Escalation

If the on-call engineer does not acknowledge a page within 10 minutes, the page escalates to the secondary on-call. If the secondary does not acknowledge within a further 10 minutes, it escalates to the engineering manager for that service. Vendors are escalated through the support portal using the premium support contract number stored in the vault.

## Post-incident review

Every SEV1 and SEV2 requires a blameless post-incident review. The draft is due within 5 business days of resolution and is reviewed at the weekly reliability meeting. Each review lists contributing factors, what went well, and action items with an owner and a due date. Action items from SEV1 reviews must be completed within 30 days or escalated to the VP of Engineering.
