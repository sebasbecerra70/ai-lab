# Globex Manufacturing - yard management proposal

## Q: Where is customer data hosted?
Customer data is hosted in AWS regions in the United States (us-east-1, us-west-2) or the European Union (eu-central-1), chosen by the customer at onboarding. Data does not leave the selected region except for encrypted backups within the same jurisdiction.

## Q: How is pricing structured?
Pricing is a per-site annual subscription based on dock doors and users, plus a one-time implementation fee. Multi-year agreements receive tiered discounts. Integrations through the standard REST API are included.

## Q: Do you support single sign-on?
Yes. We support SAML 2.0 and OpenID Connect single sign-on with Okta, Azure AD and Ping, plus SCIM 2.0 user provisioning on the Enterprise plan.
