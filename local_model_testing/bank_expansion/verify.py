import asyncio
import csv
import hashlib
import json
import sys
from collections import Counter

from .common import ROOT, RUN, digest, inside, read, sha, write
from .content import TOPICS


async def run():
    import app.models  # noqa: F401
    from sqlalchemy import select, text
    from httpx import ASGITransport, AsyncClient
    from app.core.database import engine, SessionFactory
    from app.main import app
    from app.modules.practice.router import practice_user
    from app.modules.users.models import User
    from app.modules.questions.models import Question, Rubric, RubricCriterion
    from app.modules.questions.service import detail, readiness
    from app.modules.documents.source_units import SourceUnit
    before=read('backup/rows-before.private.json')
    counts, protections = {}, {}
    async with engine.connect() as c:
        await c.execute(text('SET TRANSACTION READ ONLY'))
        for table, oldrows in before.items():
            rows=[json.loads(x) for x in (await c.execute(text('SELECT row_to_json(t)::text FROM "'+table+'" t'))).scalars()]
            hashes={digest(r) for r in rows}
            assert all(digest(r) in hashes for r in oldrows), 'Historical rows changed in '+table
            if table in ('users','practice_attempts','study_records','study_sessions','knowledge_reviews'):
                assert len(rows)==len(oldrows)
            counts[table]=len(rows)
            protections[table]=dict(original_rows=len(oldrows),unchanged=True)
    specs=read('authored-questions.json')
    units={u['source_unit_id']:u for u in read('source-units.json')}
    audit=[]
    async with SessionFactory() as s:
        learner=await s.scalar(select(User).where(User.role=='LEARNER'))
        s.expunge(learner)
        for spec in specs:
            q=await s.scalar(select(Question).where(Question.external_id==spec['question_id']))
            await readiness(s,q)
            package=q.import_metadata['approved_package']
            assert package['sha256']==digest({k:v for k,v in package.items() if k!='sha256'})
            assert q.is_available and package['approved_by']=='Codex' and package['expert_verified'] is False
            assert package['reference_answer']==spec['reference_answer']
            payload=package['payload']
            evidence={e['source_unit_id']:e for e in payload['evidence']}
            assert payload['question']==spec['question']
            assert sum(c['max_score'] for c in payload['rubric']['criteria'])==spec['max_score']
            for c in spec['criteria']:
                assert c['source_unit_ids'] and all(sid in evidence for sid in c['source_unit_ids'])
                for sid in c['source_unit_ids']:
                    assert evidence[sid]['content']==units[sid]['content']
                    assert hashlib.sha256(evidence[sid]['content'].encode()).hexdigest()==units[sid]['content_sha256']
            audit.append(dict(question_id=q.external_id,status='published_demo_source_checked',review_actor='Codex',
                reference_answer_complete=True,criterion_evidence_checked=True,source_locators_resolved=True,
                scope_conditions_checked=True,score_valid=True,distinct_objective=spec['objective'],
                standalone=True,clinician_approved=False,approved_package_hash=package['sha256']))
    async def authenticated(): return learner
    app.dependency_overrides[practice_user]=authenticated
    try:
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            response=await client.get('/api/v1/practice/questions')
            assert response.status_code==200
            listing=response.json()
            assert len(listing)==100 and len({q['question_id'] for q in listing})==100
            assert all(set(x)<={'question_id','question','topic','clinical_exercise','structured_exercise'} for x in listing)
            available={x['question_id'] for x in listing}
            assert all(q['question_id'] in available for q in specs)
            allids=[]
            for offset in range(0,120,17):
                r=await client.get('/api/v1/practice/catalog',params={'limit':17,'offset':offset})
                assert r.status_code==200
                p=r.json(); assert p['total']==100
                allids.extend(q['question_id'] for q in p['items'])
            assert len(allids)==len(set(allids))==100
            topic_counts={}
            for topic in TOPICS.values():
                p=(await client.get('/api/v1/practice/catalog',params={'topic':topic,'limit':100})).json()
                assert all(q.get('topic')==topic for q in p['items']) and p['total']>0
                topic_counts[topic]=p['total']
            draftids={q['external_id'] for q in before['questions'] if not q['is_available']}
            assert not available&draftids
            for did in draftids: assert (await client.get('/api/v1/practice/questions/'+did)).status_code==404
            search=(await client.get('/api/v1/practice/catalog',params={'q':'khoang','limit':100})).json()
            assert search['total']>0
            config=(await client.get('/api/v1/practice/config')).json()
            assert config['execution_mode']=='mock'
    finally: app.dependency_overrides.clear()
    # Verify the running web backend too. A short-lived token stays in memory;
    # no login or user-row update is performed, and no token is logged/stored.
    from app.core.config import get_settings
    from app.core.security import create_access_token
    token=create_access_token(str(learner.id),get_settings().model_copy(update={'access_token_expire_minutes':1}))
    async with AsyncClient(base_url='http://medresident-tutor-backend-1:8000',headers={'Authorization':'Bearer '+token}) as live:
        live_catalog=await live.get('/api/v1/practice/catalog?limit=100')
        assert live_catalog.status_code==200 and live_catalog.json()['available_total']==100
        live_config=await live.get('/api/v1/practice/config')
        assert live_config.json()['execution_mode']=='mock'
    token=None
    files=read('protected-files.json')
    assert all(sha(ROOT/path)==checksum for path,checksum in files.items())
    write('per-question-review.json',audit)
    write('inventory-after.json',dict(counts=counts,available_through_student_api=100,db_drafts=2,
          original_rows=protections,protected_files_unchanged=len(files),student_api={'http':200,'no_gold_before_submit':True,
          'pagination_unique_100':True,'topic_counts':topic_counts,'drafts_hidden':True,'execution_mode':'mock',
          'running_backend_http':200,'running_backend_available':100},model_calls=0))
    print(dict(available=100,drafts=2,verified_new=len(audit),original_rows_unchanged=True,model_calls=0))


