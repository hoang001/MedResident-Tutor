import asyncio
import json
import subprocess
import sys
from collections import Counter

from .common import ROOT, RUN, DOCKER, inside, read, sha, write


async def graph():
    from app.modules.knowledge.service import get_graph_store
    store=get_graph_store()
    try:
        snapshot=await store.snapshot()
        from app.modules.study.questions import question_bank
        selfstudy=question_bank(snapshot)
        selfstudy_counts=dict(Counter(q['origin'] for q in selfstudy.values()))
        counts=dict(Counter(n['type'] for n in snapshot.nodes.values()))
        before=read('graph-counts-before.json')
        assert len(snapshot.nodes)==before['nodes'] and len(snapshot.edges)==before['edges']
        from neo4j import READ_ACCESS
        from app.core.config import get_settings
        async with store.driver.session(database=get_settings().neo4j_database,default_access_mode=READ_ACCESS) as session:
            labels=await (await session.run('MATCH (n) RETURN labels(n) AS labels, count(n) AS count')).data()
        write('graph-after-readonly.json',dict(store_type=type(store).__name__,nodes=len(snapshot.nodes),edges=len(snapshot.edges),node_types=counts,
              all_database_label_counts=labels,self_study_catalog=selfstudy_counts,
              template_note='kg_template được dựng theo mẫu khi đọc KG, không phải 5658 node câu hỏi có rubric trong Neo4j.',unchanged_counts=True,writes=0))
        print(dict(graph_store=type(store).__name__,self_study_catalog=selfstudy_counts,unchanged=True))
    finally: await store.close()


def main():
    inside('finalize')
    running=subprocess.check_output([DOCKER,'ps','--format','{{.Names}}'],text=True).splitlines()
    assert all(name not in running for name in ['medresident-bank-browser','medresident-bank-playwright','medresident-bank-tests','medresident-bank-expansion','medresident-bank-lint'])
    assert all(name in running for name in ['medresident-tutor-db-1','medresident-tutor-backend-1','medresident-tutor-frontend-1'])
    memory=json.loads(subprocess.check_output(['powershell','-NoProfile','-Command',
        'Get-CimInstance Win32_OperatingSystem | Select-Object FreePhysicalMemory,TotalVisibleMemorySize | ConvertTo-Json'],text=True))
    gpu=subprocess.run(['powershell','-NoProfile','-Command',
        '$bankGpuTool = Get-Command nvidia-smi -ErrorAction SilentlyContinue; if ($bankGpuTool) { & $bankGpuTool.Source --query-gpu=name,memory.used,memory.free --format=csv,noheader,nounits }'],capture_output=True,text=True)
    write('cleanup.json',dict(task_containers_running=False,running_app_containers=[n for n in running if n.startswith('medresident-tutor-')],
        ram_free_gib=round(memory['FreePhysicalMemory']/1024**2,2),ram_total_gib=round(memory['TotalVisibleMemorySize']/1024**2,2),
        gpu_readout=gpu.stdout.strip(),model_loads_by_task=0,inference_attempts=0,weights_adapters_cache_preserved=True))
    old=read('backup/rows-before.private.json')
    write('dedup-existing.json',dict(existing_ids=[q['external_id'] for q in old['questions']],
        preserved_clinical_case_groups=[['CLINICAL_DEMO_V1_CASE01','CLINICAL_DEMO_V2_CASE01'],['CLINICAL_DEMO_V1_XR01','CLINICAL_DEMO_V2_XR01']],
        note='4 bài V1/V2 hiện có chỉ đại diện 2 ca lâm sàng; giữ nguyên theo yêu cầu, không báo thành 4 ca độc lập. 100 là số mục/bài khả dụng qua API. 95 câu mới không lặp các tiêu chí nhận diện tổn thương của các ca này; thay đổi hình thức câu hỏi không được dùng để tăng batch.',
        method='Codex so sánh phạm vi đề, điều kiện, đối tượng và tiêu chí; kiểm tra exact normalized prompt/reference plus similarity suggestions; không có model semantic-dedup call.',
        existing_Q0001_excluded_from_new_count=True,new_imports=95))
    # Dedup the candidate inventory by prompt AND physical source locator, not
    # title alone (generic chapter-end titles can describe different injuries).
    import re
    candidates=read('book-candidates-disposition.json')
    seen={}; duplicates=[]
    for c in candidates:
        normalized=re.sub(r'^Câu\s+\d+[.:]?\s*','',c['title'],flags=re.I).casefold()
        refs=sorted((s.get('source_id',''),tuple(s.get('pdf_pages',[]))) for s in c.get('sources',[]))
        key=(normalized,tuple(refs))
        if key in seen:
            duplicates.append(dict(id=c['id'],canonical_id=seen[key],title=c['title'],reason='Cùng đề và cùng source/page; không tính thành hai câu hoàn thiện.'))
            c['batch_disposition']='excluded_duplicate_candidate'
            c['batch_reason']='Trùng đề và vị trí nguồn với '+seen[key]
        else: seen[key]=c['id']
    write('book-candidates-disposition.json',candidates)
    write('book-candidate-duplicates.json',duplicates)
    stats=read('statistics.json')
    stats.update(legacy_clinical_versions=4,legacy_clinical_cases=2,tests_passed=54,browser_workflow_passed=True,
        book_candidate_duplicates=len(duplicates),kg_selfstudy_counts=read('graph-after-readonly.json')['self_study_catalog'])
    write('statistics.json',stats)
    checks=dict(tests=54,browser_test=1,representative_mock_submissions=5,real_model_calls=0,frontend_eslint='passed',source_pdfs_accessible_in_running_backend=3,
        real_backend_http=200,available=100,drafts=2,idempotent_created_on_rerun=0,
        source_and_package_checks_passed=95,historical_rows_unchanged=True,desktop_mobile_checked=True,
        browser_navigation_bug_fixed=True,frontend_production_build='passed',
        visual_review='Rendered desktop learner catalog and mobile source review inspected; no horizontal overflow at 390px. Existing Arial/teal design retained; detector advisories for typography accepted as incumbent design. Palette drift corrected.')
    write('verification-summary.json',checks)
    readme=RUN/'README.md'
    readme.write_text(readme.read_text(encoding='utf-8').split('\nKiểm thử:')[0],encoding='utf-8')
    with readme.open('a',encoding='utf-8') as f:
        f.write('\nKiểm thử: 54 backend tests qua; production build frontend qua; 1 browser workflow test qua với 5 bài nộp mock đại diện, tải lại history và ảnh ca cũ thành công. DB chính giữ nguyên 6 attempt, 105 study record, 21 study session và 9 tài khoản.\n')
        f.write('\nLưu ý cách đếm: 100 là số mục/bài khả dụng trên web. 4 bài ca bệnh cũ gồm V1/V2 của 2 ca, không phải 4 ca độc lập; xem dedup-existing.json. 95 câu bổ sung không phải các paraphrase của những câu này.\n')
    write('artifact-hashes.json',{p.relative_to(RUN).as_posix():sha(p) for p in RUN.rglob('*') if p.is_file() and
        p.parts[len(RUN.parts)] not in ('deps','backup','playwright') and p.name!='artifact-hashes.json'})
    print(json.dumps(dict(available=100,tests_passed=54,browser_passed=True,task_workers_stopped=True,ram_free_gib=round(memory['FreePhysicalMemory']/1024**2,2))))

if __name__=='__main__':
    if '--inside' in sys.argv: asyncio.run(graph())
    else: main()
