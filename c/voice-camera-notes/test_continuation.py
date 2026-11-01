import json
from pathlib import Path
import tempfile
import unittest
from continuation import quota_snapshot, quota_remaining, next_reset, ready, launch_args


class Tests(unittest.TestCase):
    def test_quota_ignores_user_content_and_uses_limiting_window(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'session.jsonl'
            p.write_text('\n'.join(json.dumps(d) for d in [
                {'type':'response_item','payload':{'type':'message','role':'user','rate_limits':'not quota'}},
                {'type':'event_msg','timestamp':'2026-11-01T00:00:00Z','payload':{'type':'token_count','rate_limits':{
                    'primary':{'used_percent':91,'resets_at':100},'secondary':{'used_percent':95,'resets_at':200}}}}]))
            q=quota_snapshot(p)
            self.assertEqual(quota_remaining(q),5)
            self.assertEqual(next_reset(q),200)
            self.assertNotIn('user', json.dumps(q))

    def test_requires_pushed_checkpoint_and_never_resumes_active_work(self):
        s={'enabled':True,'checkpoint_pushed':True,'status':'waiting_quota','resume_after':100}
        self.assertFalse(ready(s,99)); self.assertTrue(ready(s,101))
        for status in ['working','resuming','complete','awaiting_checkpoint']:
            self.assertFalse(ready(dict(s,status=status),101))
        self.assertFalse(ready(dict(s,checkpoint_pushed=False),101))

    def test_resume_explicit_session_without_permission_bypass(self):
        args=launch_args({'codex_exe':'codex','session_id':'01a1923c-1177-7b02-800a-baf270b07af1'})
        self.assertNotIn('--last',args)
        self.assertFalse(any('dangerously' in value for value in args))
        self.assertIn('workspace-write',args)


if __name__=='__main__':unittest.main()
