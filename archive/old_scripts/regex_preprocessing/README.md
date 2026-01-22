# EU AI Act Regex-Based Preprocessing

This folder contains a pure regex-based solution for preprocessing the EU AI Act, without using any LLMs.

## Files

- `preprocess_eu_ai_act.py` - Main preprocessing script that parses the EU AI Act and ingests data into Neo4j
- `validate_database.py` - Validation script to verify database content matches the source file
- `.env` - Environment configuration for Neo4j connection (port 7688 for the regex container)

## Usage

```bash
# From the project root directory
cd /home/jose/Documents/18\ Novembro/trustworthy_project_v0

# Run preprocessing (clears database and reloads all data)
.venv/bin/python3 regex_preprocessing/preprocess_eu_ai_act.py

# Run validation
.venv/bin/python3 regex_preprocessing/validate_database.py
```

## What Gets Extracted

The preprocessing extracts the complete structure of the EU AI Act:

| Element | Count | Description |
|---------|-------|-------------|
| Recitals | 180 | Whereas clauses (1-180) |
| Chapters | 13 | CHAPTER I through XIII |
| Sections | 16 | Sections within chapters |
| Articles | 113 | Article 1 through 113 |
| Paragraphs | 519 | Numbered paragraphs within articles |
| Points | 382 | Lettered/numbered points within paragraphs |
| Annexes | 13 | ANNEX I through XIII |

## Neo4j Graph Schema

```
(Regulation)
  ├── HAS_RECITAL → (Recital)
  ├── HAS_CHAPTER → (Chapter)
  │     ├── HAS_SECTION → (Section)
  │     │     └── HAS_ARTICLE → (Article)
  │     │           └── HAS_PARAGRAPH → (Paragraph)
  │     │                 └── HAS_POINT → (Point)
  │     └── HAS_ARTICLE → (Article)  [direct articles, no section]
  │           └── HAS_PARAGRAPH → (Paragraph)
  │                 └── HAS_POINT → (Point)
  └── HAS_ANNEX → (Annex)
```

## Node Properties

### Regulation
- `document_id`: "eu_ai_act_2024"
- `official_title`: Full regulation title
- `short_title`: "Artificial Intelligence Act"
- `regulation_number`: "2024/1689"
- `year`: 2024

### Recital
- `id`: Unique identifier
- `number`: Recital number (1-180)
- `text`: Full recital text

### Chapter
- `id`: Unique identifier
- `number`: Roman numeral (I-XIII)
- `number_int`: Integer equivalent (1-13)
- `title`: Chapter title

### Section
- `id`: Unique identifier
- `number`: Section number
- `title`: Section title

### Article
- `id`: Unique identifier
- `number`: Article number (1-113)
- `title`: Article title
- `full_text`: Complete article text

### Paragraph
- `id`: Unique identifier
- `number`: Paragraph number
- `text`: Paragraph text

### Point
- `id`: Unique identifier
- `marker`: Point marker (a, b, c, i, ii, etc.)
- `text`: Point text
- `order`: Order within paragraph

### Annex
- `id`: Unique identifier
- `number`: Roman numeral (I-XIII)
- `number_int`: Integer equivalent (1-13)
- `title`: Annex title
- `full_text`: Complete annex text

## Neo4j Connection

The scripts connect to:
- URI: `neo4j://localhost:7688` (mapped to container `neo4j_trustworthy_project_v0_regex`)
- User: `neo4j`
- Password: `password`

## Key Features

1. **Deterministic Processing**: No LLM randomness - same input always produces same output
2. **Complete Extraction**: 100% of structural elements extracted (all 113 articles)
3. **Validated Output**: Automated validation confirms database matches source
4. **Idempotent Operations**: Uses MERGE for all database writes
5. **Fast Execution**: Processes entire document in seconds

## Validation Checks

The validation script performs 8 comprehensive checks:

1. Regulation node exists
2. All 180 recitals present
3. All 13 chapters present
4. All 113 articles present
5. All 16 sections present
6. All 13 annexes present
7. Content samples verification (spot checks)
8. Graph structure integrity
