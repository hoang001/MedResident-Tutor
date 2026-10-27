from fastapi import APIRouter

from app.ai.rag.router import router as rag_router
from app.api.v1.system import router as system_router
from app.modules.auth.router import router as auth_router
from app.modules.documents.router import router as documents_router
from app.modules.practice.router import router as practice_router
from app.modules.questions.router import router as questions_router
from app.modules.topics.router import router as topics_router

router = APIRouter()
router.include_router(system_router)
router.include_router(auth_router)
router.include_router(topics_router)
router.include_router(documents_router)
router.include_router(rag_router)


router.include_router(practice_router)

router.include_router(questions_router)
