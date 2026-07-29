/* Shared calibrated-vocabulary copy (DEC-08, docs/architecture.md Section 8).
   The seven statuses are a closed set served live by the facade's
   .well-known; these subtitles are fixed, non-authoritative copy that
   explains each term for a human reader. Never invent a term outside the
   served vocabulary; an unknown status falls back to a generic pointer at
   the callsite, never to a guessed subtitle here. */
export const VOCAB_SUBTITLES: Record<string, string> = {
  not_applicable: "the obligation does not bind this system",
  potentially_applicable: "may bind, facts incomplete",
  applicable_missing_evidence: "binds, no evidence submitted yet",
  partially_satisfied: "evidence covers part of the obligation",
  satisfied_with_evidence: "the judge accepted the submitted evidence",
  rejected_as_unsupported: "the judge rejected the submitted evidence",
  requires_human_review: "the system abstains and asks a human",
};
