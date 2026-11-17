"""Real workflow, explicitly mock, on the named disposable copy only."""
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.core.security import hash_password
from app.common.enums import UserRole
from app.main import app
from app.modules.users.models import User

assert make_url(get_settings().database_url).database=='medresident_test_bank_browser_20261116'
assert get_settings().practice_provider=='mock'
assert get_settings().model_calls_enabled is False

def forbidden(*a,**kw): raise AssertionError('Unexpected live KG/vector retrieval for approved package')
import app.ai.retrieval.factory as retrieval
retrieval.create_retriever=forbidden
retrieval.is_textbook_question=forbidden

original=app.router.lifespan_context
@asynccontextmanager
async def lifespan(application):
    async with original(application):
        async with SessionFactory() as s,s.begin():
            if not await s.scalar(select(User).where(User.email=='bank-workflow-test@example.com')):
                s.add(User(email='bank-workflow-test@example.com',full_name='Mock workflow test — disposable database',
                    hashed_password=hash_password('BankWorkflowOnly123!'),role=UserRole.LEARNER,is_active=True))
        yield
app.router.lifespan_context=lifespan
