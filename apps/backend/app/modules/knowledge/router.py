from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.modules.auth.dependencies import CurrentUser
from app.modules.knowledge.service import GraphStore, get_graph_store

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
Graph = Annotated[GraphStore, Depends(get_graph_store)]


@router.get("/status")
async def status(user: CurrentUser, graph: Graph):
    snapshot = await graph.snapshot()
    return {
        "status": "ready",
        "nodes": len(snapshot.nodes),
        "relations": len(snapshot.edges),
        "model_calls_enabled": get_settings().model_calls_enabled,
    }


@router.get("/search")
async def search(
    user: CurrentUser,
    graph: Graph,
    q: str = Query(default="", max_length=200),
    book: str = Query(default="", max_length=100),
    chapter: int | None = Query(default=None, ge=1),
    kind: str = Query(default="", max_length=60),
    offset: int = Query(default=0, ge=0, le=20000),
    limit: int = Query(default=20, ge=1, le=50),
):
    return (await graph.snapshot()).search(q, book, chapter, kind, offset, limit)


@router.get("/node")
async def node(user: CurrentUser, graph: Graph, id: str = Query(max_length=300)):
    return (await graph.snapshot()).detail(id)


@router.get("/curriculum")
async def curriculum(user: CurrentUser, graph: Graph):
    return (await graph.snapshot()).curriculum()


@router.get("/sources")
async def sources(user: CurrentUser, graph: Graph):
    return (await graph.snapshot()).sources(get_settings().knowledge_data_root)


@router.get("/pdf/{source_id}")
async def pdf(source_id: str, user: CurrentUser, graph: Graph):
    path = (await graph.snapshot()).pdf_path(source_id, get_settings().knowledge_data_root)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=path.name,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, no-store"},
    )
