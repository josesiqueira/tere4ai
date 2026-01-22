"""
Pydantic Models for Legal Document Structure

This module defines the structural representation of legal documents (regulations).
It captures ONLY the physical structure:
  - Recitals (numbered Whereas clauses)
  - Chapters (CHAPTER I, CHAPTER II, ...)
  - Sections (optional subdivisions within chapters)
  - Articles (numbered articles with titles)
  - Paragraphs (numbered subdivisions within articles)
  - Points (lettered items within paragraphs)
  - Annexes (appendices to the regulation)

NO semantic information is captured here:
  - No risk classifications
  - No actor/obligation labeling
  - No HLEG principles
  - No cross-references or interpretations

This is pure structural extraction for trustworthy, deterministic preprocessing.
"""

from typing import List, Optional, Any
from pydantic import BaseModel, Field, field_validator


class Recital(BaseModel):
    """
    One recital of a regulation, from the 'Whereas' part.

    Example: Recital (1), (2), (3), etc.
    """
    number: int = Field(
        description="Recital number as it appears in the text, e.g. 1 for '(1)'."
    )
    text: str = Field(
        description="Full text of the recital, without the leading '(number)'."
    )

    @field_validator('number', mode='before')
    @classmethod
    def coerce_number_to_int(cls, v: Any) -> int:
        """Convert string to int if needed (LLM may return '1' instead of 1)."""
        if isinstance(v, str):
            return int(v)
        return v


class Point(BaseModel):
    """
    A lettered or numbered point inside a paragraph or directly under an article.
    Example: (a), (b), (c).
    """
    marker: str = Field(
        description="Point marker as string, e.g. 'a', 'b', '1'."
    )
    text: str = Field(
        description="Full text of the point, without the leading marker."
    )


class Paragraph(BaseModel):
    """
    Numbered paragraph inside an article.
    Example: '1.', '2.'.
    """
    index: int = Field(
        description="Paragraph number inside the article, e.g. 1 for '1.'."
    )
    text: str = Field(
        description="Full text of the paragraph, excluding lettered points."
    )
    points: List[Point] = Field(
        default_factory=list,
        description="Optional list of lettered points within this paragraph."
    )

    @field_validator('index', mode='before')
    @classmethod
    def coerce_index_to_int(cls, v: Any) -> int:
        """Convert string to int if needed (LLM may return '1' instead of 1)."""
        if isinstance(v, str):
            return int(v)
        return v


class Article(BaseModel):
    """
    One article of the regulation.

    Contains a title and a list of numbered paragraphs (which may contain points).
    """
    number: int = Field(
        description="Article number, e.g. 1 for 'Article 1'."
    )
    title: str = Field(
        description="Article title as shown in the regulation."
    )
    paragraphs: List[Paragraph] = Field(
        default_factory=list,
        description="Ordered list of paragraphs in this article."
    )

    @field_validator('number', mode='before')
    @classmethod
    def coerce_number_to_int(cls, v: Any) -> int:
        """Convert string to int if needed (LLM may return '1' instead of 1)."""
        if isinstance(v, str):
            return int(v)
        return v


class Section(BaseModel):
    """
    Optional section within a chapter.
    Example: 'SECTION 1 - Classification rules'.
    """
    number: str = Field(
        description="Section number as string (often roman or decimal), e.g. '1'."
    )
    title: str = Field(
        description="Section title."
    )
    articles: List[Article] = Field(
        default_factory=list,
        description="Ordered list of articles in this section."
    )

    @field_validator('number', mode='before')
    @classmethod
    def coerce_number_to_str(cls, v: Any) -> str:
        """Convert integer to string if needed (LLM often returns int instead of str)."""
        if isinstance(v, int):
            return str(v)
        return v


class Chapter(BaseModel):
    """
    One chapter of the regulation.
    Example: 'CHAPTER I - GENERAL PROVISIONS'.
    """
    number: str = Field(
        description="Chapter number as string (e.g. 'I', 'II', 'III')."
    )
    title: str = Field(
        description="Chapter title."
    )
    # Some chapters have sections; others have articles directly.
    sections: List[Section] = Field(
        default_factory=list,
        description="Optional sections within the chapter."
    )
    articles: List[Article] = Field(
        default_factory=list,
        description="Articles directly under this chapter (when there are no sections)."
    )

    @field_validator('number', mode='before')
    @classmethod
    def coerce_number_to_str(cls, v: Any) -> str:
        """Convert integer to string if needed (LLM often returns int instead of str)."""
        if isinstance(v, int):
            return str(v)
        return v


class Annex(BaseModel):
    """
    Annex to the regulation.
    Example: 'ANNEX I', 'ANNEX II', etc.
    """
    number: str = Field(
        description="Annex number as string, typically roman (e.g. 'I', 'II')."
    )
    title: str = Field(
        description="Annex title."
    )
    raw_text: str = Field(
        description="Full raw text of the annex body."
    )

    @field_validator('number', mode='before')
    @classmethod
    def coerce_number_to_str(cls, v: Any) -> str:
        """Convert integer to string if needed (LLM often returns int instead of str)."""
        if isinstance(v, int):
            return str(v)
        return v


class PreprocessedLegalDocument(BaseModel):
    """
    Structural representation of a single legal document (here: the EU AI Act).

    This is the output of the structural preprocessing agent. It contains
    ONLY physical structure (recitals, chapters, articles, annexes), no
    semantic labels like risk categories or actors.
    """
    document_id: str = Field(
        description="Stable identifier for this document, e.g. 'eu_ai_act_2024'."
    )
    official_title: str = Field(
        description="Full official title of the regulation as printed."
    )
    short_title: Optional[str] = Field(
        default=None,
        description="Optional short/working title, e.g. 'EU AI Act'."
    )
    year: Optional[int] = Field(
        default=None,
        description="Year of adoption/publication, if known."
    )
    recitals: List[Recital] = Field(
        default_factory=list,
        description="Ordered list of recitals (Whereas (1), (2), ...)."
    )
    chapters: List[Chapter] = Field(
        default_factory=list,
        description="Ordered list of chapters."
    )
    annexes: List[Annex] = Field(
        default_factory=list,
        description="Ordered list of annexes."
    )
