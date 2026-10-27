"""Reusable document -> chunks -> JSON extraction -> optional review -> export."""
from contextlib import ExitStack
import json
from pathlib import Path

from .checkpoint import Checkpoint,CachedLLM
from .common import fingerprint,write_json
from .documents import read_document,chunk_sections
from .llm_client import LLMClient,LLMError


def extract_document(input_path,output_path,*,settings,prompt,schema,judge_prompt=None,judge_schema=None,
                     resume=False,force=False,max_chunk_bytes=6000,ocr_page=None,force_ocr=False,client=None,
                     validator=None,validator_version='',ocr_version=''):
    """validator(result, chunk) raises ValueError on unsupported domain-specific output.

    Use your own prompt/schema; original text and source metadata stay outside LLM output.
    Change validator_version/ocr_version when changing those external implementations.
    """
    input_path,output_path=Path(input_path),Path(output_path)
    checkpoint_path=output_path.with_suffix('.checkpoint.json')
    if input_path.resolve() in (output_path.resolve(),checkpoint_path.resolve()):
        raise ValueError('Output/checkpoint must not overwrite the input document')
    if output_path.exists() and not (resume or force):
        raise ValueError('Output exists; use --continue, --force or another output')
    if not settings.model:raise ValueError('Set LLM_MODEL for extraction')
    if validator is not None and not validator_version:raise ValueError('Set validator_version when providing a validator')
    if ocr_page is not None and not ocr_version:raise ValueError('Set ocr_version when providing an OCR implementation')
    # Validate schemas BEFORE any paid requests.
    from jsonschema import Draft202012Validator
    Draft202012Validator.check_schema(schema)
    if judge_schema is not None:Draft202012Validator.check_schema(judge_schema)
    document=read_document(input_path,ocr_page=ocr_page,force_ocr=force_ocr)
    chunks=chunk_sections(document['sections'],max_chunk_bytes)
    if not chunks:raise ValueError('No readable text. Inspect unreadable_pages or provide an OCR callback first.')
    source_files=[Path(__file__).parent/name for name in ('pipeline.py','documents.py','checkpoint.py','llm_client.py','common.py','config.py')]
    signature=fingerprint([document,prompt,schema,judge_prompt,judge_schema,max_chunk_bytes,validator_version,ocr_version,
        settings.model,settings.judge_model,settings.llm_base_url,settings.llm_chat_completions_endpoint,
        settings.prompt_budget_bytes,settings.max_output_tokens,[path.read_text(encoding='utf-8') for path in source_files]])
    checkpoint=Checkpoint(checkpoint_path,signature,resume=resume,force=force)
    checkpoint.data['complete']=False;checkpoint.save()
    results=[];failures=[];interrupted=False
    with ExitStack() as stack:
        raw_client=client or stack.enter_context(LLMClient(settings))
        cached=CachedLLM(raw_client,checkpoint,namespace=settings.endpoint_url(settings.llm_chat_completions_endpoint))
        try:
            for index,chunk in enumerate(chunks):
                checkpoint.data['position']={'chunk_index':index,'chunk_id':chunk['chunk_id'],'stage':'extract'}
                checkpoint.save()
                try:
                    validate_result=(lambda result:validator(result,chunk)) if validator is not None else None
                    value=cached.chat_json(settings.model,[{'role':'system','content':prompt},
                        {'role':'user','content':json.dumps({'source':chunk},ensure_ascii=False)}],schema,
                        validator=validate_result if not judge_prompt else None)
                    if judge_prompt:
                        checkpoint.data['position']['stage']='judge';checkpoint.save()
                        value=cached.chat_json(settings.judge_model or settings.model,[{'role':'system','content':judge_prompt},
                            {'role':'user','content':json.dumps({'source':chunk,'candidates':value},ensure_ascii=False)}],
                            judge_schema if judge_schema is not None else schema,validator=validate_result)
                    results.append({'chunk_id':chunk['chunk_id'],
                        'source':{key:value for key,value in chunk.items() if key!='text'},'extraction':value})
                except Exception as exc:
                    # Failed calls are not treated as completed chunks. Stop and resume later.
                    failures.append({'chunk_id':chunk['chunk_id'],'stage':checkpoint.data['position']['stage'],
                        'error':str(exc) if isinstance(exc,(ValueError,LLMError)) else type(exc).__name__})
                    break
        except KeyboardInterrupt:
            interrupted=True
    complete=len(results)==len(chunks) and not document['unreadable_pages'] and not failures and not interrupted
    result={'status':'complete' if complete else 'partial','source_file':document['source_file'],
            'source_sha256':document['source_sha256'],'total_chunks':len(chunks),'completed_chunks':len(results),
            'unreadable_pages':document['unreadable_pages'],'failures':failures,'results':results}
    write_json(output_path,result)
    checkpoint.data['complete']=complete;checkpoint.save()
    if interrupted:raise KeyboardInterrupt
    return result
