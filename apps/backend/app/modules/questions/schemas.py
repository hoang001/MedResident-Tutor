from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


class CriterionEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion_id: str | None = Field(default=None, min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=4000)
    max_score: FiniteFloat = Field(gt=0, strict=True)
    source_unit_ids: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def check(self):
        if not self.description.strip() or len(set(self.source_unit_ids)) != len(
            self.source_unit_ids
        ):
            raise ValueError("Invalid criterion or duplicate evidence")
        return self


class QuestionEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int | None = Field(default=None, ge=1)
    content: str = Field(min_length=1, max_length=4000)
    rubric_name: str = Field(min_length=1, max_length=255)
    max_score: FiniteFloat = Field(gt=0, strict=True)
    criteria: list[CriterionEdit] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def check(self):
        import math

        ids = [c.criterion_id for c in self.criteria if c.criterion_id is not None]
        if len(set(ids)) != len(ids) or not self.content.strip() or not self.rubric_name.strip():
            raise ValueError("Invalid content or duplicate criterion IDs")
        if not math.isclose(
            sum(c.max_score for c in self.criteria), self.max_score, rel_tol=0, abs_tol=1e-9
        ):
            raise ValueError("Rubric total must equal criterion total")
        return self


class AvailabilityEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    is_available: bool
