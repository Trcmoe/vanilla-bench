import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from vanilla_bench.capture import capture_command
from vanilla_bench.catalog import resolve


class SetupTests(unittest.TestCase):
    def test_capture_preserves_argument_boundaries_and_replaces_only_game_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'local-command.json'
            capture_command(['--','java','-Xmx4G','-cp','a b.jar','Main','--gameDir',tmp,'--username','test'],output)
            data=json.loads(output.read_text())
            self.assertIn('a b.jar',data['command'])
            self.assertIn('{game_dir}',data['command'])
            self.assertEqual(data['game_dir'],str(Path(tmp).resolve()))
            with self.assertRaises(FileExistsError): capture_command(['java','--gameDir',tmp],output)
    def test_capture_requires_game_dir_and_no_quickplay(self):
        with tempfile.TemporaryDirectory() as tmp:
            for command in [['java','@args.txt'],['java','--gameDir',tmp,'--server','example.org']]:
                with self.assertRaises(ValueError): capture_command(command,Path(tmp)/'local.json')
    def test_catalog_never_silently_selects_beta(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self): return b'[{"version_type":"beta","date_published":"2026"}]'
        with patch('vanilla_bench.catalog.urlopen',return_value=Response()):
            with self.assertRaisesRegex(ValueError,'No stable Fabric release'): resolve(['pack-a'])

    def test_catalog_resolves_only_requested_projects(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self):
                return json.dumps([{'version_type':'release','date_published':'2026-01-01',
                                    'id':'version-id','version_number':'1.0','files':[]}]).encode()
        with patch('vanilla_bench.catalog.urlopen',return_value=Response()) as request:
            result = resolve(['pack-b','pack-a','pack-b'])
        self.assertEqual([p['project'] for p in result['packs']],['pack-b','pack-a'])
        self.assertEqual(request.call_count,2)
        self.assertIn('/project/pack-b/version?',request.call_args_list[0].args[0].full_url)
        self.assertIn('/project/pack-a/version?',request.call_args_list[1].args[0].full_url)

    def test_catalog_requires_explicit_valid_projects(self):
        with patch('vanilla_bench.catalog.urlopen') as request:
            for projects in ([],None,'pack-a',[''],['pack-a?query'],['https://example.com']):
                with self.assertRaises(ValueError): resolve(projects)
            request.assert_not_called()
