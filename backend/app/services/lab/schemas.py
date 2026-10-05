"""Pydantic schemas for the LLM's structured outputs.

The model returns JSON; these schemas **validate and coerce** it — so a generated
objective, quiz question, or summary is schema-validated, not hand-parsed. Invalid
items raise a ValidationError and are dropped; the generators fall back if a whole
batch fails validation.
"""
import uuid

from pydantic import BaseModel, Field, field_validator, model_validator

_DIFFICULTIES = {"beginner", "intermediate", "advanced"}
_DEFAULT_HINT = "Re-read the relevant part of the material."


class Objective(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    title: str
    difficulty: str = "beginner"
    focus: str = ""

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = str(v).strip()
        if not v:
            raise ValueError("empty objective title")
        return v

    @field_validator("difficulty")
    @classmethod
    def _difficulty(cls, v: str) -> str:
        v = str(v).strip().lower()
        return v if v in _DIFFICULTIES else "beginner"

    @field_validator("focus")
    @classmethod
    def _focus(cls, v) -> str:
        return str(v or "").strip()


class Question(BaseModel):
    question: str
    options: list[str]
    correctIndex: int = 0
    explanation: str = ""
    hint: str = _DEFAULT_HINT
    concept: str = ""

    @field_validator("question")
    @classmethod
    def _question(cls, v: str) -> str:
        v = str(v).strip()
        if not v:
            raise ValueError("empty question")
        return v

    @field_validator("concept", mode="before")
    @classmethod
    def _concept(cls, v) -> str:
        return str(v or "").strip()  # null/missing concept must not drop the question

    @model_validator(mode="after")
    def _shape(self) -> "Question":
        opts = [str(o).strip() for o in self.options if str(o).strip()][:4]
        if len(opts) < 2:
            raise ValueError("need at least 2 options")
        self.options = opts
        if not (0 <= self.correctIndex < len(opts)):
            self.correctIndex = 0
        self.hint = (self.hint or "").strip() or _DEFAULT_HINT
        return self


class PerObjective(BaseModel):
    title: str = ""
    comment: str = ""


class Summary(BaseModel):
    overall: str = ""
    perObjective: list[PerObjective] = Field(default_factory=list)
    studyTips: list[str] = Field(default_factory=list)
