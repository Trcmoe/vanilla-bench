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
            with self.assertRaisesRegex(ValueError,'No stable Fabric release'): resolve()
