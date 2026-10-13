# Northwind Distribution - WMS proposal

## Q: Describe your uptime SLA and service credits.
Our production platform carries a 99.9% monthly uptime SLA, excluding scheduled maintenance announced 72 hours in advance. If availability falls below 99.9%, the customer receives a 10% service credit; below 99.5%, a 25% credit. Uptime is published on a public status page.

## Q: What is your typical implementation timeline?
A standard single-site WMS implementation takes 12 to 16 weeks: 2 weeks discovery, 6 weeks configuration and integration, 3 weeks user acceptance testing, and 2 weeks hypercare after go-live. Multi-site rollouts add about 4 weeks per additional site.

## Q: Which ERP systems do you integrate with?
We provide certified connectors for SAP S/4HANA, Oracle NetSuite and Microsoft Dynamics 365. Other ERPs integrate through our REST API and EDI (X12 940/945/856) gateway.

## Q: How is customer data encrypted?
Data is encrypted in transit with TLS 1.2 or higher and at rest with AES-256. Encryption keys are managed in a cloud KMS with annual rotation; customer-managed keys are available on the Enterprise plan.
