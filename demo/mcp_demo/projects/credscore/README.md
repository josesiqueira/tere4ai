# CredScore (expected high risk, Annex III point 5)

A creditworthiness scoring service for a small consumer loan fintech.

## Honest facts, written before touching TERE4AI

CredScore evaluates the creditworthiness of natural persons applying for
consumer loans. It produces a score and a recommendation that loan officers use
in their decisions and can override. Inputs are application data, income, and
payment history.

It is intended by its provider for exactly this purpose. It is not a fraud
detection tool. It profiles natural persons. The deployer is a private company
under EU jurisdiction providing an essential private service, consumer credit.

## Known gaps

This skeleton scores applications and stops there. There is no risk management
documentation, no record keeping of the kind Article 12 has in mind, no written
human oversight procedure, and no technical documentation. Which of those are
obligations, and under which articles, is the question for TERE4AI, not for our
intuition.
