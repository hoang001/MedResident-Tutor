from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    LEARNER = "LEARNER"


class DocumentProcessingStatus(StrEnum):
    UPLOADED = "UPLOADED"
    EXTRACTING = "EXTRACTING"
    CHUNKING = "CHUNKING"
    INDEXING = "INDEXING"
    READY = "READY"
    FAILED = "FAILED"


class RelationType(StrEnum):
    PREREQUISITE_OF = "PREREQUISITE_OF"
    RELATED_TO = "RELATED_TO"
    PART_OF = "PART_OF"


class QuestionType(StrEnum):
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    SHORT_ANSWER = "SHORT_ANSWER"


class AttemptStatus(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    GRADED = "GRADED"


class RecommendationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISMISSED = "DISMISSED"
    COMPLETED = "COMPLETED"
