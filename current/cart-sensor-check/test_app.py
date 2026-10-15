"""무구동 자동 검사. 실제 카메라/COM 포트는 열지 않습니다."""
import ast
import hashlib
from pathlib import Path
from types import SimpleNamespace
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from app import App, PacketParser, PointStore, measure, eligible_port, angle_delta


def packet(ds, first=0, last=4):
    raw=lambda a: (int(a*64)<<1)|1
    values=[0x55aa, len(ds)<<8, raw(first), raw(last)]
    distances=[int(d*4) for d in ds]
    checksum=0
    for v in values+distances: checksum^=v
    return b"".join(v.to_bytes(2,"little") for v in values+[checksum]+distances)


class CoreTests(unittest.TestCase):
    def test_official_zero_packet(self):
        parser=PacketParser()
        out=parser.feed(bytes.fromhex("aa 55 01 01 53 ae 53 ae ab 54 00 00"))
        self.assertEqual(parser.good,1)
        self.assertEqual(out[0][1],0)

    def test_partial_noise_and_checksum(self):
        parser=PacketParser(); p=packet([520,521,522])
        self.assertEqual(parser.feed(b"noise"+p[:8]),[])
        self.assertEqual([d for a,d in parser.feed(p[8:])],[520,521,522])
        broken=bytearray(p); broken[-1]^=1
        self.assertEqual(parser.feed(broken),[])
        self.assertGreater(parser.bad,0)
        self.assertEqual(len(parser.feed(p)),3)

    def test_wrap_and_single(self):
        values=PacketParser().feed(packet([520,520,520],358,2))
        self.assertEqual([a for a,d in values],[358,0,2])
        self.assertEqual(angle_delta(359,0),-1)
        self.assertEqual(len(PacketParser().feed(packet([500],30,30))),1)

    def test_zero_and_age_clear(self):
        store=PointStore(); store.update([(1,500)],10)
        self.assertEqual(len(store.fresh(10.1)),1)
        self.assertEqual(store.fresh(10.36),[])
        self.assertEqual(store.fresh(9),[])
        store.update([(1,0)],10.2)
        self.assertEqual(store.fresh(10.3),[])

    def test_background_exclusion(self):
        pts=[(a,520+a,10) for a in range(-3,4)]+[(4,1600,10)]
        result,chosen=measure(pts,10.1,0,5,550,250)
        self.assertEqual(result['mm'],520)
        self.assertEqual(result['n'],7)
        self.assertEqual(result['span'],6)
        self.assertEqual(measure(pts,11,0,5,550,250)[0],None)

    def test_invalid_mixed_and_few(self):
        self.assertIsNone(measure([(0,500,10)],10,0,5,500,250)[0])
        self.assertIsNone(measure([(0,500,10),(1,900,10),(2,1100,10)],10,0,5,800,500)[0])

    def test_motor_port_rejected(self):
        p=lambda dev,vid,pid,s:SimpleNamespace(device=dev,vid=vid,pid=pid,serial_number=s)
        self.assertTrue(eligible_port(p("COM3",0x10c4,0xea60,"0001")))
        self.assertFalse(eligible_port(p("COM7",0x10c4,0xea60,"0001")))
        self.assertFalse(eligible_port(p("COM3",0x2341,0x42,"arduino")))
        self.assertFalse(eligible_port(p("COM3",0x10c4,0xea60,"another")))

    def test_motor_and_original_files_unchanged(self):
        base=Path(__file__).resolve().parent.parent
        expected={
            'ROBOT-motor-review-928b2a8/urt/mecanum_motor/src/main.cpp':'6C95886A741D153604B23B092C5A1DFBA6D75294FA6BA2F2B7FEF690B3DA175C',
            'ROBOT-motor-review-928b2a8/common/manual_motor_test.py':'66F3E3A32E5965FB09B086869F5C41C495DB0148EE8635C0BCCD40FD0FAE1632',
            'cart-manual-ui/driver_adapter.py':'AA6C2FAE299025609A4E1923C45F08006A1AA0A00F62E6E9850AFB4E24029689',
            'cart-target-preview/preview.py':'AFFA454BBF99E429A0A47FA70990475359DC83F62FF626D333114EA224E254DF',
            'cart-target-preview/target_core.py':'AC6B5F723FCB55BBD6E86A71AEE1657FD76718A1D63DDB728829E3CDD933F6FC',
        }
        for path,value in expected.items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((base/path).read_bytes()).hexdigest().upper(),value)

    def test_only_scan_commands(self):
        tree=ast.parse(Path(__file__).with_name('app.py').read_text(encoding='utf-8'))
        writes=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='write']
        self.assertEqual([n.args[0].value for n in writes],[b'\xa5\x60',b'\xa5\x65'])


class UiTests(unittest.TestCase):
    def test_demo_controls_and_sizes_without_devices(self):
        with patch('app.serial.Serial',side_effect=AssertionError('포트 열면 실패')),patch('app.cv2.VideoCapture',side_effect=AssertionError('카메라 열면 실패')):
            root=tk.Tk()
            try:
                ui=App(root,demo=True)
                for size in ('1280x820','1060x740'):
                    root.geometry(size); root.update()
                    self.assertGreater(ui.video.winfo_width(),400)
                    self.assertGreater(ui.radar.winfo_width(),300)
                    self.assertLess(ui.note_label.winfo_rooty(),root.winfo_rooty()+root.winfo_height())
                ui.start(); root.update(); ui.tick()
                self.assertIsNotNone(ui.current)
                self.assertGreaterEqual(ui.current['mm'],518)
                self.assertLessEqual(ui.current['mm'],522)
                ui.set_baseline(); self.assertIsNotNone(ui.baseline)
                ui.fields[0].set('NaN'); ui.apply_region()
                self.assertIn('입력 오류',ui.note.get())
                ui.fields[0].set('180'); ui.apply_region(); ui.tick()
                self.assertIsNone(ui.current)
                self.assertIsNone(ui.baseline)
                ui.set_baseline(); self.assertIn('없어',ui.note.get())
                ui.fields[0].set('0'); ui.apply_region(); ui.tick()
                ui.stop(); ui.tick(); self.assertIsNone(ui.current)
                self.assertIsNone(ui.packet)
                ui.start(); ui.tick(); self.assertIsNotNone(ui.current)
                ui.close()
            finally:
                try: root.destroy()
                except tk.TclError: pass


if __name__=='__main__': unittest.main()
