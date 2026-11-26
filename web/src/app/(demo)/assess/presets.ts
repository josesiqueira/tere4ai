/* One-click canonical scenario presets for the /assess demo flow (#53, demo
   revamp task C2). The five scenarios mirror the four worked examples under
   examples/ (SpamGuard, ShopBot, CredScore, MoodWatch, plus a MoodWatch
   safety-exception variant), so the demo, the example READMEs, and the
   archived fixtures tell the same story:
   - spamguard: minimal_risk (no prohibition or Annex III flag applies);
     the facts set true are those of the recorded request fixture
     tests/fixtures/demo_sessions/spamguard-classify.jsonl, which produced
     the archived confident-minimal envelope.
   - shopbot: limited_risk via Article 50 (interacts with natural
     persons, generates text)
   - credscore: high_risk via Annex III point 5(b) (creditworthiness
     evaluation), FRIA applies
   - moodwatch: unacceptable_risk via Article 5(1)(f) (workplace emotion
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

/* All 56 flags defined in schema/json_schemas/system_features.schema.json,
   matching schema_flag_names() in src/tere4ai/elicit_features/elicitor.py
   (sorted; the drift gate in
   tests/unit/test_web_copy_honesty.py::test_presets_name_every_schema_flag
   fails if this list falls behind the schema). */
const ALL_FLAG_KEYS = [
  "annex_i_covered_product",
  "annex_i_section_b_legislation",
  "annex_iii_3a_admission",
  "annex_iii_3b_learning_outcomes",
  "annex_iii_3c_education_level",
  "annex_iii_3d_test_monitoring",
  "annex_iii_4a_recruitment",
  "annex_iii_4b_work_relationships",
  "annex_iii_5a_public_benefits",
  "annex_iii_5d_emergency_calls",
  "annex_iii_6a_victim_risk",
  "annex_iii_6b_polygraphs",
  "annex_iii_6c_evidence_reliability",
  "annex_iii_6d_offending_risk",
  "annex_iii_6e_profiling",
  "annex_iii_7a_polygraphs",
  "annex_iii_7b_entry_risk",
  "annex_iii_7c_applications",
  "annex_iii_7d_identification",
  "annex_iii_8a_judicial",
  "annex_iii_8b_elections",
  "biometric_categorisation",
  "biometric_categorisation_lawful_or_law_enforcement",
  "biometric_categorisation_sensitive_or_protected_attributes",
  "biometric_categorisation_system",
  "biometric_identification",
  "causes_significant_harm",
  "creditworthiness_evaluation",
  "critical_infrastructure_safety",
  "detects_patterns_without_replacing_human_assessment",
  "emotion_recognition",
  "emotion_recognition_medical_or_safety",
  "emotion_recognition_workplace_or_education",
  "exploits_vulnerabilities",
  "facial_image_scraping",
  "generates_csam",
  "generates_deep_fake",
  "generates_nonconsensual_intimate_material",
  "generates_public_interest_text",
  "generates_synthetic_content",
  "improves_previous_human_activity",
  "interacts_with_natural_persons",
  "law_enforcement_purpose",
  "life_health_insurance_risk_pricing",
  "medical_or_safety_component",
  "narrow_procedural_task",
  "predictive_policing_profiling",
  "preparatory_task",
  "profiling_of_natural_persons",
  "real_time_remote_biometric_public",
  "rtrb_strictly_necessary_authorised",
  "social_score_detrimental_treatment",
  "social_scoring",
  "subliminal_or_manipulative",
  "supports_human_assessment_on_verifiable_facts",
  "third_party_conformity_assessment_required",
] as const;

/* law_enforcement_purpose stays unknown in every preset: by the plan of
   B184 it is set only where real_time_remote_biometric_public is true, and
   no preset sets that fact true. */
