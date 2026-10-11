#!/usr/bin/env python3
import argparse, json, re, sys
from pathlib import Path
from collections import defaultdict, Counter

REQUIRED_INPUT={"schema_version","question","student_answer","medical_evaluation","learner_context","metadata"}
REQUIRED_MED={"correct_points","incorrect_points","missing_points","rubric_scores","total_score","max_score","sufficient_evidence","evidence_refs"}
REQUIRED_OUTPUT={"strengths","corrections","missing_focus","learning_priority","feedback_text","follow_up_question"}
REQUIRED_META={"specialty","course_group","course_id","course_name","specialty_level","topic_id","topic_name","concept_ids"}
REQUIRED_LC={"mastery","recurring_errors","recent_improvements","recent_attempts_summary"}
LOCKED_MEDICAL_TEST_QIDS={"0002","0009"}
ALLOWED_PRIORITY={"high","medium","low"}
STOP=set("ban da dang duoc theo trong mot nhung va la cua co can nay do voi ve cho khi de o neu tu se thi nguoi hoc medical evaluation criterion criteria y noi dung diem cau tra loi phan hien tai".split())

def read_jsonl(path):
    rows=[]
    for i,line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(),1):
        if not line.strip(): continue
        try: rows.append(json.loads(line))
        except Exception as e: raise ValueError(f"{path}:{i}: invalid JSON: {e}")
    return rows

def norm(s):
    s=str(s or '').lower()
    s=re.sub(r'[^0-9a-zà-ỹđ]+',' ',s)
    return ' '.join(s.split())

def toks(s):
    return {t for t in norm(s).split() if len(t)>=3 and t not in STOP}

def sim(a,b):
    A,B=toks(a),toks(b)
    if not A or not B:return 0.0
    return len(A&B)/max(1,min(len(A),len(B)))

def sample_med_id(sid):
    m=re.match(r'^TEACH_(MED_\d{4}_\d{2})_V\d{2}$',sid)
    return m.group(1) if m else None

def qnum_from_sid(sid):
    m=re.match(r'^TEACH_MED_(\d{4})_\d{2}_V\d{2}$',sid)
    return m.group(1) if m else None

def add(errs,layer,split,sid,msg): errs.append({'layer':layer,'split':split,'sample_id':sid,'message':msg})
def is_str_list(x): return isinstance(x,list) and all(isinstance(v,str) for v in x)
def has_context(lc): return bool(lc.get('mastery') or lc.get('recurring_errors') or lc.get('recent_improvements') or lc.get('recent_attempts_summary'))

def factual_anchors(m):
    a=list(m['correct_points'])+list(m['incorrect_points'])+list(m['missing_points'])
    for r in m['rubric_scores']:
        a.extend([r.get('criterion',''),r.get('reason','')])
    return [x for x in a if x]

def anchor_ok(text,anchors,threshold=.42):
    n=norm(text)
    if not n:return True
    generic=('medical evaluation','tiêu chí','ý này','nội dung này','câu trả lời','ôn lại','ưu tiên','chưa nêu','chưa thể hiện','tự kiểm tra','lần trả lời','learner context','learner_context','mastery','lặp lại','cải thiện')
    if any(g in n for g in generic) and len(toks(text))<8:return True
    return max((sim(text,a) for a in anchors),default=0.0)>=threshold

def walk_keys(obj):
    if isinstance(obj,dict):
        for k,v in obj.items():
            yield k; yield from walk_keys(v)
    elif isinstance(obj,list):
        for v in obj: yield from walk_keys(v)

