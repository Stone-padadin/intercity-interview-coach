"""Synthetic provider responses; not a successful real-model vision evaluation."""
import base64
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from urllib import request, error
from app import Notes, make_server, now
from vision import Vision, VisionError, NoRedirect
from test_app import event

IMAGE = b'\xff\xd8\xffsynthetic-test-payload'


class Camera:
    def snapshot(self):
        return IMAGE, now()


class Tests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.cfg = self.root / 'vision-config.json'
        self.cfg.write_text(json.dumps({'base_url': 'https://example.invalid/v1',
                                      'model': 'synthetic-vision', 'api_key': 'test-only-key'}))
        self.vision = Vision(self.cfg)

    def tearDown(self):
        self.folder.cleanup()

    def response(self, answer='合成模型响应'):
        return io.BytesIO(json.dumps({'choices': [{'message': {'content': answer}}]}).encode())

    def test_payload_transports_exact_image_and_question_without_audio(self):
        opener = Mock()
        opener.open.return_value = self.response()
        with patch('vision.request.build_opener', return_value=opener):
            result = self.vision.ask(IMAGE, '合成问题')
        req = opener.open.call_args.args[0]
        body = json.loads(req.data)
        self.assertEqual(req.full_url, 'https://example.invalid/v1/chat/completions')
        parts = body['messages'][1]['content']
        self.assertEqual(parts[0]['text'], '合成问题')
        self.assertEqual(base64.b64decode(parts[1]['image_url']['url'].split(',')[1]), IMAGE)
        self.assertFalse(body['stream'])
        self.assertNotIn('audio', body)
        self.assertEqual(result['source'], 'ai_generated')
        self.assertFalse(result['confirmed'])

    def test_missing_config_and_bad_endpoint_never_call_provider(self):
        self.cfg.unlink()
        self.assertFalse(self.vision.status()['configured'])
        with patch('vision.request.build_opener') as transport:
            with self.assertRaises(VisionError):
                self.vision.ask(IMAGE, '问题')
            transport.assert_not_called()
        for base in ['http://example.invalid/v1', 'https://name:secret@example.invalid/v1']:
            self.cfg.write_text(json.dumps({'base_url': base, 'model': 'test', 'api_key': 'test'}))
            self.assertFalse(self.vision.status()['configured'])

    def test_failures_are_sanitized_and_release_lock(self):
        opener = Mock()
        for failure in [error.HTTPError('https://example.invalid', 401, 'private detail', {}, None),
                        TimeoutError('private detail')]:
            opener.open.side_effect = failure
            with patch('vision.request.build_opener', return_value=opener):
                with self.assertRaises(VisionError) as caught:
                    self.vision.ask(IMAGE, '问题')
            self.assertNotIn('private', str(caught.exception))
            self.assertFalse(self.vision.lock.locked())
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.invalid'))

    def test_busy_and_empty_response_do_not_fake_success(self):
        self.vision.lock.acquire()
        with self.assertRaises(VisionError) as caught:
            self.vision.ask(IMAGE, '问题')
        self.assertEqual(caught.exception.status, 409)
        self.vision.lock.release()
        opener = Mock(); opener.open.return_value = self.response('')
        with patch('vision.request.build_opener', return_value=opener):
            with self.assertRaises(VisionError): self.vision.ask(IMAGE, '问题')

    def test_http_consent_and_note_integrity_before_upload(self):
        notes = Notes(self.root, 'test_exp', Camera())
        notes.ingest(event())
        note = notes.list()[0]
        server = make_server(notes, 0, self.vision)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        def post(body):
            req = request.Request(f'http://127.0.0.1:{server.server_port}/api/vision/ask',
                                  data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
            return request.urlopen(req)
        try:
            with patch.object(self.vision, 'ask', return_value={'answer': '合成回答'}) as ask:
                with self.assertRaises(error.HTTPError) as caught: post({'question': '问题'})
                self.assertEqual(caught.exception.code, 400); ask.assert_not_called()
                with post({'question': '问题', 'upload_confirmed': True, 'note_id': note['id']}) as response:
                    self.assertEqual(json.load(response)['note_id'], note['id'])
                self.assertEqual(ask.call_args.args[0], IMAGE)
                self.assertIn(note['text'], ask.call_args.args[1])
                self.assertFalse(notes.list()[0]['confirmed'])
                (self.root / 'photos' / note['photo']).write_bytes(b'changed')
                ask.reset_mock()
                with self.assertRaises(error.HTTPError):
                    post({'question': '问题', 'upload_confirmed': True, 'note_id': note['id']})
                ask.assert_not_called()
        finally:
            server.shutdown(); server.server_close(); worker.join(3)


if __name__ == '__main__':
    unittest.main()