function allFalse(overrides: Record<string, TriState> = {}): Record<string, TriState> {
  const flags: Record<string, TriState> = {};
  for (const key of ALL_FLAG_KEYS) flags[key] = "false";
  flags.law_enforcement_purpose = "unknown";
  return { ...flags, ...overrides };
}

export const SCENARIO_PRESETS: ScenarioPreset[] = [
  {
    id: "spamguard",
    label: "SpamGuard (email filter)",
    hint: "minimal_risk",
    description:
      "SpamGuard is a machine learning email filter deployed by a 20 person company for its own shared inboxes. It classifies incoming mail as ham, spam, or phishing using message text and metadata, moves likely spam to a retrievable quarantine folder, and never blocks, deletes, or answers mail on its own. It does not profile or score people and is not used in employment, credit, education, law enforcement, migration, or any other Annex III context.",
    domain: "email security",
    autonomy: "partial",
    /* The facts set true are those of
       tests/fixtures/demo_sessions/spamguard-classify.jsonl (the recorded
       request that produced the archived confident-minimal envelope), in
       the facts of B184: every flag false (law_enforcement_purpose unknown,
       see allFalse) except two Article 6(3) facts, narrow_procedural_task (sorting mail into folders and
       flagging links is a narrow procedural task) and
       detects_patterns_without_replacing_human_assessment, which are true
       but never reached since no Annex III use matches in the first place;
       preparatory_task is false (no assessment of an Annex III use
       follows). */
    flags: allFalse({
      narrow_procedural_task: "true",
      detects_patterns_without_replacing_human_assessment: "true",
    }),
  },
  {
    id: "shopbot",
    label: "ShopBot (customer chat)",
    hint: "limited_risk (Article 50)",
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
    /* interacts_with_natural_persons and two Article 6(3) facts
       (improves_previous_human_activity,
       detects_patterns_without_replacing_human_assessment) are left unknown:
       the README does not settle them, and none of the three affects this
       outcome (Annex III point 5(b) already matches via
       creditworthiness_evaluation, and profiling_of_natural_persons being
       true would cancel any accidental derogation candidacy anyway).
       narrow_procedural_task and preparatory_task are false: scoring an
       application is the assessment itself (scripts/make_compliance.py
       records the same reading). The other listed uses of Annex III,
       point 5(a) public benefits included, are false.
       The two deployer booleans (body_governed_by_public_law,
       private_entity_providing_public_services) are not sent at all: the
       form does not model them (see the task report). That does not change
       this preset's FRIA outcome, because creditworthiness_evaluation is
       itself a point 5(b) trigger that applies "for any deployer" per
       src/tere4ai/mcp_server/fria.py, evaluated before the deployer-category
       branch. */
    flags: allFalse({
      creditworthiness_evaluation: "true",
      profiling_of_natural_persons: "true",
      interacts_with_natural_persons: "unknown",
      improves_previous_human_activity: "unknown",
      detects_patterns_without_replacing_human_assessment: "unknown",
    }),
  },
  {
    id: "moodwatch",
    label: "MoodWatch (workplace emotion)",
    hint: "unacceptable_risk (Article 5(1)(f))",
    description:
      "MoodWatch continuously analyzes employees' facial expressions from webcam feeds and their typing patterns to infer emotions such as stress, frustration, and engagement in the workplace, aggregating results into dashboards visible to management. Participation is a condition of employment. It is not a medical device and is not deployed for safety reasons; its stated purpose is productivity and wellbeing monitoring.",
    domain: "employment",
    autonomy: "",
    flags: allFalse({
      emotion_recognition: "true",
      emotion_recognition_workplace_or_education: "true",
      /* The description states monitoring of employees during work hours
         (Annex III point 4(b)); no recruitment (point 4(a) stays false). */
      annex_iii_4b_work_relationships: "true",
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
      /* The description does not settle whether driver state is monitored
         as worker behaviour (Annex III point 4(b)), so that fact is left
         unknown, not false. */
      annex_iii_4b_work_relationships: "unknown",
    }),
  },
];
