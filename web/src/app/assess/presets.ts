/* One-click canonical scenario presets for the /assess demo flow (#53, demo
   revamp task C2). The five scenarios mirror the four worked examples under
   examples/ (SpamGuard, ShopBot, CredScore, MoodWatch, plus a MoodWatch
   safety-exception variant), so the demo, the example READMEs, and the
   archived fixtures tell the same story:
   - spamguard: minimal_or_none (no prohibition or Annex III flag applies);
     flags reused verbatim from the recorded request fixture
     tests/fixtures/demo_sessions/spamguard-classify.jsonl, which produced
     the archived confident-minimal envelope.
   - shopbot: transparency_only via Article 50 (interacts with natural
     persons, generates text)
   - credscore: high_risk via Annex III point 5(b) (creditworthiness
     evaluation), FRIA applies
   - moodwatch: prohibited via Article 5(1)(f) (workplace emotion
     recognition, no medical/safety exception)
   - moodwatch-safety: same facts as moodwatch, but the medical/safety
     exception fact is deliberately left unknown (a driver-fatigue-safety
     claim TERE4AI cannot verify from the description alone), which routes
     to requires_human_review instead of a confident prohibition. This is
     the calibrated-abstention beat: TERE4AI does not guess an exculpating
     fact into existence just because a description asserts a safety
     purpose.
   Flags are set explicitly to true or false wherever the example's README
   plainly settles the fact; where it does not, the flag is left "unknown"
   so the deterministic rule ladder can show its own missing-facts
   handling instead of a guessed value. Presets only fill the form;
   classification still runs through the facade and the deterministic
   ladder. */

export type TriState = "true" | "false" | "unknown";

export type ScenarioPreset = {
  id: string;
  label: string;
  /* Expected deterministic outcome, shown as a hint on the button. The
     ladder still runs live; this is a stated expectation, not a guarantee. */
  hint: string;
  description: string;
  domain: string;
  autonomy: string;
  flags: Record<string, TriState>;
};

/* All 34 flags defined in schema/json_schemas/system_features.schema.json,
   matching schema_flag_names() in src/tere4ai/elicit_features/elicitor.py
   (alphabetically sorted; the drift gate in
   tests/unit/test_web_copy_honesty.py::test_presets_cover_every_schema_flag
   fails if this list falls behind the schema). */
const ALL_FLAG_KEYS = [
  "annex_i_covered_product",
  "biometric_categorisation",
  "biometric_categorisation_lawful_or_law_enforcement",
  "biometric_identification",
  "causes_significant_harm",
  "creditworthiness_evaluation",
  "critical_infrastructure_safety",
  "detects_patterns_without_replacing_human_assessment",
  "education_scoring_or_access",
  "emotion_recognition",
  "emotion_recognition_medical_or_safety",
  "emotion_recognition_workplace_or_education",
  "employment_decisions",
  "essential_services_access",
  "exploits_vulnerabilities",
  "facial_image_scraping",
  "generates_synthetic_content",
  "improves_previous_human_activity",
  "interacts_with_natural_persons",
  "justice_democratic_use",
  "law_enforcement_use",
  "life_health_insurance_risk_pricing",
  "medical_or_safety_component",
  "migration_asylum_border_use",
  "predictive_policing_profiling",
  "preparatory_or_narrow_procedural_task",
  "profiling_of_natural_persons",
  "real_time_remote_biometric_public",
  "rtrb_strictly_necessary_authorised",
  "social_score_detrimental_treatment",
  "social_scoring",
  "subliminal_or_manipulative",
  "supports_human_assessment_on_verifiable_facts",
  "third_party_conformity_assessment_required",
] as const;

function allFalse(overrides: Record<string, TriState> = {}): Record<string, TriState> {
  const flags: Record<string, TriState> = {};
  for (const key of ALL_FLAG_KEYS) flags[key] = "false";
  return { ...flags, ...overrides };
}

