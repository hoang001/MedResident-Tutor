"""Import all mapped classes so Alembic and test metadata see every table."""

from app.modules.documents.models import (
    Concept,
    ConceptRelation,
    Document,
    DocumentChunk,
    DocumentConcept,
    DocumentSection,
)
from app.modules.documents.source_units import SourceUnit
from app.modules.exams.models import Exam, ExamAttempt, ExamQuestion, UserAnswer
from app.modules.practice.models import PracticeAttempt
from app.modules.progress.models import LearningResult
from app.modules.questions.models import (
    Question,
    QuestionOption,
    Rubric,
    RubricCriterion,
    RubricCriterionSourceUnit,
)
from app.modules.recommendations.models import Recommendation
from app.modules.specialties.models import Specialty
from app.modules.topics.models import Topic
from app.modules.users.models import User

__all__ = [
    "PracticeAttempt",
    "Concept",
    "ConceptRelation",
    "Document",
    "DocumentChunk",
    "DocumentConcept",
    "DocumentSection",
    "Exam",
    "ExamAttempt",
    "ExamQuestion",
    "LearningResult",
    "Question",
    "QuestionOption",
    "Recommendation",
    "Rubric",
    "RubricCriterion",
    "RubricCriterionSourceUnit",
    "SourceUnit",
    "Specialty",
    "Topic",
    "User",
    "UserAnswer",
]
