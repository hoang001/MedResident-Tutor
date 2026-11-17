"""Idempotent authorized import. Uses the same save/readiness/publication as admin UI."""
import asyncio
import sys
import uuid
from pathlib import Path

from .common import ROOT, RUN, digest, inside, read, write
from .content import TOPICS


async def run():
    import app.models  # noqa: F401
    from sqlalchemy import select
    from app.core.database import SessionFactory
    from app.common.enums import UserRole, DocumentProcessingStatus
    from app.modules.users.models import User
    from app.modules.specialties.models import Specialty
    from app.modules.topics.models import Topic
    from app.modules.documents.models import Document
    from app.modules.documents.source_units import SourceUnit
    from app.modules.questions.models import Question, Rubric, RubricCriterion
    from app.modules.questions.schemas import QuestionEdit
    from app.modules.questions.service import save, get_question
    from app.modules.questions.publication import publish
    from .build import REVIEW, SCORING
    records=read('authored-questions.json')
    units={u['source_unit_id']:u for u in read('source-units.json')}
    sources=read('sources-verified.json')
    assert not read('anchor-issues.json')
    assert len(records)==95
    assert (RUN/'backup/postgres.dump').stat().st_size>1000
    results=[]
    # The application mounts ./data at /app/data; /workspace is a temporary
    # authoring-runner mount, so it must not become a persisted file locator.
    if '--validate-only' not in sys.argv:
        corrected=[]
        async with SessionFactory() as session,session.begin():
            docs=list(await session.scalars(select(Document).where(Document.external_id.startswith('QB26_DOC_'))))
            for d in docs:
                source=(d.import_metadata or {}).get('source',{})
                path=source.get('pdf_path','')
                assert path.startswith('data/raw-source/') and source['sha256']==d.source_sha256
                target='/app/'+path
                if d.storage_path!=target:
                    d.storage_path=target
                    corrected.append(d.external_id)
        if corrected: write('document-path-correction.json',dict(document_ids=corrected,scope='only_new_batch_documents',source_content_unchanged=True,reason='Use persistent backend mount /app/data, not temporary runner /workspace'))
    async with SessionFactory() as session:
        account=await session.scalar(select(User.id).where(User.role==UserRole.ADMIN).order_by(User.created_at))
    assert account

    async def materialize(session, q):
        old=await session.scalar(select(Question).where(Question.external_id==q['question_id']))
        fingerprint=digest(q)
        if old:
            assert old.import_metadata.get('batch_content_sha256')==fingerprint, 'Existing revision differs; explicit new revision required'
            assert old.is_available and old.import_metadata.get('approved_package'), 'Existing import incomplete'
            package=old.import_metadata['approved_package']
            assert digest({k:v for k,v in package.items() if k!='sha256'})==package['sha256']
            return dict(original_ids=q['original_ids'],question_id=old.external_id,version=old.bank_version,package_hash=package['sha256'],action='unchanged')
        specialty_id=uuid.uuid5(uuid.NAMESPACE_URL,'medresident:bank-expansion:orthopaedics')
        specialty=await session.get(Specialty,specialty_id)
        if not specialty:
            specialty=await session.scalar(select(Specialty).where(Specialty.name=='Chấn thương chỉnh hình'))
            if not specialty:
                specialty=Specialty(id=specialty_id,name='Chấn thương chỉnh hình',description='Ngân hàng demo đối chiếu nguồn bởi Codex; chưa xác nhận duyệt chuyên gia.')
                session.add(specialty)
                await session.flush()
        tid=uuid.uuid5(uuid.NAMESPACE_URL,'medresident:bank-expansion:topic:'+q['topic'])
        if not await session.get(Topic,tid):
            session.add(Topic(id=tid,specialty_id=specialty.id,name=TOPICS[q['topic']],description='Phân nhóm nội dung ngân hàng demo; không phải xác nhận phân phối chương trình chính thức.'))
            await session.flush()
        required={sid for c in q['criteria'] for sid in c['source_unit_ids']}
        for sid in sorted(required):
            u=units[sid]; source=sources[u['source_id']]
            did='QB26_DOC_'+source['sha256'][:24]
            d=await session.scalar(select(Document).where(Document.external_id==did))
            if not d:
                path=ROOT/source['pdf_path']
                d=Document(external_id=did,name=source['title'],original_filename=Path(source['pdf_path']).name,
                    storage_path='/app/'+source['pdf_path'],mime_type='application/pdf',file_size=path.stat().st_size,
                    source_name=source['title'],source_url=source.get('url'),source_sha256=source['sha256'],
                    version=str(source['year']),processing_status=DocumentProcessingStatus.READY,created_by=account,
                    import_metadata=dict(batch='bank-expansion-20261116',source=source,review=REVIEW))
                session.add(d); await session.flush()
            assert d.source_sha256==u['source_sha256']
            existing=await session.scalar(select(SourceUnit).where(SourceUnit.external_id==sid))
            if existing:
                assert existing.content==u['content'] and existing.document_id==d.id
            else:
                session.add(SourceUnit(external_id=sid,document_id=d.id,title=u['title'],content=u['content'],
                    pdf_page_start=u['pdf_page_start'],pdf_page_end=u['pdf_page_end'],section=u['locator'],chapter=TOPICS[q['topic']],
                    import_metadata=dict(batch='bank-expansion-20261116',expert_review={'status':'unverified'},
                        source_review=REVIEW,content_sha256=u['content_sha256'],page_text_sha256=u['page_text_sha256'],locator=u['locator'])))
        await session.flush()
        body=QuestionEdit(content=q['question'],reference_answer=q['reference_answer'],rubric_name=TOPICS[q['topic']]+' — '+q['objective'],
            max_score=q['max_score'],course='BSNT Chấn thương chỉnh hình — ngân hàng demo',topic=TOPICS[q['topic']],
            criteria=[{k:c[k] for k in ('description','max_score','source_unit_ids')} for c in q['criteria']])
        saved=await save(session,account,body)
        entity=await get_question(session,saved['question_id'])
        entity.external_id=q['question_id']
        entity.topic_id=tid
        entity.import_metadata={**entity.import_metadata,'batch':'bank-expansion-20261116','batch_content_sha256':fingerprint,
            'source_review':REVIEW,'source_type':q['source_type'],'original_ids':q['original_ids'],
            'bank_review':{'status':'codex_source_checked_demo','actor':'Codex','expert_verified':False}}
        r=await session.scalar(select(Rubric).where(Rubric.question_id==entity.id))
        r.external_id=q['question_id']+'_R'
        r.import_metadata={**r.import_metadata,'source_review':REVIEW,
            'dataset_fields':{**r.import_metadata['dataset_fields'],'scoring_rule':SCORING,'validation_status':'source_checked_demo'}}
        cs=list(await session.scalars(select(RubricCriterion).where(RubricCriterion.rubric_id==r.id).order_by(RubricCriterion.criterion_order)))
        for c,spec in zip(cs,q['criteria'],strict=True):
            c.external_id=spec['criterion_id']
            c.import_metadata={**c.import_metadata,'scoring_rule':SCORING,'source_review':REVIEW}
        await session.flush()
        await publish(session,entity,account,review=REVIEW)
        return dict(original_ids=q['original_ids'],question_id=entity.external_id,version=entity.bank_version,
                    package_hash=entity.import_metadata['approved_package']['sha256'],action='created')

    # Validate every record through real application validators, then roll back.
    if '--validate-only' in sys.argv:
        async with SessionFactory() as session:
            async with session.begin():
                for q in records: results.append(await materialize(session,q))
                await session.rollback()
        write('preflight.json',dict(validated=len(results),committed=False,model_calls=0))
    else:
        # Per-question atomicity: a failure cannot leave a partial question published.
        for q in records:
            async with SessionFactory() as session,session.begin():
                results.append(await materialize(session,q))
            write('import-progress.json',results)
        name='import-rerun.json' if all(x['action']=='unchanged' for x in results) else 'import-manifest.json'
        write(name,dict(batch='bank-expansion-20261116',records=results,model_calls=0,review=REVIEW))
        write('crosswalk.json',results)
    print(dict(count=len(results),created=sum(x['action']=='created' for x in results),unchanged=sum(x['action']=='unchanged' for x in results),validate_only='--validate-only' in sys.argv))

if __name__=='__main__':
    if '--inside' in sys.argv: asyncio.run(run())
    else: inside('import_bank', *sys.argv[1:])