export const SCENARIO_PRESETS: ScenarioPreset[] = [
  {
    id: "spamguard",
    label: "SpamGuard (email filter)",
    hint: "minimal_or_none",
    description:
      "SpamGuard is a machine learning email filter deployed by a 20 person company for its own shared inboxes. It classifies incoming mail as ham, spam, or phishing using message text and metadata, moves likely spam to a retrievable quarantine folder, and never blocks, deletes, or answers mail on its own. It does not profile or score people and is not used in employment, credit, education, law enforcement, migration, or any other Annex III context.",
    domain: "email security",
    autonomy: "partial",
    /* Verbatim from tests/fixtures/demo_sessions/spamguard-classify.jsonl
       (the recorded request that produced the archived confident-minimal
       envelope): every flag false except the two narrow-task Article 6(3)
       flags, which are true but never reached since no Annex III category
       matches in the first place. */
    flags: allFalse({
      preparatory_or_narrow_procedural_task: "true",
      detects_patterns_without_replacing_human_assessment: "true",
    }),
  },
  {
    id: "shopbot",
    label: "ShopBot (customer chat)",
    hint: "transparency_only (Article 50)",
    description:
      "ShopBot is an LLM backed chat assistant embedded in a webshop. It answers questions about order status, return policy, and product details, and escalates to a human agent on request or when unsure. It interacts directly with natural persons and generates text, but does not make decisions about people, does not profile, score, or categorize individuals, and performs no biometric processing or emotion inference.",
    domain: "consumer",
    autonomy: "",
    flags: allFalse({
      interacts_with_natural_persons: "true",
      generates_synthetic_content: "true",
    }),
  },
  {
    id: "credscore",
    label: "CredScore (credit scoring)",
    hint: "high_risk (Annex III point 5(b)), FRIA applies",
    description:
      "CredScore is a machine learning service that evaluates the creditworthiness of natural persons applying for consumer loans, producing a score and a recommendation that loan officers use in their decisions and can override. It is not a fraud detection tool, and is deployed by a private company under EU jurisdiction as a private entity providing an essential private service (consumer credit).",
    domain: "banking",
    autonomy: "advisory",
    /* interacts_with_natural_persons and the three Article 6(3) narrow-task
       flags are left unknown: the README does not settle them, and none of
       the four affects this outcome (Annex III point 5(b) already matches
       via creditworthiness_evaluation, and profiling_of_natural_persons
       being true would cancel any accidental derogation candidacy anyway).
       The two deployer booleans (body_governed_by_public_law,
       private_entity_providing_public_services) are not sent at all: the
       form does not model them (see the task report). That does not change
       this preset's FRIA outcome, because creditworthiness_evaluation is
       itself a point 5(b) trigger that applies "for any deployer" per
       src/tere4ai/mcp_server/fria.py, evaluated before the deployer-category
       branch. */
    flags: allFalse({
      creditworthiness_evaluation: "true",
      essential_services_access: "true",
      profiling_of_natural_persons: "true",
      interacts_with_natural_persons: "unknown",
      preparatory_or_narrow_procedural_task: "unknown",
      improves_previous_human_activity: "unknown",
      detects_patterns_without_replacing_human_assessment: "unknown",
    }),
  },
  {
    id: "moodwatch",
    label: "MoodWatch (workplace emotion)",
    hint: "prohibited (Article 5(1)(f))",
    description:
      "MoodWatch continuously analyzes employees' facial expressions from webcam feeds and their typing patterns to infer emotions such as stress, frustration, and engagement in the workplace, aggregating results into dashboards visible to management. Participation is a condition of employment. It is not a medical device and is not deployed for safety reasons; its stated purpose is productivity and wellbeing monitoring.",
    domain: "employment",
    autonomy: "",
    flags: allFalse({
      emotion_recognition: "true",
      emotion_recognition_workplace_or_education: "true",
      /* emotion_recognition_medical_or_safety stays false (default): the
         README explicitly rules the exception out ("is not deployed for
         safety reasons"), so Article 5(1)(f) fires with no exception to
         resolve. */
    }),
  },
  {
    id: "moodwatch-safety",
    label: "MoodWatch (driver fatigue safety variant)",
    hint: "requires_human_review (calibrated abstention: the exception fact is deliberately left unsettled)",
    description:
      "MoodWatch, driver fatigue safety variant: the same webcam based workplace emotion recognition system, but the deploying company now states the purpose is monitoring professional drivers for fatigue and reduced alertness during work hours, for driver and road safety. Participation is a condition of employment. TERE4AI cannot independently verify a stated safety purpose from the description alone, so whether the Article 5(1)(f) medical or safety exception applies is left unresolved rather than assumed.",
    domain: "employment",
    autonomy: "",
    flags: allFalse({
      emotion_recognition: "true",
      emotion_recognition_workplace_or_education: "true",
      /* The whole point of this variant: the exculpating fact for Article
         5(1)(f) is left unknown, not assumed true from the claimed safety
         purpose and not assumed false either. The deterministic ladder
         then declines to confidently prohibit or confidently clear the
         system, and reports requires_human_review instead. */
      emotion_recognition_medical_or_safety: "unknown",
    }),
  },
];
