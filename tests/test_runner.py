import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import psutil
from vanilla_bench.runner import Protocol, one_run, run_suite, check_effective_settings
from vanilla_bench.config import load_config


class RunnerTests(unittest.TestCase):
    def event(self, kind, **kw):
        return dict(type=kind, run_id='test', jvm_uptime_ms=10, **kw)

    def test_protocol_rejects_foreign_and_out_of_order(self):
        p = Protocol('test')
        with self.assertRaises(ValueError): p.accept(self.event('menu'))
        with self.assertRaises(ValueError): p.accept({'type':'hello', 'run_id':'other'})
        p.accept(self.event('hello', pid=1))
        p.accept(self.event('menu'))
        p.accept(self.event('world_ready'))
        p.accept(self.event('measurement_start'))
        for value in [0, -1, float('nan'), float('inf'), True]:
            with self.assertRaises(ValueError): p.accept(self.event('frames', frame_ms=[value]))

    def fixture(self, root, script):
        game = root / 'original'
        game.mkdir()
        (game / 'options.txt').write_text('enableVsync:true\n')
        world = root / 'world'
        world.mkdir()
        (world / 'level.dat').write_bytes(b'test fixture, not a real world')
        jar = root / 'probe.jar'
        jar.write_bytes(b'fixture')
        fake = root / 'fake.py'
        fake.write_text(script)
        config = {'minecraft_version':'1.20.1','world_template':str(world),'probe_jar':str(jar),
                  'repetitions':1,'warmup_seconds':0,'duration_seconds':1,'timeout_seconds':5,
                  'cooldown_seconds':0,'sample_interval_seconds':.05,'seed':1,'scenarios':['static'],
                  'options':{'enableVsync':'false'},
                  'packs':[{'name':'Fixture','version':'test','game_dir':str(game),
                            'command':[sys.executable,str(fake),'{game_dir}']}]}
        return config

    def test_subprocess_collection_and_source_preservation(self):
        script = r'''import json, os, time
f = open(os.environ['VANILLA_BENCH_OUTPUT'], 'w')
def emit(kind, **kw):
    f.write(json.dumps(dict(type=kind, run_id=os.environ['VANILLA_BENCH_RUN_ID'], **kw))+'\n'); f.flush()
emit('hello',pid=os.getpid(),jvm_uptime_ms=10)
emit('menu',jvm_uptime_ms=100)
emit('world_ready',jvm_uptime_ms=200,effective_settings={'vsync':False})
emit('measurement_start',jvm_uptime_ms=201)
time.sleep(1.1)
emit('frames',frame_ms=[10]*100)
emit('measurement_end',jvm_uptime_ms=1201,sample_count=100)
f.close()
'''
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            config=self.fixture(root, script)
            run=one_run(config,config['packs'][0],'static',1,root/'run')
            self.assertEqual(run['status'],'ok',run['error'])
            self.assertEqual(run['startup_ms'],100)
            self.assertEqual(run['world_load_ms'],100)
            self.assertTrue(run['resources'])
            self.assertEqual((root/'original/options.txt').read_text(),'enableVsync:true\n')
            self.assertEqual((root/'run/game/options.txt').read_text(),'enableVsync:false\n')
            self.assertFalse((root/'original/saves').exists())

    def test_failure_and_timeout_are_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            config=self.fixture(root,'raise SystemExit(2)')
            run=one_run(config,config['packs'][0],'static',1,root/'run')
            self.assertEqual(run['status'],'failed')
            self.assertIsNotNone(run['error'])
            self.assertTrue((root/'run/run.json').exists())
            config['timeout_seconds']=1
            pid_path = root / 'child.pid'
            Path(config['packs'][0]['command'][1]).write_text(
                'import os,time; from pathlib import Path; '
                + 'Path(' + repr(str(pid_path)) + ').write_text(str(os.getpid())); time.sleep(30)')
            run=one_run(config,config['packs'][0],'static',1,root/'timeout')
            self.assertIn('TimeoutError',run['error'])
            self.assertTrue(pid_path.exists())
            self.assertFalse(psutil.pid_exists(int(pid_path.read_text())))

    def test_effective_settings_check_uses_window_units_on_hidpi(self):
        config = {'options': {'overrideWidth':'1920','overrideHeight':'1080','enableVsync':'false'}}
        event = {'effective_settings': {'window_width':1920,'window_height':1080,
                 'framebuffer_width':3840,'framebuffer_height':2160,'vsync':False}}
        check_effective_settings(config,event)
        event['effective_settings']['vsync'] = True
        with self.assertRaises(ValueError): check_effective_settings(config,event)

    def test_config_and_nested_output_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            config=self.fixture(root,'pass')
            config_path=root/'config.json'
            config_path.write_text(json.dumps(config))
            self.assertEqual(load_config(config_path)['minecraft_version'],'1.20.1')
            with self.assertRaises(ValueError): run_suite(config, root/'original'/'results')
            config['packs'][0]['command']=[sys.executable,'fake.py']
            config_path.write_text(json.dumps(config))
            with self.assertRaises(ValueError): load_config(config_path)

if __name__=='__main__': unittest.main()
