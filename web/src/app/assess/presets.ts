/* One-click canonical scenario presets for the /assess demo flow (#53).
   The three scenarios mirror the canonical classification fixtures in
   tests/unit/test_classify.py, so the demo, the unit tests, and the paper
   screenshots tell the same story:
   - hospital triage: high_risk via Annex III point 5 (Article 6(2))
   - customer-service chatbot: transparency_only via Article 50
   - spam filter: minimal_or_none (no prohibition or Annex III flag applies)
   Every flag is set explicitly to true or false (never unknown) so the
   deterministic rule ladder reaches a settled outcome instead of
   requires_human_review. Presets only fill the form; classification still
   runs through the facade and the deterministic ladder. */

export type TriState = "true" | "false" | "unknown";

export type ScenarioPreset = {
  id: string;
  label: string;
  /* Expected deterministic outcome, shown as a hint on the button. */
  hint: string;
  description: string;
  domain: string;
  autonomy: string;
  flags: Record<string, TriState>;
};

/* All flags defined in schema/json_schemas/system_features.schema.json,
   matching ALL_FLAGS in tests/unit/test_classify.py. */
const ALL_FLAG_KEYS = [
  "biometric_identification",
  "biometric_categorisation",
  "real_time_remote_biometric_public",
  "emotion_recognition",
  "emotion_recognition_workplace_or_education",
  "social_scoring",
  "subliminal_or_manipulative",
  "exploits_vulnerabilities",
  "predictive_policing_profiling",
  "facial_image_scraping",
  "law_enforcement_use",
  "migration_asylum_border_use",
  "justice_democratic_use",
  "education_scoring_or_access",
  "employment_decisions",
  "essential_services_access",
  "critical_infrastructure_safety",
  "medical_or_safety_component",
  "interacts_with_natural_persons",
  "generates_synthetic_content",
  "profiling_of_natural_persons",
  "preparatory_or_narrow_procedural_task",
] as const;

function allFalse(overrides: Record<string, TriState> = {}): Record<string, TriState> {
  const flags: Record<string, TriState> = {};
  for (const key of ALL_FLAG_KEYS) flags[key] = "false";
  return { ...flags, ...overrides };
}

export const SCENARIO_PRESETS: ScenarioPreset[] = [
  {
    id: "hospital-triage",
    label: "Hospital triage",
    hint: "high_risk (Annex III point 5)",
    description: "Hospital emergency department triage support system.",
    domain: "healthcare",
    autonomy: "",
    flags: allFalse({
      essential_services_access: "true",
      medical_or_safety_component: "true",
    }),
  },
  {
    id: "customer-service-chatbot",
    label: "Customer service chatbot",
    hint: "transparency_only (Article 50)",
    description: "Customer service chatbot for an e-commerce shop.",
    domain: "consumer",
    autonomy: "",
    flags: allFalse({
      interacts_with_natural_persons: "true",
    }),
  },
  {
    id: "spam-filter",
    label: "Spam filter",
    hint: "minimal_or_none",
    description: "Email spam filter that flags unsolicited bulk messages in a mailbox.",
    domain: "consumer",
    autonomy: "",
    flags: allFalse(),
  },
];