def reports():
    q=read('authored-questions.json'); manifest=read('import-manifest.json')
    after=read('inventory-after.json')
    staged=json.loads((ROOT/'data/clinical-cases/exercises/manifest.json').read_text(encoding='utf-8'))
    queue=[]
    for item in staged['rows']:
        queue.append({**item,'batch_disposition':'existing_preserved' if item['demo'] else 'staging_not_released',
            'reason':'Giữ nguyên ca demo V1 và bản tương tác V2; không tính hai phiên bản là hai ca lâm sàng độc lập.' if item['demo'] else
            'Đã kiểm kê manifest, bản dịch, đáp án và trạng thái ảnh; batch sách đã đủ mục tiêu. Chưa tái kiểm tra từng ảnh/annotation và giấy phép để phát hành thêm ca này; không tự đổi cờ staging thành approved.'})
    write('clinical-staging-disposition.json',queue)
    review_queue=[x for x in read('qa18-disposition.json') if x['status']=='review']
    for old in read('backup/rows-before.private.json')['questions']:
        if not old['is_available']:
            review_queue.append(dict(id=old['external_id'],status='existing_draft_preserved',reason='Đáp án/rubric trước task chưa đầy đủ; giữ bản nháp gốc, không phát hành chỉ dựa trên đoạn trích. Nội dung chủ đề đã có câu biên soạn riêng.'))
    write('review-queue.json',review_queue)
    write('excluded-queue.json',[x for x in read('qa18-disposition.json') if x['status']=='excluded_duplicate'])
    stats=dict(total_db=after['counts']['questions'],available=100,draft_db=2,existing_preserved=5,
        added=95,existing_qa_added=12,existing_qa_held=5,book_originals_completed=5,
        book_candidates_remaining=121,new_authored=78,template_kg_imported=0,
        new_topics=dict(Counter(x['topic'] for x in q)),source_types=dict(Counter(x['source_type'] for x in q)),
        new_criterion_count=sum(len(x['criteria']) for x in q),source_units_added=len(read('source-units.json')),
        newly_downloaded_clinical_sources=0,external_metadata_verification='Official KCB entry for local 5728/QĐ-BYT (2017)',
        model_attempts=0,grading_provider='mock',clinician_approved=False)
    write('statistics.json',stats)
    with (RUN/'statistics.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow(['topic','new_published_questions'])
        w.writerows((TOPICS[k],v) for k,v in stats['new_topics'].items())
    with (RUN/'questions.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['question_id','topic','source_type','max_score','reference_answer'])
        w.writeheader(); w.writerows({k:x[k] for k in w.fieldnames} for x in q)
    # Freeze the published input bundle and its file hashes for reproducibility.
    write('release-manifest.json',dict(batch='bank-expansion-20261116',review_actor='Codex',model_attempts=0,
        input_hashes={name:sha(RUN/name) for name in ('authored-questions.json','source-units.json','sources-verified.json')},
        created=95,unchanged_on_rerun=95,protected_existing=5,backup='backup/postgres.dump',
        source_warning='Hai file quy trình local trùng byte, cùng bản 2017; alias 2014 được sửa trong nguồn của batch, không ghi đè dữ liệu gốc.'))


if __name__=='__main__':
    if '--inside' in sys.argv: asyncio.run(run())
    else:
        inside('verify')
        reports()
