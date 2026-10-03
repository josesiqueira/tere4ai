// TERE4AI v2 Layer 0+1 Cypher constraints.
// @implements: DEC-09 (partial: Neo4j store constraints)
// @grounded_by: REF-20, REF-21, REF-22, REF-08, REF-23
// Format: one full statement per line, each preceded by a comment line,
// blank line between statements. Property types follow schema/json_schemas/nodes.schema.json.

// Uniqueness of SourceDocument.id (Layer 0)
CREATE CONSTRAINT sourcedocument_id_unique IF NOT EXISTS FOR (n:SourceDocument) REQUIRE n.id IS UNIQUE;

// Uniqueness of SourceFile.id (Layer 0)
CREATE CONSTRAINT sourcefile_id_unique IF NOT EXISTS FOR (n:SourceFile) REQUIRE n.id IS UNIQUE;

// Uniqueness of BuildRun.id (Layer 0)
CREATE CONSTRAINT buildrun_id_unique IF NOT EXISTS FOR (n:BuildRun) REQUIRE n.id IS UNIQUE;

// Uniqueness of Regulation.id (Layer 1)
CREATE CONSTRAINT regulation_id_unique IF NOT EXISTS FOR (n:Regulation) REQUIRE n.id IS UNIQUE;

// Uniqueness of Chapter.id (Layer 1)
CREATE CONSTRAINT chapter_id_unique IF NOT EXISTS FOR (n:Chapter) REQUIRE n.id IS UNIQUE;

// Uniqueness of Section.id (Layer 1)
CREATE CONSTRAINT section_id_unique IF NOT EXISTS FOR (n:Section) REQUIRE n.id IS UNIQUE;

// Uniqueness of Article.id (Layer 1)
CREATE CONSTRAINT article_id_unique IF NOT EXISTS FOR (n:Article) REQUIRE n.id IS UNIQUE;

// Uniqueness of Paragraph.id (Layer 1)
CREATE CONSTRAINT paragraph_id_unique IF NOT EXISTS FOR (n:Paragraph) REQUIRE n.id IS UNIQUE;

// Uniqueness of Point.id (Layer 1, populated from Formex in M2)
CREATE CONSTRAINT point_id_unique IF NOT EXISTS FOR (n:Point) REQUIRE n.id IS UNIQUE;

// Uniqueness of Recital.id (Layer 1)
CREATE CONSTRAINT recital_id_unique IF NOT EXISTS FOR (n:Recital) REQUIRE n.id IS UNIQUE;

// Uniqueness of Annex.id (Layer 1)
CREATE CONSTRAINT annex_id_unique IF NOT EXISTS FOR (n:Annex) REQUIRE n.id IS UNIQUE;

// Uniqueness of AnnexItem.id (Layer 1, populated from Formex in M2)
CREATE CONSTRAINT annexitem_id_unique IF NOT EXISTS FOR (n:AnnexItem) REQUIRE n.id IS UNIQUE;

// Uniqueness of UnitVersion.id (Layer 1, the 2024 wording of a changed unit, B132)
CREATE CONSTRAINT unitversion_id_unique IF NOT EXISTS FOR (n:UnitVersion) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT crossreference_id_unique IF NOT EXISTS FOR (n:CrossReference) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT condition_id_unique IF NOT EXISTS FOR (n:Condition) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT exception_id_unique IF NOT EXISTS FOR (n:Exception) REQUIRE n.id IS UNIQUE;

// Chapter.number is a Roman numeral string per nodes.schema.json
CREATE CONSTRAINT chapter_number_type IF NOT EXISTS FOR (n:Chapter) REQUIRE n.number IS :: STRING;

// Section.number is an integer per nodes.schema.json
CREATE CONSTRAINT section_number_type IF NOT EXISTS FOR (n:Section) REQUIRE n.number IS :: INTEGER;

// Drop the INTEGER type constraint on Article.number of databases loaded before B132: CREATE ... IF NOT EXISTS would keep it under its old name and refuse the label "4a"
DROP CONSTRAINT article_number_type IF EXISTS;

// Article.number is the Act's label, a string such as "4a", per nodes.schema.json (B132); a new name, so a later run drops nothing
CREATE CONSTRAINT article_number_label_type IF NOT EXISTS FOR (n:Article) REQUIRE n.number IS :: STRING;

// Article.sort_key is an integer (4a gives 401) per nodes.schema.json (B132)
CREATE CONSTRAINT article_sort_key_type IF NOT EXISTS FOR (n:Article) REQUIRE n.sort_key IS :: INTEGER;

// Drop the INTEGER type constraint on Paragraph.index of databases loaded before B132, for the same reason (the label "1a")
DROP CONSTRAINT paragraph_index_type IF EXISTS;

// Paragraph.index is the Act's label, a string such as "1a", per nodes.schema.json (B132); a new name, so a later run drops nothing
CREATE CONSTRAINT paragraph_index_label_type IF NOT EXISTS FOR (n:Paragraph) REQUIRE n.index IS :: STRING;

// Paragraph.sort_key is an integer (1a gives 101) per nodes.schema.json (B132)
CREATE CONSTRAINT paragraph_sort_key_type IF NOT EXISTS FOR (n:Paragraph) REQUIRE n.sort_key IS :: INTEGER;

// Recital.number is an integer (1 to 180) per nodes.schema.json
CREATE CONSTRAINT recital_number_type IF NOT EXISTS FOR (n:Recital) REQUIRE n.number IS :: INTEGER;

// Annex.number is a Roman numeral string per nodes.schema.json
CREATE CONSTRAINT annex_number_type IF NOT EXISTS FOR (n:Annex) REQUIRE n.number IS :: STRING;

// Point.marker is a string per nodes.schema.json
CREATE CONSTRAINT point_marker_type IF NOT EXISTS FOR (n:Point) REQUIRE n.marker IS :: STRING;

// AnnexItem.marker is a string per nodes.schema.json
CREATE CONSTRAINT annexitem_marker_type IF NOT EXISTS FOR (n:AnnexItem) REQUIRE n.marker IS :: STRING;
