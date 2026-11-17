"""UI-only fixture, real application routes, explicitly mock grading, isolated DB."""
from contextlib import asynccontextmanager
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.core.security import hash_password
from app.common.enums import UserRole
from app.main import app
from app.modules.users.models import User
from app.modules.documents.source_units import SourceUnit
from app.modules.practice import router as practice_routes
from app.modules.practice.providers import MockProvider
from tests.e2e.bank_fixtures import seed_sources

assert make_url(get_settings().database_url).database=='medresident_test_ui_completion_20261116'
assert get_settings().practice_provider=='mock' and get_settings().model_calls_enabled is False
assert get_settings().authoring_provider=='off'
practice_routes.get_provider=lambda *_:MockProvider('teaching_error')
original=app.router.lifespan_context

@asynccontextmanager
async def lifespan(application):
    async with original(application):
        async with SessionFactory() as s,s.begin():
            for email,role in [('ui-student@example.com',UserRole.LEARNER),('ui-admin@example.com',UserRole.ADMIN)]:
                u=await s.scalar(select(User).where(User.email==email))
                if not u:
                    u=User(email=email,full_name='Học viên kiểm thử' if role==UserRole.LEARNER else 'Quản trị kiểm thử',role=role,
                        hashed_password=hash_password('UiFixtureOnly123!'),is_active=True)
                    s.add(u); await s.flush()
                if role==UserRole.ADMIN and not await s.scalar(select(SourceUnit.id).where(SourceUnit.external_id=='FIXTURE_SU_A')):
                    await seed_sources(s,u.id,Path('/tmp/ui-fixture-sources'))
        yield
app.router.lifespan_context=lifespan
