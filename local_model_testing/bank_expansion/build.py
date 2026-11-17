import json
import re
from collections import Counter
from difflib import SequenceMatcher

from .common import ROOT, digest, read, sha, write
from .content import ITEMS, TOPICS

REVIEW = dict(actor='Codex', method='manual_source_comparison', date='2026-11-16',
              human_reviewed=False, clinician_approved=False, expert_verified=False,
              publication_scope='graduation_project_demo', authorization='User batch instruction f722aa54')
SCORING = ('Mỗi tiêu chí 1 điểm: cho đủ điểm khi trả lời đúng ý được mô tả, giữ đúng điều kiện và không phủ định chính ý đó; '
           '0 điểm nếu thiếu hoặc sai. Chấp nhận diễn đạt tương đương; không chấm bằng đối chiếu từ khóa. Cộng điểm các tiêu chí độc lập.')


def main():
    pages, catalog = read('source-pages.json'), read('source-catalog.json')
    # Visually checked original decision cover. The two files have identical bytes.
    moh = catalog['SRC_ORTHO_PROCEDURES_MOH_2017_001']
    moh.update(title='Hướng dẫn quy trình kỹ thuật Ngoại khoa, chuyên khoa Chấn thương chỉnh hình',
               year=2017, decision='5728/QĐ-BYT', decision_date='2017-12-21',
               url='https://kcb.vn/van-ban/quyet-dinh-so-5728-qd-byt-ngay-21-12-2017-ve-viec-ban-hanh-tai-lieu-huong-dan-quy-trinh-ky-thuat-ngoai-khoa-chuyen-khoa-.html',
               metadata_status='original_cover_and_official_kcb_entry_checked',
               applicability='62 quy trình; đơn vị xây dựng hướng dẫn phù hợp điều kiện theo quyết định; không xác nhận là bản hiện hành năm 2026',
               duplicate_aliases=['SRC_ORTHO_PROCEDURES_MOH_2014_001'])
    catalog.pop('SRC_ORTHO_PROCEDURES_MOH_2014_001')
    for s in catalog.values(): assert sha(ROOT/s['pdf_path']) == s['sha256']
    write('sources-verified.json',catalog)
    units, records, anchor_issues = {}, [], []

    def evidence(qid, ci, page, anchors, source='SRC_ORTHO_TEXTBOOK_001'):
        p = pages[source+':'+str(page)]
        lines = p['content'].splitlines()
        selected = []
        for anchor in anchors:
            # Keep adjacent list rows as context (e.g. a numeric table cell and
            # its label). Never infer a missing paragraph from a heading alone.
            positions = [i for i,line in enumerate(lines) if anchor.casefold() in line.casefold()]
            hits = [lines[j].strip() for i in positions for j in range(max(0,i-1),min(len(lines),i+2))]
            if not hits: anchor_issues.append(dict(question=qid, criterion=ci, page=page, anchor=anchor))
            selected.extend(hits)
        content = '\n'.join(dict.fromkeys(selected)) if anchors else p['content'].strip()
        if not content: content = '[UNRESOLVED]'
        sid='QB26_SU_'+digest(dict(source=source,page=page,content=content))[:24]
        units[sid] = dict(source_unit_id=sid, source_id=source, title=f'{catalog[source]["title"]} — PDF {page}',
                          content=content,pdf_page_start=page,pdf_page_end=page,
                          content_sha256=__import__('hashlib').sha256(content.encode()).hexdigest(),
                          page_text_sha256=p['text_version_sha256'],source_sha256=catalog[source]['sha256'],
                          locator=f'PDF page {page}; paragraph anchors: '+', '.join(anchors),review=REVIEW)
        return sid

    qs=[json.loads(l) for l in (ROOT/'data/processed/qa_items.jsonl').read_text(encoding='utf-8').splitlines()]
    rubrics={r['question_id']:r for r in [json.loads(l) for l in (ROOT/'data/processed/rubrics.jsonl').read_text(encoding='utf-8').splitlines()]}
    a_pages={2:[67],3:[67,68],5:[72],7:[73,74],8:[74],9:[75],10:[76],11:[77],12:[69,70],13:[7],14:[7],15:[8]}
    dispositions=[]
    held={4:'Mốc thời gian nhiễm khuẩn theo Friedrich có nguy cơ bị hiểu là quy tắc điều trị hiện hành; cần biên tập chuyên môn riêng.',
          6:'Nội dung rửa vết thương/ga rô cần đối chiếu hướng dẫn cấp cứu cập nhật, không phát hành nguyên văn chỉ để tăng số lượng.',
          16:'Tình huống không thêm tiêu chí mới so với Q0013 và Q0014; không đếm lại.',
          17:'Trùng phạm vi đánh giá mô sâu, mạch thần kinh và hình ảnh của Q0003/Q0005.',
          18:'Câu tổng hợp lặp lại các tiêu chí Q0006/Q0007/Q0010/Q0011, không tính thêm câu độc lập.'}
    for i,q in enumerate(qs,1):
        if i==1:
            dispositions.append(dict(id=q['question_id'],status='existing_preserved',reason='Đã có trên web; giữ nguyên.'))
            continue
        if i in held:
            dispositions.append(dict(id=q['question_id'],status='review' if i in (4,6) else 'excluded_duplicate',reason=held[i]))
            continue
        source='SRC_ORTHO_PROCEDURES_MOH_2017_001' if i>=13 else 'SRC_ORTHO_TEXTBOOK_001'
        criteria=[]
        for j,c in enumerate(rubrics[q['question_id']]['criteria'],1):
            criteria.append(dict(criterion_id=q['question_id']+f'_C{j:02}',description=c['description'],max_score=1.0,
                                 source_unit_ids=[evidence(q['question_id'],j,p,[],source) for p in a_pages[i]], scoring_rule=SCORING))
        scope='quy trình Bộ Y tế, Quyết định 5728/QĐ-BYT (2017)' if i>=13 else 'Bệnh học ngoại khoa – Chấn thương chỉnh hình (2021)'
        question=q['question'].replace('trong pilot','trong tài liệu').replace('các source unit đã xác nhận','giáo trình').replace('source unit đã xác nhận','giáo trình').replace('trong nguồn','trong tài liệu')
        answer=q['reference_answer']
        if i==7: answer+=' Khi mở rộng cần tránh vùng da ngay trên xương và tránh cắt ngang nếp gấp khớp.'
        records.append(dict(question_id=q['question_id'],topic='open',objective=f'processed-{i:02}',
            question=f'Theo {scope}, {question[0].lower()+question[1:]}',reference_answer=answer,
            criteria=criteria,max_score=float(len(criteria)),source_type='existing_qa_completed',original_ids=[q['question_id']],review=REVIEW))
        dispositions.append(dict(id=q['question_id'],status='ready',reason='Codex đối chiếu trực tiếp chương gãy hở 2021 hoặc quy trình gốc 2017; hiệu chỉnh nhãn nguồn, bổ sung ý thiếu trong đáp án Q0007.'))
    write('qa18-disposition.json',dispositions)
    candidates=read('book-question-candidates.json')
    for n,item in enumerate(ITEMS,1):
        qid=f'QB26_{item["topic"].upper()}_{item["objective"].upper().replace("-","_")}'
        criteria=[]
        for j,(text,refs) in enumerate(item['criteria'],1):
            ids=[]
            for page,anchors in refs:
                sid='SRC_ORTHO_EMERGENCY_001' if item['objective']=='graft-flap' else 'SRC_ORTHO_TEXTBOOK_001'
                ids.append(evidence(qid,j,page,anchors,sid))
            criteria.append(dict(criterion_id=qid+f'_C{j:02}',description=text,max_score=1.0,source_unit_ids=list(dict.fromkeys(ids)),scoring_rule=SCORING))
        original_titles={
            'stabilizers':'Trình bày đặc điểm giải phẫu các hệ thống giữ khớp vai?',
            'mechanism-pathology':'Trình bày cơ chế chấn thương và tổn thương giải phẫu bệnh trong trật khớp khuỷu?',
            'classification':'Trình bày phân loại trật khớp khuỷu?',
            'clinical-xray-diagnosis':'Trình bày chẩn đoán trật khớp khuỷu?',
            'clinical-radiographic':'Trình bày các triệu chứng lâm sàng và X quang gãy hai xương cẳng tay?',
        }
        title=original_titles.get(item['objective'])
        matches=[c for c in candidates if title and title in c.get('title','')]
        if title: assert len(matches)==1, (title,len(matches))
        book=matches[0] if matches else None
        # Only exact end-of-chapter questions are counted as completed originals.
        original = bool(book and item['objective'] != 'perfusion-mechanism')
        records.append(dict(question_id=qid,topic=item['topic'],objective=item['objective'],
            question=('Theo Cấp cứu ngoại khoa – Chấn thương (2006), ' if item['objective']=='graft-flap' else 'Theo Bệnh học ngoại khoa – Chấn thương chỉnh hình (2021), ')+item['question'][0].lower()+item['question'][1:],
            reference_answer='\n'.join(c['description'] for c in criteria),criteria=criteria,max_score=float(len(criteria)),
            source_type='book_question_completed' if original else 'authored_from_source',original_ids=[book['id']] if book else [],review=REVIEW))
    for c in candidates:
        matching=[q for q in records if c['id'] in q['original_ids']]
        c['batch_disposition']='completed' if any(q['source_type']=='book_question_completed' for q in matching) else 'adapted_narrower' if matching else 'review_not_completed'
        c['batch_question_ids']=[q['question_id'] for q in matching]
        c['batch_reason']='Câu gốc đã có đáp án/rubric/evidence' if c['batch_disposition']=='completed' else 'Chưa biên soạn đầy đủ phạm vi câu gốc trong batch này; không được tính là câu đã hoàn thiện.'
    write('book-candidates-disposition.json',candidates)
    exact=Counter(re.sub(r'\W+',' ',q['question'].casefold()) for q in records)
    assert max(exact.values())==1 and len({q['question_id'] for q in records})==len(records)
    near=[]
    for i,a in enumerate(records):
        for b in records[i+1:]:
            ratio=SequenceMatcher(None,a['reference_answer'],b['reference_answer']).ratio()
            if ratio>.66: near.append(dict(a=a['question_id'],b=b['question_id'],similarity=ratio,decision='distinct_objectives',reason='So sánh tiêu chí và điều kiện; không tự merge theo tương đồng.'))
    write('dedup-review.json',near)
    write('anchor-issues.json',anchor_issues)
    write('authored-questions.json',records)
    write('source-units.json',list(units.values()))
    print(json.dumps(dict(records=len(records),topics=dict(Counter(q['topic'] for q in records)),units=len(units),anchor_issues=anchor_issues),ensure_ascii=True))

if __name__=='__main__': main()