def main():
    ap=argparse.ArgumentParser(description='Deterministic Teaching dataset validator v1')
    ap.add_argument('--data-dir',default=str(Path(__file__).resolve().parent))
    ap.add_argument('--report-json',default=None)
    args=ap.parse_args(); d=Path(args.data_dir)
    files={'train':d/'teaching_train.jsonl','validation':d/'teaching_validation.jsonl','test':d/'teaching_test.jsonl'}
    errors=[]; rows={}
    for split,p in files.items():
        try: rows[split]=read_jsonl(p)
        except Exception as e: add(errors,'V1',split,'<file>',str(e)); rows[split]=[]

    # Cross-check against Medical train+validation only. medical_test.jsonl is intentionally never loaded.
    med_ref={}
    for p in [d/'medical_train.jsonl',d/'medical_validation.jsonl']:
        if p.exists():
            for x in read_jsonl(p): med_ref[x['sample_id']]=x

    # V1 schema validity
    for split,xs in rows.items():
        for x in xs:
            sid=x.get('sample_id','<missing>')
            if set(x.keys())!={'sample_id','input','gold_output'}: add(errors,'V1',split,sid,'top-level keys must be sample_id,input,gold_output')
            inp=x.get('input'); out=x.get('gold_output')
            if not isinstance(inp,dict): add(errors,'V1',split,sid,'input must be object'); continue
            if not REQUIRED_INPUT.issubset(inp): add(errors,'V1',split,sid,f'missing input keys: {sorted(REQUIRED_INPUT-set(inp))}')
            m=inp.get('medical_evaluation',{})
            if not isinstance(m,dict) or not REQUIRED_MED.issubset(m): add(errors,'V1',split,sid,'medical_evaluation schema invalid')
            lc=inp.get('learner_context',{})
            if not isinstance(lc,dict) or not REQUIRED_LC.issubset(lc): add(errors,'V1',split,sid,'learner_context schema invalid')
            meta=inp.get('metadata',{})
            if not isinstance(meta,dict) or not REQUIRED_META.issubset(meta): add(errors,'V1',split,sid,'metadata schema invalid')
            else:
                if meta.get('course_group') is not None: add(errors,'V1',split,sid,'course_group must be null until official taxonomy exists')
                if meta.get('specialty_level') is not None: add(errors,'V1',split,sid,'specialty_level must be null until official taxonomy exists')
                if meta.get('topic_id') in set(meta.get('concept_ids') or []): add(errors,'V1',split,sid,'topic_id must not be reused as concept_id')
            if not isinstance(out,dict) or not REQUIRED_OUTPUT.issubset(out): add(errors,'V1',split,sid,'gold_output schema invalid')

    # V2 output completeness
    for split,xs in rows.items():
        for x in xs:
            sid=x['sample_id']; out=x['gold_output']
            if not is_str_list(out.get('strengths')): add(errors,'V2',split,sid,'strengths must be list[str]')
            for key,req in [('corrections',{'incorrect_point','feedback'}),('missing_focus',{'missing_point','feedback'}),('learning_priority',{'focus','priority','reason'})]:
                arr=out.get(key)
                if not isinstance(arr,list): add(errors,'V2',split,sid,f'{key} must be list'); continue
                for i,c in enumerate(arr):
                    if not isinstance(c,dict) or not req.issubset(c): add(errors,'V2',split,sid,f'{key}[{i}] incomplete'); continue
                    if key=='learning_priority' and c.get('priority') not in ALLOWED_PRIORITY: add(errors,'V2',split,sid,f'{key}[{i}] priority invalid')
                    if not str(c.get('feedback',c.get('reason',''))).strip(): add(errors,'V2',split,sid,f'{key}[{i}] text empty')
            if not isinstance(out.get('feedback_text'),str) or not out['feedback_text'].strip(): add(errors,'V2',split,sid,'feedback_text must be non-empty string')
            if out.get('follow_up_question') is not None and not isinstance(out.get('follow_up_question'),str): add(errors,'V2',split,sid,'follow_up_question must be string|null')

    # V3 Medical/Teaching consistency
    for split,xs in rows.items():
        for x in xs:
            sid=x['sample_id']; m=x['input']['medical_evaluation']; out=x['gold_output']
            if Counter(c.get('incorrect_point') for c in out['corrections'])!=Counter(m['incorrect_points']): add(errors,'V3',split,sid,'corrections must map 1:1 to incorrect_points')
            if Counter(c.get('missing_point') for c in out['missing_focus'])!=Counter(m['missing_points']): add(errors,'V3',split,sid,'missing_focus must map 1:1 to missing_points')
            if len(out['strengths'])!=len(m['correct_points']): add(errors,'V3',split,sid,'strength count must equal correct_points count')
            else:
                unmatched=list(m['correct_points'])
                for st in out['strengths']:
                    if not unmatched: break
                    best=max(range(len(unmatched)),key=lambda i:sim(st,unmatched[i]))
                    if sim(st,unmatched[best])<.45: add(errors,'V3',split,sid,f'strength not anchored: {st}')
                    else: unmatched.pop(best)

    # V4 score immutability + exact source Medical alignment
    forbidden={'score','total_score','max_score','rubric_scores'}
    for split,xs in rows.items():
        for x in xs:
            sid=x['sample_id']; m=x['input']['medical_evaluation']; out=x['gold_output']
            if m['total_score']!=sum(r.get('score',0) for r in m['rubric_scores']): add(errors,'V4',split,sid,'medical total_score != sum rubric_scores')
            if m['max_score']!=sum(r.get('max_score',0) for r in m['rubric_scores']): add(errors,'V4',split,sid,'medical max_score != sum rubric max_score')
            if forbidden & set(walk_keys(out)): add(errors,'V4',split,sid,'Teaching output must not contain score fields')
            mid=sample_med_id(sid)
            if mid not in med_ref: add(errors,'V4',split,sid,'source Medical sample absent from medical_train/medical_validation; medical_test is intentionally excluded')
            else:
                r=med_ref[mid]
                if x['input']['question']!=r['question']: add(errors,'V4',split,sid,'question differs from source Medical sample')
                if sid.endswith('_V01') and x['input']['student_answer']!=r['student_answer']: add(errors,'V4',split,sid,'V01 student_answer differs from source Medical sample')
                if m!=r['gold_output']: add(errors,'V4',split,sid,'medical_evaluation differs from immutable source Medical gold_output')

    # V5 learner-context influence
    by_case=defaultdict(list)
    for split,xs in rows.items():
        for x in xs: by_case[sample_med_id(x['sample_id'])].append((split,x))
    for mid,group in by_case.items():
        if len(group)>1:
            med0=group[0][1]['input']['medical_evaluation']
            for split,x in group[1:]:
                if x['input']['medical_evaluation']!=med0: add(errors,'V5',split,x['sample_id'],'learner-context variant changed medical_evaluation')
    for split,xs in rows.items():
        for x in xs:
            sid=x['sample_id']; lc=x['input']['learner_context']; out=x['gold_output']
            blob=norm(out['feedback_text']+' '+' '.join(p.get('reason','') for p in out['learning_priority']))
            if has_context(lc):
                if not out['learning_priority'] and (x['input']['medical_evaluation']['incorrect_points'] or x['input']['medical_evaluation']['missing_points']): add(errors,'V5',split,sid,'non-empty learner_context must influence learning_priority when remediation exists')
                if lc.get('recurring_errors') and 'lặp' not in blob: add(errors,'V5',split,sid,'recurring_errors present but recurrence not reflected')
                if lc.get('recent_improvements') and 'cải thiện' not in blob: add(errors,'V5',split,sid,'recent_improvements present but improvement not reflected')
                levels={i.get('level') for i in lc.get('mastery',[]) if isinstance(i,dict)}
                if levels & {'low','high'} and not lc.get('recurring_errors') and not lc.get('recent_improvements') and 'mastery' not in blob: add(errors,'V5',split,sid,'low/high mastery present but not reflected')

    # V6 rule-based no-hallucination anchor checks
    for split,xs in rows.items():
        for x in xs:
            sid=x['sample_id']; m=x['input']['medical_evaluation']; out=x['gold_output']; anchors=factual_anchors(m)
            for st in out['strengths']:
                if not anchor_ok(st,m['correct_points'],.45): add(errors,'V6',split,sid,f'unanchored strength: {st}')
            for c in out['corrections']:
                if not anchor_ok(c['feedback'],anchors,.35): add(errors,'V6',split,sid,f'unanchored correction feedback: {c["feedback"]}')
            for c in out['missing_focus']:
                if not anchor_ok(c['feedback'],anchors,.30): add(errors,'V6',split,sid,f'unanchored missing feedback: {c["feedback"]}')
            fq=out.get('follow_up_question')
            if fq and not anchor_ok(fq,anchors,.30): add(errors,'V6',split,sid,f'unanchored follow_up_question: {fq}')
            if not m['sufficient_evidence'] and len(out['corrections'])!=len(m['incorrect_points']): add(errors,'V6',split,sid,'insufficient-evidence sample adds unsupported correction')

    # V7 split leakage + locked Medical test exclusion
    qsets={}; casesets={}
    for split,xs in rows.items():
        qsets[split]={qnum_from_sid(x['sample_id']) for x in xs}
        casesets[split]={sample_med_id(x['sample_id']) for x in xs}
        for x in xs:
            q=qnum_from_sid(x['sample_id'])
            if q in LOCKED_MEDICAL_TEST_QIDS: add(errors,'V7',split,x['sample_id'],f'locked Medical test Q_{q} forbidden')
    for a,b in [('train','validation'),('train','test'),('validation','test')]:
        for q in sorted(qsets[a]&qsets[b]): add(errors,'V7',f'{a}<->{b}',f'Q_{q}',f'question leakage Q_{q}')
        for c in sorted(casesets[a]&casesets[b]): add(errors,'V7',f'{a}<->{b}',c,f'case leakage {c}')

    counts=Counter(e['layer'] for e in errors)
    print('=== Teaching Dataset Validator v1 ===')
    print('Policy: deterministic rule-based; medical_test.jsonl is never loaded.')
    print('Test split: dataset schema/invariant/leakage checks only; no model-selection metric.')
    for v in [f'V{i}' for i in range(1,8)]: print(f'{v}: '+('PASS' if counts[v]==0 else f'FAIL ({counts[v]})'))
    print('OVERALL: '+('PASS' if not errors else f'FAIL ({len(errors)} errors)'))
    if errors:
        print('\nErrors:')
        for e in errors: print(f"- [{e['layer']}] {e['split']} {e['sample_id']}: {e['message']}")
    if args.report_json:
        Path(args.report_json).write_text(json.dumps({'overall':'PASS' if not errors else 'FAIL','layers':{f'V{i}':('PASS' if counts[f'V{i}']==0 else 'FAIL') for i in range(1,8)},'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if not errors else 1

if __name__=='__main__': sys.exit(main())
