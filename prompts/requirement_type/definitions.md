## Requirement type (ISO/IEC/IEEE 29148:2018 clause 5.2.8.3, DEC-19)

ISO/IEC/IEEE 29148:2018 clause 5.2.8.3 gives examples of the requirements
type attribute, not a closed list; this project uses three of them. A
typed requirement has exactly one requirement_type, one of three values:

- "functional": the AI system or one of its elements shall perform a
  function or produce a result. 29148 (p. 15): "Functional/Performance.
  Functional requirements describe the system or system element functions
  or tasks to be performed by the system." ISO/IEC/IEEE 24765:2017 3.1704
  (p. 195): "1. statement that identifies what results a product or
  process shall produce 2. requirement that specifies a function that a
  system or system component shall perform". Example: Article 12(1), the
  system technically allows the automatic recording of events.
- "quality": the AI system or its data shall have a property or meet a
  level. 29148 names the type Quality (Non-Functional) Requirements (p.
  16): "Include a number of the 'ilities' in requirements to include, for
  example, transportability, survivability, flexibility, portability,
  reusability, reliability, maintainability and security." 24765 3.3287,
  definition 1 (p. 364): "requirement that a software attribute be present
  in software to satisfy a contract, standard, specification, or other
  formally imposed document". The definition speaks of software; applying
  it to the AI system's training, validation and testing data is this
  project's reading beyond the source. Examples: Article 15(1), appropriate
  accuracy, robustness and cybersecurity; Article 10(3), data sets that
  are relevant and sufficiently representative.
- "process": the obligation constrains the operator's activities,
  organisation or records rather than the AI system or its data, during
  development or after it (deployment, use, monitoring, reporting). 29148
  (p. 15): "Process Requirements. These are stakeholder, usually acquirer
  or user, requirements imposed through the contract or statement of
  work." SWEBOK Guide V4.0a, Software Requirements 1.3 (p. 1-3): project
  requirements, also called process requirements, "constrain the project
  that constructs the software." Glinz, RE 2007, section 4.2 (p. 24): "As
  project and process requirements are conceptually different from system
  requirements, they should be distinguished at the root level and not in
  a sub-category such as non-functional requirements." So process is a
  type of its own beside functional and quality, never a kind of quality.
  Examples: Article 17, a quality management system; Article 19, keeping
  the logs; Article 72, post-market monitoring.

Reading rules:

1. Read by the outcome the obligation constrains, not by its main verb:
   "shall be designed and developed in such a way that" (Articles 13(1),
   14(1), 15(1)) is functional or quality by the outcome that follows.
2. A required level of a function's output is quality when the
   obligation is about the level (Article 15(1)).
3. A duty to draw up, keep, update or submit documents or logs is process
   (Articles 11(1), 18, 19, 47, 49); a required content of what is
   delivered with the system (the instructions for use, Article 13(2) and
   13(3)) is functional, a result the product shall produce.
4. An interface requirement is functional; a usability or human factors
   requirement is quality.
5. The type follows what the obligation constrains, not where it comes
   from: an obligation is not process because it is a legal duty, although
   29148 says process requirements include compliance with laws.
6. An obligation that mixes a system function and an operator process
   takes the type of the outcome it mainly constrains.
