# RFP Answer Drafter

Drafts answers to RFP questions from **past approved proposals**. Every sentence carries a citation, and a confidence threshold sends questions the library can't answer to a subject-matter expert instead of letting the model improvise.

```text
$ python -m rfp_rag
1. What uptime do you commit to and what credits apply if you miss it?
   [drafted, confidence 0.50]
   Our production platform carries a 99.9% monthly uptime SLA, excluding scheduled maintenance announced 72 hours in advance [1]. If availability falls below 99.9%, the customer receives a 10% service credit; below 99.5%, a 25% credit [1].
     [1] northwind_wms.md: Describe your uptime SLA and service credits.
2. Please list your security certifications (SOC 2, ISO).
   [drafted, confidence 1.00]
   We hold a SOC 2 Type II report covering security, availability and confidentiality, renewed annually, and ISO 27001 certification for our hosting operations [1]. Reports are shared under NDA [1].
     [1] contoso_tms.md: Do you have SOC 2 Type II or ISO 27001 certification?
3. What are your RPO and RTO for disaster recovery?
   [drafted, confidence 1.00]
   Production runs active-passive across two cloud regions [1]. Our recovery point objective (RPO) is 15 minutes and recovery time objective (RTO) is 4 hours [1].
     [1] contoso_tms.md: Describe your disaster recovery capabilities.
4. How long does implementation take for one warehouse?
   [drafted, confidence 0.71]
   A standard single-site WMS implementation takes 12 to 16 weeks: 2 weeks discovery, 6 weeks configuration and integration, 3 weeks user acceptance testing, and 2 weeks hypercare after go-live [1]. Multi-site rollouts add about 4 weeks per additional site [1].
     [1] northwind_wms.md: What is your typical implementation timeline?
     [2] globex_yard.md: How is pricing structured?
5. Can we use our Okta tenant for SSO?
   [drafted, confidence 0.50]
   Yes [1]. We support SAML 2.0 and OpenID Connect single sign-on with Okta, Azure AD and Ping, plus SCIM 2.0 user provisioning on the Enterprise plan [1].
     [1] globex_yard.md: Do you support single sign-on?
6. Is customer data encrypted at rest?
   [drafted, confidence 1.00]
   Data is encrypted in transit with TLS 1.2 or higher and at rest with AES-256 [1]. Encryption keys are managed in a cloud KMS with annual rotation; customer-managed keys are available on the Enterprise plan [1].
     [1] northwind_wms.md: How is customer data encrypted?
     [2] globex_yard.md: Where is customer data hosted?
7. Do you hold FedRAMP authorization?
   [needs_sme, confidence 0.33]
   -> route to a subject-matter expert; closest past answer: Do you have SOC 2 Type II or ISO 27001 certification?
8. Describe your carbon emissions reporting for shipments.
   [needs_sme, confidence 0.00]
   -> route to a subject-matter expert; closest past answer: none

6/8 drafted from past proposals, 2 routed to SMEs
```

## Why it matters
A typical enterprise RFP has 150–300 questions, and roughly 70–80% of them were answered in some earlier proposal. Proposal managers spend days copying and adapting those answers. A generic chatbot is dangerous here, because RFP answers become contractual commitments: an invented "FedRAMP authorized" or "99.99% SLA" can cost the deal or create liability. This tool drafts only from approved language, cites the source proposal for every sentence so legal can verify quickly, and **refuses below a confidence threshold**. In the sample, 6 of 8 questions get a draft and the FedRAMP and carbon-reporting questions go to SMEs.

## Architecture
```
docs/proposals/*.md ─► one passage per "## Q:" section (question + approved answer)
                                    │
RFP question ─► tokenize (stopwords incl. RFP boilerplate, light stemming, buyer→our synonyms)
                                    │
                       BM25 top-k  +  coverage confidence (IDF-weighted share of
                                    │   question terms found in the top passage)
                     conf < 0.4 ? ──┴── yes → needs_sme (no LLM call)
                                    │ no
               numbered passages + strict prompt → LLMClient (Extractive | Claude)
                                    │
                    check_citations: out-of-range [n], uncited sentences
```
- **BM25 for ranking, coverage for the threshold.** BM25 scores aren't comparable across questions, so a fixed cutoff on them is arbitrary. Coverage (0–1) has a clear meaning: "the top passage contains the words that carry 50% of this question's information".
- **The unit of retrieval is a Q&A pair.** Past answers are reused per question, so a citation points to an approved answer a reviewer can open.
- **No answer, no LLM call.** Below threshold the model is never invoked, so it can't produce a confident-sounding promise.
- **Citations are checked after generation.** A model that cites `[4]` with two sources, or adds an uncited sentence, gets flagged for the reviewer.
- **Trade-off:** keyword retrieval misses paraphrases with no shared words. The synonym map (`warehouse → site`, `SSO → sign-on`) is a small, reviewable fix. Embeddings (project 026) are the next step.

## Run
```bash
pip install pytest
python -m pytest -q                         # 11 tests
python -m rfp_rag                           # data/rfp_questions.txt
python -m rfp_rag my_rfp_questions.txt
ANTHROPIC_API_KEY=... python -m rfp_rag     # Claude drafts from the same passages
```

## Next steps
- Track which drafted answers SMEs edit, and feed the approved edits back into the library.
- Add answer freshness (last-reviewed metadata) and down-rank stale answers.
- Export to the buyer's spreadsheet template with a sources column.
