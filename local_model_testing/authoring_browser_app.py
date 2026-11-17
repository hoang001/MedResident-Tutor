"""Isolated browser fixture: replay authoring, mock grading, real API and PostgreSQL."""
import asyncio
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.core.security import hash_password
from app.main import app
from app.modules.questions import authoring
from app.modules.users.models import User
from app.common.enums import UserRole
from tests.e2e.bank_fixtures import seed_sources

assert make_url(get_settings().database_url).database == "medresident_test_authoring_20261112"


async def replay_retrieve(scope):
    e={"source_unit_id":"REPLAY_SOURCE_1","source_id":"REPLAY_BOOK","title":"Synthetic browser source",
       "content":"Synthetic source statement with conditions; not clinical learning content.","page_start":1,"page_end":1}
    p={"source_unit_id":e["source_unit_id"],"source_id":e["source_id"],"sha256":"a"*64,"book_year":2026,
       "book_title":"Synthetic replay only"}
    bundle={"scope":scope.model_dump(),"evidence":[e],"provenance":[p],"trace":{"fallback_reason":"browser_replay_not_live_retrieval"}}
    return {**bundle,"bundle_token":authoring.seal(bundle,"evidence"),"status":"replay"}


async def replay_propose(body):
    bundle,evidence=authoring.selected(body)
    if bundle["scope"]!=body.scope.model_dump():
        from fastapi import HTTPException
        raise HTTPException(409,"Stale proposal")
    value=authoring.validate_proposal({"reference_answer":"Replay source statement, for workflow testing only.",
        "criteria":[{"description":"Replay criterion", "max_score":body.scope.max_score,
                     "source_unit_ids":[evidence[0]["source_unit_id"]]}],"insufficient_basis":[]},evidence,body.scope.max_score)
    return {**value,"proposal_token":authoring.seal({"version":"authoring-v1", "mode":"browser_replay",
        "scope":body.scope.model_dump(),"selected_ids":body.selected_ids,"proposal":value},"proposal")}


authoring.retrieve=replay_retrieve
authoring.propose=replay_propose


async def seed():
    async with SessionFactory() as session, session.begin():
        for email,role in [("authoring-admin@example.com",UserRole.ADMIN),("authoring-learner@example.com",UserRole.LEARNER)]:
            user=await session.scalar(select(User).where(User.email==email))
            if not user:
                user=User(email=email,full_name="Authoring browser fixture",role=role,hashed_password=hash_password("BrowserFixtureOnly123!"),is_active=True)
                session.add(user)
                await session.flush()
            if role==UserRole.ADMIN:
                await seed_sources(session,user.id,Path("/tmp/authoring-fixtures"))


from contextlib import asynccontextmanager
original_lifespan=app.router.lifespan_context


@asynccontextmanager
async def lifespan(application):
    async with original_lifespan(application):
        await seed()
        yield


app.router.lifespan_context=lifespan
