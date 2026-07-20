"""Import all mapped classes so Alembic and test metadata see every table."""

from app.modules.documents.models import (
    Concept,
    ConceptRelation,
    Document,
    DocumentChunk,
    DocumentConcept,
    DocumentSection,
)
from app.modules.exams.models import Exam, ExamAttempt, ExamQuestion, UserAnswer
from app.modules.progress.models import LearningResult
from app.modules.questions.models import Question, QuestionOption, Rubric, RubricCriterion
from app.modules.recommendations.models import Recommendation
from app.modules.specialties.models import Specialty
from app.modules.topics.models import Topic
from app.modules.users.models import User

__all__ = [
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
    "Specialty",
    "Topic",
    "User",
    "UserAnswer",
]
