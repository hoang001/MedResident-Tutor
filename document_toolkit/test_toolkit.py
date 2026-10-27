"""Offline tests for portability, provenance, retries and interrupted extraction."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import httpx

from .common import read_json, write_json
from .config import Settings
from .documents import read_document, text_parts
from .llm_client import LLMClient
from .pipeline import extract_document


SCHEMA = {'type': 'object', 'properties': {'value': {'type': 'string'}},
          'required': ['value'], 'additionalProperties': False}


class ToolkitTests(unittest.TestCase):
    def test_utf8_chunks_preserve_text_and_limit(self):
        text = ('S\u1eafp x\u1ebfp c\u00e1c s\u1ed1 \U0001f600\n' * 20)
        chunks = list(text_parts(text, 31))
        self.assertEqual(''.join(chunks), text)
        self.assertTrue(all(len(part.encode('utf-8')) <= 31 for part in chunks))

    def test_pdf_ocr_only_missing_pages_and_provenance(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'scan.pdf'
            source.write_bytes(b'pdf fixture; reader is mocked')
            reader = Mock(is_encrypted=False)
            reader.pages = [Mock(), Mock()]
            reader.pages[0].extract_text.return_value = 'page one'
            reader.pages[1].extract_text.return_value = ''
            ocr = Mock(return_value='page two')
            with patch('document_toolkit.documents.PdfReader', return_value=reader):
                incomplete = read_document(source)
                result = read_document(source, ocr_page=ocr)
            self.assertEqual(incomplete['unreadable_pages'], [2])
            self.assertEqual(result['unreadable_pages'], [])
            ocr.assert_called_once_with(source, 2)
            self.assertEqual(result['sections'][1]['page_start'], 2)
            self.assertEqual(result['sections'][1]['read_method'], 'ocr')
            self.assertEqual(result['sections'][0]['read_method'], 'pdf_text')

    def test_interrupt_then_resume_does_not_repeat_finished_calls(self):
        with TemporaryDirectory() as directory:
            source, target = Path(directory) / 'input.json', Path(directory) / 'out.json'
            write_json(source, [{'text': 'one', 'chapter': 'A'}, {'text': 'two'}])
            client = Mock()
            client.chat_json.side_effect = [{'value': 'first'}, KeyboardInterrupt()]
            arguments = dict(settings=Settings(model='fake'), prompt='extract', schema=SCHEMA)
            with self.assertRaises(KeyboardInterrupt):
                extract_document(source, target, client=client, **arguments)
            self.assertEqual(read_json(target)['completed_chunks'], 1)
            resumed_client = Mock()
            resumed_client.chat_json.return_value = {'value': 'second'}
            result = extract_document(source, target, client=resumed_client, resume=True, **arguments)
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(result['completed_chunks'], 2)
            resumed_client.chat_json.assert_called_once()
            self.assertEqual(result['results'][0]['source']['chapter'], 'A')
            self.assertEqual(result['results'][0]['extraction']['value'], 'first')
            with self.assertRaisesRegex(ValueError, 'changed'):
                extract_document(source, target, client=resumed_client, resume=True,
                                 **{**arguments, 'prompt': 'different'})

    def test_invalid_domain_result_is_not_cached(self):
        for judge in (None, 'review'):
            with self.subTest(judge=judge), TemporaryDirectory() as directory:
                source, target = Path(directory) / 'input.json', Path(directory) / 'out.json'
                write_json(source, {'text': 'source'})
                def validate(value, chunk):
                    if value['value'] != 'valid':
                        raise ValueError('Unsupported by source')
                arguments = dict(settings=Settings(model='fake'), prompt='extract', schema=SCHEMA,
                                 judge_prompt=judge, validator=validate, validator_version='1')
                client = Mock()
                client.chat_json.return_value = {'value': 'invalid'}
                result = extract_document(source, target, client=client, **arguments)
                self.assertEqual(result['completed_chunks'], 0)
                self.assertEqual(result['failures'][0]['error'], 'Unsupported by source')
                checkpoint = read_json(target.with_suffix('.checkpoint.json'))
                self.assertEqual(len(checkpoint['calls']), 1 if judge else 0)
                client.chat_json.reset_mock()
                client.chat_json.return_value = {'value': 'valid'}
                result = extract_document(source, target, client=client, resume=True, **arguments)
                self.assertEqual(result['status'], 'complete')
                client.chat_json.assert_called_once()

    def test_chat_retry_endpoint_and_local_server_without_key(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={'choices': [{'message': {'content':
                'invalid JSON' if len(requests) == 1 else '{"value":"ok"}'}, 'finish_reason': 'stop'}]})
        settings = Settings(llm_base_url='http://example.invalid/v1', model='fake', max_output_tokens=222)
        with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
            with LLMClient(settings, client=http_client) as llm:
                result = llm.chat_json('fake', [{'role': 'user', 'content': 'test'}], SCHEMA)
        self.assertEqual(result, {'value': 'ok'})
        self.assertEqual(len(requests), 2)
        self.assertEqual(str(requests[0].url), 'http://example.invalid/v1/chat/completions')
        self.assertNotIn('authorization', requests[0].headers)
        self.assertEqual(json.loads(requests[0].content)['max_tokens'], 222)

    def test_folder_can_be_copied_and_run_without_original_project(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(Path(__file__).parent, root / 'document_toolkit',
                            ignore=shutil.ignore_patterns('__pycache__'))
            source, target = root / 'input.json', root / 'output.json'
            write_json(source, {'text': 'portable text'})
            # -I ignores working-directory imports and PYTHONPATH. Add only the copied root.
            script = ('import sys,runpy;sys.path.insert(0,sys.argv.pop(1));'
                      'sys.argv[0]="document_toolkit";'
                      'runpy.run_module("document_toolkit",run_name="__main__")')
            result = subprocess.run([sys.executable, '-I', '-c', script, str(root), 'read',
                                     '--input', str(source), '--output', str(target)],
                                    cwd=root, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(read_json(target)['sections'][0]['text'], 'portable text')


if __name__ == '__main__':
    unittest.main()
