"""Read text PDFs or structured JSON/JSONL; optionally accept an external OCR function."""
import hashlib
import json
from pathlib import Path
import unicodedata

from pypdf import PdfReader

from .common import fingerprint,read_json


def read_document(path,*,ocr_page=None,force_ocr=False,page_numbers=None):
    """ocr_page(pdf_path, page_number_1_based) -> str; OCR is not bundled.

    page_numbers optionally restricts PDF reading/OCR to original 1-based indices.
    It does not renumber pages or imply that the rest of the PDF was processed.
    """
    path=Path(path)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    manifest={'source_file':path.name,'source_sha256':digest,'unreadable_pages':[]}
    sections=[]
    if path.suffix.lower()=='.pdf':
        if force_ocr and ocr_page is None:raise ValueError('force_ocr requires an ocr_page callback')
        reader=PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(''):raise ValueError('PDF requires a password')
        manifest['page_count']=len(reader.pages)
        selected=set(range(1,len(reader.pages)+1)) if page_numbers is None else set(page_numbers)
        if not selected or any(type(n) is not int or not 1<=n<=len(reader.pages) for n in selected):
            raise ValueError('Invalid selected PDF pages')
        for number,page in enumerate(reader.pages,1):
            if number not in selected:continue
            text='' if force_ocr else page.extract_text() or ''
            method='pdf_text'
            if (force_ocr or not text.strip()) and ocr_page is not None:
                text=ocr_page(path,number);method='ocr'
                if not isinstance(text,str):raise ValueError('OCR callback must return text')
            if not text.strip():manifest['unreadable_pages'].append(number);continue
            sections.append({'source_file':path.name,'source_sha256':digest,'page_start':number,'page_end':number,
                             'read_method':method,'text':unicodedata.normalize('NFC',text)})
    elif path.suffix.lower() in ('.json','.jsonl'):
        if page_numbers is not None:raise ValueError('page_numbers applies to PDF inputs only')
        if force_ocr:raise ValueError('force_ocr applies to PDF inputs only')
        if path.suffix.lower()=='.jsonl':
            rows=[json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
        else:
            rows=read_json(path)
            if isinstance(rows,dict) and 'sections' in rows:
                manifest['unreadable_pages']=rows.get('unreadable_pages',[])
                rows=rows['sections']
            elif isinstance(rows,dict):rows=[rows]
        if not isinstance(rows,list):raise ValueError('JSON source must be a section, an array, or an object with sections')
        for number,row in enumerate(rows,1):
            if not isinstance(row,dict) or not isinstance(row.get('text'),str) or not row['text'].strip():
                raise ValueError(f'Invalid or empty text in section {number}')
            start,end=row.get('page_start'),row.get('page_end')
            if (start is None)!=(end is None) or start is not None and (
                    type(start) is not int or type(end) is not int or start<1 or end<start):
                raise ValueError(f'Invalid page range in section {number}')
            sections.append({'source_file':path.name,'source_sha256':digest,'page_start':None,'page_end':None,
                             'read_method':'structured_text',**row})
    else:
        raise ValueError('Supported inputs: .pdf, .json, .jsonl')
    # No fabricated text for unreadable pages. Caller can inspect these before extraction.
    return {**manifest,'sections':sections}


def text_parts(text,max_bytes):
    if max_bytes<4:raise ValueError('max_bytes must be at least 4')
    buffer=[];size=0
    for char in text:
        width=len(char.encode('utf-8'))
        if buffer and size+width>max_bytes:
            value=''.join(buffer);cut=value.rfind('\n')+1
            if cut<len(value)//2:cut=value.rfind(' ')+1
            if cut<len(value)//2:cut=len(value)
            yield value[:cut]
            buffer=list(value[cut:]);size=len(value[cut:].encode('utf-8'))
        buffer.append(char);size+=width
    if buffer:yield ''.join(buffer)


def chunk_sections(sections,max_bytes=6000):
    chunks=[]
    for section_number,section in enumerate(sections,1):
        metadata={key:value for key,value in section.items() if key not in ('text','chunk_id')}
        for part_number,text in enumerate(text_parts(section['text'],max_bytes),1):
            if not text.strip():continue
            value={**metadata,'section_index':section_number,'part_index':part_number,'text':text}
            chunks.append({'chunk_id':fingerprint(value)[:24],**value})
    return chunks
