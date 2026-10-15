"""카메라 + LiDAR 동시 점검. 대차 모터 연결/명령 기능은 없습니다."""
import sys
sys.dont_write_bytecode = True
import argparse
from collections import deque
import csv
from datetime import datetime
import math
from pathlib import Path
from statistics import median
import threading
import time
import tkinter as tk
from tkinter import ttk

import cv2
from PIL import Image, ImageTk
import serial
from serial.tools import list_ports

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "cart-target-preview"))
from preview import CameraWorker, DEFAULT_WEIGHTS
from target_core import Detection, demo_frame, pick_detection

MAX_AGE = .35


def eligible_port(p):
    # 실제 확인한 CP210x 센서만 허용. Arduino 및 기존 모터 COM7은 거부합니다.
    return (p.device.upper() != "COM7" and p.vid == 0x10C4 and p.pid == 0xEA60
            and p.serial_number == "0001")


def angle_delta(a, b):
    return (a-b+180) % 360-180


class PacketParser:
    """비강도 2-byte YDLIDAR 패킷. 공식 XOR 검증, raw/4 mm.

    https://github.com/YDLIDAR/YDLidar-SDK/blob/master/doc/YDLidar-SDK-Communication-Protocol.md
    각도는 기존 코드와 같은 1차 raw 방위입니다. 장착/삼각측량 각도 보정 미적용.
    """
    def __init__(self):
        self.buffer = bytearray()
        self.good = self.bad = 0

    def feed(self, data):
        self.buffer.extend(data)
        out = []
        while len(self.buffer) >= 10:
            pos = self.buffer.find(b"\xaa\x55")
            if pos < 0:
                self.buffer = self.buffer[-1:]
                break
            del self.buffer[:pos]
            if len(self.buffer) < 10:
                break
            n = self.buffer[3]
            if not n:
                self.bad += 1
                del self.buffer[0]
                continue
            size = 10+2*n
            if len(self.buffer) < size:
                break
            p = self.buffer[:size]
            word = lambda i: p[i] | p[i+1] << 8
            check = word(0) ^ word(2) ^ word(4) ^ word(6)
            for i in range(10, size, 2):
                check ^= word(i)
            first, last = (word(4) >> 1)/64, (word(6) >> 1)/64
            if check != word(8) or not (word(4) & 1 and word(6) & 1) or first >= 360 or last >= 360:
                self.bad += 1
                del self.buffer[0]
                continue
            self.good += 1
            for i in range(n):
                angle = (first + ((last-first) % 360)*i/max(1, n-1)) % 360
                out.append((angle, word(10+i*2)/4))
            del self.buffer[:size]
        return out


class PointStore:
    def __init__(self):
        self.bins = {}

    def update(self, points, stamp):
        for a, d in points:
            key = int(round(a*2)) % 720
            # 0도 갱신하여 이전 유효점이 계속 남지 않게 합니다.
            self.bins[key] = (a, d, stamp)

    def fresh(self, now):
        return [(a, d, t) for a, d, t in self.bins.values()
                if 0 <= now-t <= MAX_AGE and 0 < d <= 12000]


def measure(points, now, bearing, half_width, center, gate):
    chosen = [(a, d, t) for a, d, t in points if 0 <= now-t <= MAX_AGE
              and 0 < d <= 12000 and abs(angle_delta(a, bearing)) <= half_width
              and abs(d-center) <= gate]
    if len(chosen) < 3:
        return None, chosen
    distances = [d for _, d, _ in chosen]
    span = max(distances)-min(distances)
    if span > 200:
        return None, chosen  # 서로 다른 표면이 섞인 구간을 단일 거리로 확정하지 않음
    return {"mm": median(distances), "span": span, "n": len(chosen),
            "stamp": max(t for _, _, t in chosen)}, chosen


class LidarWorker:
    def __init__(self, port):
        self.port = port
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.points = PointStore()
        self.parser = PacketParser()
        self.status = "연결 준비"
        self.error = ""
        self.last_packet = None
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def snapshot(self):
        with self.lock:
            return (self.points.fresh(time.monotonic()), self.status, self.error,
                    self.parser.good, self.parser.bad, self.last_packet)

    def run(self):
        device = None
        try:
            matches = [p for p in list_ports.comports() if p.device == self.port and eligible_port(p)]
            if len(matches) != 1:
                raise ValueError("허용된 LiDAR USB 장치가 아닙니다. COM7/Arduino는 열지 않습니다.")
            device = serial.Serial(self.port, 128000, timeout=.1, write_timeout=.5)
            device.reset_input_buffer()
            device.write(b"\xa5\x60")  # LiDAR 스캔 시작만 허용
            self.status = "수신 대기"
            while not self.stop_event.is_set():
                data = device.read(256)
                stamp = time.monotonic()
                with self.lock:
                    previous = self.parser.good
                    points = self.parser.feed(data)
                    if self.parser.good > previous:
                        self.last_packet = stamp
                        self.status = "스캔 수신"
                    self.points.update(points, stamp)
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
                self.status = "연결 오류"
                self.points = PointStore()
        finally:
            if device is not None:
                try:
                    device.write(b"\xa5\x65")  # LiDAR 스캔 종료
                except Exception:
                    pass
                device.close()


class App:
    def __init__(self, root, demo=False, size="1280x820"):
        self.root, self.demo = root, demo
        root.title("대차 카메라 + LiDAR · 모터 연결 없음" + (" · 모의" if demo else ""))
        root.geometry(size)
        root.minsize(1060, 740)
        root.configure(bg="#edf2f6")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#edf2f6")
        style.configure("TLabel", background="#edf2f6", foreground="#203b50", font=("맑은 고딕", 10))
        style.configure("TButton", font=("맑은 고딕", 10), padding=6)
        self.cam = self.lidar = None
        self.running = self.closing = False
        self.packet = None
        self.current = None
        self.baseline = None
        self.history = deque(maxlen=200)
        self.rows = deque(maxlen=6000)
        self.last_record = 0
        self.last_measure_stamp = None
        self.raw_points = []
        self.image_map = None
        self.radar_map = None
        self.selected = "red_box"
        self.bearing, self.half_width, self.center, self.gate = 0., 5., 550., 250.
        self.port = tk.StringVar(value="COM3")
        self.fields = [tk.StringVar(value=v) for v in ("0", "5", "55", "25")]
        self.camera_status = tk.StringVar(value="카메라 대기")
        self.lidar_status = tk.StringVar(value="LiDAR 대기")
        self.object_status = tk.StringVar(value="표적: red_box · 화면 박스로 변경 가능")
        self.distance = tk.StringVar(value="구간 거리 —")
        self.stats = tk.StringVar(value="기준 변화 — · 최근 3초 범위 —")
        self.note = tk.StringVar(value="아래 거리는 선택 구간의 LiDAR 거리입니다. 카메라 표적과 자동 연결되지 않습니다.")
        body = ttk.Frame(root, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="표적 인식 · 거리 변화 점검", font=("맑은 고딕", 20, "bold")).pack(anchor="w")
        ttk.Label(body, text="화면 전용 / 모터 연결·명령 없음 / 동일 표적 여부·실측 정확도 미검증", foreground="#a64b24").pack(anchor="w", pady=(2, 8))
        bar = ttk.Frame(body)
        bar.pack(fill="x")
        ttk.Label(bar, text="LiDAR").pack(side="left")
        self.port_box = ttk.Combobox(bar, textvariable=self.port, values=("COM3",), width=7, state="readonly")
        self.port_box.pack(side="left", padx=5)
        self.start_button = ttk.Button(bar, text="둘 다 시작", command=self.start)
        self.start_button.pack(side="left", padx=4)
        self.stop_button = ttk.Button(bar, text="둘 다 종료", command=self.stop)
        self.stop_button.pack(side="left", padx=4)
        ttk.Button(bar, text="기준 거리 잡기", command=self.set_baseline).pack(side="left", padx=4)
        ttk.Button(bar, text="수치 CSV 저장", command=self.save_csv).pack(side="left", padx=4)
        ttk.Label(bar, text="StreamCam 0 · Full HD / X4 방식 128000").pack(side="right")
        controls = ttk.Frame(body)
        controls.pack(fill="x", pady=8)
        for label, var in zip(("방위°", "폭 ±°", "중심거리 cm", "거리폭 ±cm"), self.fields):
            ttk.Label(controls, text=label).pack(side="left", padx=(0, 4))
            ttk.Entry(controls, textvariable=var, width=7).pack(side="left", padx=(0, 10))
        ttk.Button(controls, text="구간 적용", command=self.apply_region).pack(side="left")
        ttk.Label(controls, text="또는 오른쪽 측정점을 클릭", foreground="#526d80").pack(side="left", padx=10)
        panels = ttk.Frame(body)
        panels.pack(fill="both", expand=True)
        panels.columnconfigure(0, weight=3, uniform="panels")
        panels.columnconfigure(1, weight=2, uniform="panels")
        panels.rowconfigure(1, weight=1)
        ttk.Label(panels, text="01  카메라 · YOLO 박스 클릭", font=("맑은 고딕", 12, "bold")).grid(row=0,column=0,sticky="w")
        ttk.Label(panels, text="02  LiDAR · 측정 구간 선택", font=("맑은 고딕", 12, "bold")).grid(row=0,column=1,sticky="w")
        self.video = tk.Canvas(panels, bg="#172b37", highlightthickness=0, width=300, height=160)
        self.radar = tk.Canvas(panels, bg="#132630", highlightthickness=0, width=200, height=160)
        self.video.grid(row=1,column=0,sticky="nsew",padx=(0,8),pady=5)
        self.radar.grid(row=1,column=1,sticky="nsew",pady=5)
        self.video.bind("<Button-1>", self.select_object)
        self.radar.bind("<Button-1>", self.select_point)
        ttk.Label(panels, textvariable=self.camera_status).grid(row=2,column=0,sticky="w")
        ttk.Label(panels, textvariable=self.lidar_status).grid(row=2,column=1,sticky="w")
        ttk.Label(body, textvariable=self.object_status).pack(anchor="w",pady=4)
        ttk.Label(body, textvariable=self.distance, font=("맑은 고딕", 23, "bold")).pack(anchor="w")
        ttk.Label(body, textvariable=self.stats).pack(anchor="w", pady=3)
        self.chart = tk.Canvas(body, bg="#ffffff", height=65, highlightthickness=0)
        self.chart.pack(fill="x", pady=4)
        self.note_label = ttk.Label(body, textvariable=self.note, foreground="#a64b24", wraplength=1000)
        self.note_label.pack(anchor="w")
        ttk.Label(body, text="상자를 치웠다 놓아 측정점도 변하는지 비교하세요. 방위는 센서 raw 기준이며 차체 정면/카메라 방위가 아닙니다.", wraplength=1000).pack(anchor="w", pady=(4,0))
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.tick)

    def start(self):
        if self.running or any(w and w.thread.is_alive() for w in (self.cam, self.lidar)):
            self.note.set("기존 센서 작업 종료 중입니다. 잠시 후 다시 시작해 주세요.")
            return
        self.history.clear(); self.baseline = None; self.packet = None
        self.current = None; self.last_measure_stamp = None
        if not self.demo:
            candidates = [p.device for p in list_ports.comports() if eligible_port(p)]
            self.port_box.configure(values=candidates)
            if self.port.get() not in candidates:
                self.note.set("선택한 LiDAR가 없습니다. CP210x 0001 장치만 허용하며 Arduino는 열지 않습니다.")
                return
            self.lidar = LidarWorker(self.port.get())
            self.cam = CameraWorker(0,"DSHOW","YOLO",str(DEFAULT_WEIGHTS))
            self.lidar.start(); self.cam.start()
        self.running = True
        self.start_button.configure(state="disabled")
        self.port_box.configure(state="disabled")
        self.note.set("실제 영상/스캔 수신 중 · 센서 대응 보정 전: 거리값은 선택 구간 값입니다." if not self.demo else "모의 데이터 · 실제 카메라/COM 연결 없음")

    def stop(self):
        self.running = False
        for worker in (self.cam, self.lidar):
            if worker:
                worker.stop()
        self.packet = None; self.current = None; self.history.clear()
        self.raw_points = []; self.baseline = None
        self.distance.set("구간 거리 — · 종료")
        self.start_button.configure(state="normal")
        self.port_box.configure(state="readonly")
        self.note.set("센서 종료 요청 완료 · 새 시작 전 이전 작업의 종료를 확인합니다.")

    def close(self):
        self.stop()
        self.closing = True
        self.root.destroy()

    def apply_region(self):
        try:
            a, w, c, g = map(lambda v: float(v.get()), self.fields)
            if not all(math.isfinite(v) for v in (a,w,c,g)) or not (0 <= a < 360 and .5 <= w <= 30 and 1 <= c <= 1200 and 1 <= g <= 200):
                raise ValueError()
        except ValueError:
            self.note.set("입력 오류: 방위 0~359.9°, 폭 0.5~30°, 중심 1~1200cm, 거리폭 1~200cm")
            return
        self.bearing, self.half_width, self.center, self.gate = a, w, c*10, g*10
        self.history.clear(); self.baseline = None; self.current = None
        self.last_measure_stamp = None
        self.note.set("측정 구간 변경 · 기준 초기화. 이 구간이 표적에 해당하는지 치웠다 놓아 확인하세요.")

    def set_baseline(self):
        if not self.current or time.monotonic()-self.current["stamp"] > MAX_AGE:
            self.note.set("최신 유효 구간 거리가 없어 기준을 잡을 수 없습니다.")
            return
        self.baseline = self.current["mm"]
        self.note.set(f"기준 {self.baseline/10:.1f}cm 설정. 변화는 가까워지면 −, 멀어지면 +입니다. 표적 대응은 미검증입니다.")

    def select_point(self, event):
        if not self.radar_map or not self.raw_points:
            return
        cx,cy,scale = self.radar_map
        best = None
        for a,d,t in self.raw_points:
            x = cx+math.sin(math.radians(a))*d*scale
            y = cy-math.cos(math.radians(a))*d*scale
            distance = math.hypot(event.x-x,event.y-y)
            if distance <= 24 and time.monotonic()-t <= MAX_AGE and (best is None or distance<best[0]):
                best = distance,a,d
        if best:
            self.fields[0].set(f"{best[1]:.1f}")
            self.fields[2].set(f"{best[2]/10:.1f}")
            self.apply_region()
        else:
            self.note.set("최신 측정점 가까이를 클릭해 주세요.")

    def select_object(self, event):
        if not self.packet or not self.image_map or time.monotonic()-self.packet[3] > .5:
            return
        ox,oy,scale = self.image_map
        item = pick_detection(self.packet[1], (event.x-ox)/scale, (event.y-oy)/scale)
        if item:
            self.selected = item.label
            self.note.set(f"카메라 표적 {self.selected} 선택. LiDAR 구간 선택과는 별개입니다.")

    def save_csv(self):
        if not self.rows:
            self.note.set("저장할 수치가 없습니다. 먼저 센서를 시작해 주세요.")
            return
        try:
            directory = ROOT/"logs"
            directory.mkdir(exist_ok=True)
            path = directory/f"sensor_check_{datetime.now():%Y%m%d_%H%M%S_%f}.csv"
            with path.open("w",encoding="utf-8-sig",newline="") as f:
                writer = csv.DictWriter(f,fieldnames=list(self.rows[0]))
                writer.writeheader(); writer.writerows(self.rows)
            self.note.set(f"수치 저장 완료: {path.name} · 영상 저장 없음")
        except OSError as exc:
            self.note.set(f"저장 실패: {exc}")

    def draw_video(self, now):
        canvas = self.video
        canvas.delete("all"); self.image_map = None
        p = self.packet
        if not p or now-p[3] > .5 or p[4]:
            canvas.create_text(canvas.winfo_width()/2,canvas.winfo_height()/2,text="영상 대기 / 오래된 영상은 표시 중지",fill="#e4edf0",font=("맑은 고딕",13))
            self.object_status.set("표적 위치 — · 최신 영상 없음")
            return
        frame,ds,seq,stamp,frozen = p
        h,w = frame.shape[:2]
        scale = min(canvas.winfo_width()/w,canvas.winfo_height()/h)
        sw,sh=max(1,int(w*scale)),max(1,int(h*scale))
        ox,oy=(canvas.winfo_width()-sw)/2,(canvas.winfo_height()-sh)/2
        self.image_map=(ox,oy,scale)
        self.photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)).resize((sw,sh),Image.Resampling.LANCZOS))
        canvas.create_image(ox,oy,anchor="nw",image=self.photo)
        canvas.create_line(ox+sw/2,oy,ox+sw/2,oy+sh,fill="#ffde59",dash=(5,4))
        for d in ds:
            x1,y1,x2,y2=d.box
            color="#35edb6" if d.label==self.selected else "#dbe7ed"
            canvas.create_rectangle(ox+x1*scale,oy+y1*scale,ox+x2*scale,oy+y2*scale,outline=color,width=2)
            canvas.create_text(ox+x1*scale,max(oy+12,oy+y1*scale-10),anchor="w",text=f"{d.label} {d.score:.0%}",fill=color)
        matches=[d for d in ds if d.label==self.selected]
        if len(matches)==1:
            d=matches[0]; x1,y1,x2,y2=d.box
            clipped = x1<=1 or y1<=1 or x2>=w-1 or y2>=h-1
            self.object_status.set(f"{self.selected} {d.score:.0%} · X {d.center[0]-w/2:+.0f}px / Y {d.center[1]-h/2:+.0f}px"+(" · 경계 잘림: 중심 신뢰 불가" if clipped else " · 실제 이동량 아님"))
        else:
            self.object_status.set(f"{self.selected}: {'후보 여러 개' if matches else '표적 상실'} · 거리와 자동 연결하지 않음")

    def draw_radar(self, points, chosen):
        canvas=self.radar; canvas.delete("all")
        w,h=canvas.winfo_width(),canvas.winfo_height()
        cx,cy=w/2,h/2
        radius=max(10,min(w,h)/2-28)
        scale=radius/2000
        self.radar_map=(cx,cy,scale)
        for mm in (500,1000,1500,2000):
            r=mm*scale
            canvas.create_oval(cx-r,cy-r,cx+r,cy+r,outline="#38515f")
            canvas.create_text(cx+4,cy-r+10,text=f"{mm/1000:g}m",fill="#a8bac5",anchor="w")
        for a in (self.bearing-self.half_width,self.bearing+self.half_width):
            for lo,hi in [(0,2000)]:
                canvas.create_line(cx,cy,cx+math.sin(math.radians(a))*hi*scale,cy-math.cos(math.radians(a))*hi*scale,fill="#b6a746",dash=(3,3))
        selected={(a,d,t) for a,d,t in chosen}
        for a,d,t in points:
            if d>2000: continue
            x=cx+math.sin(math.radians(a))*d*scale
            y=cy-math.cos(math.radians(a))*d*scale
            color="#ffdc59" if (a,d,t) in selected else "#44c9ae"
            canvas.create_oval(x-2,y-2,x+2,y+2,fill=color,outline="")
        canvas.create_oval(cx-4,cy-4,cx+4,cy+4,fill="white")
        canvas.create_text(10,12,anchor="nw",text="raw 0° ↑ / 90° → · 표시 2m",fill="#c5d8e4")
        canvas.create_text(10,h-18,anchor="w",text="노랑: 선택 구간 · 카메라 표적 대응 미검증",fill="#ffdc59")

    def draw_chart(self, now):
        canvas=self.chart; canvas.delete("all")
        history=[(t,d) for t,d in self.history if now-t<=10]
        if len(history)<2:
            canvas.create_text(10,20,anchor="w",text="선택 구간 거리 · 최근 10초 추이 (유효 데이터 대기)",fill="#526d80")
            return
        lo=min(d for _,d in history)-10; hi=max(d for _,d in history)+10
        width=max(100,canvas.winfo_width()-115)
        previous=None
        for t,d in history:
            point=(100+(t-(now-10))/10*width,53-(d-lo)/(hi-lo)*40)
            if previous and t-previous[0]<.5:
                canvas.create_line(*previous[1],*point,fill="#187d89",width=2)
            previous=(t,point)
        canvas.create_text(8,14,anchor="w",text=f"{hi/10:.1f}cm",fill="#526d80")
        canvas.create_text(8,52,anchor="w",text=f"{lo/10:.1f}cm",fill="#526d80")

    def tick(self):
        if self.closing: return
        now=time.monotonic(); points=[]; chosen=[]; camera_valid=False
        if self.running:
            if self.demo:
                f=demo_frame(300)
                self.packet=(f,[Detection((240,150,360,330),"red_box",.95)],int(now*10),now,False)
                points=[(a%360,520+2*math.sin(now*2)+a*.1,now) for a in range(-4,5)]
                good,bad,last=100,0,now
                status,error="모의 수신",""
            else:
                self.packet,error_cam=self.cam.snapshot()
                points,status,error,good,bad,last=self.lidar.snapshot()
                if error_cam: self.camera_status.set(f"카메라 오류: {error_cam[:65]}")
                elif self.packet: self.camera_status.set(f"실제 {self.packet[0].shape[1]}×{self.packet[0].shape[0]} · #{self.packet[2]} · {now-self.packet[3]:.2f}s 전")
                else: self.camera_status.set("카메라/YOLO 준비 중")
            if self.demo: self.camera_status.set("모의 영상 · 실제 장치 아님")
            camera_valid=bool(self.packet and 0<=now-self.packet[3]<=.5 and not self.packet[4])
            fresh=last is not None and 0<=now-last<=MAX_AGE and not error
            self.lidar_status.set(f"{'모의' if self.demo else self.port.get()} · {'갱신' if fresh else '미수신/오래됨'} · 정상 {good} / 오류 {bad}")
            if error: self.note.set(f"LiDAR 오류: {error[:120]}")
            self.current,chosen=measure(points,now,self.bearing,self.half_width,self.center,self.gate)
            if self.current:
                result=self.current
                if result['stamp']!=self.last_measure_stamp:
                    self.history.append((result['stamp'],result['mm']))
                    self.last_measure_stamp=result['stamp']
                self.distance.set(f"구간 거리 {result['mm']/10:.1f} cm  · 표적 대응 미검증")
                delta="—" if self.baseline is None else f"{(result['mm']-self.baseline)/10:+.1f}cm"
                recent=[d for t,d in self.history if now-t<=3]
                spread=max(recent)-min(recent) if recent else 0
                self.stats.set(f"기준 대비 {delta} · 최근 3초 변화폭 {spread/10:.1f}cm · 점 {result['n']}개 / 구간 내부 폭 {result['span']/10:.1f}cm")
            else:
                self.distance.set("구간 거리 — · 점 부족 / 혼합 / 오래됨")
                self.stats.set("현재 거리·변화량 무효 · 구간을 확인하거나 새 측정점을 선택해 주세요.")
            if now-self.last_record>=.2:
                self.last_record=now
                matches=[d for d in self.packet[1] if d.label==self.selected] if camera_valid else []
                self.rows.append({"시간":datetime.now().isoformat(timespec="milliseconds"),"모의":self.demo,"카메라유효":camera_valid,"표적":self.selected,"검출수":len(matches),"X_px":round(matches[0].center[0]-self.packet[0].shape[1]/2,2) if len(matches)==1 else "","방위_deg":self.bearing,"구간거리_mm":self.current['mm'] if self.current else "","내부폭_mm":self.current['span'] if self.current else "","대응":"미검증"})
        else:
            self.camera_status.set("카메라 종료"); self.lidar_status.set("LiDAR 종료")
        self.raw_points=points
        self.draw_video(now); self.draw_radar(points,chosen); self.draw_chart(now)
        self.root.after(100,self.tick)


def main():
    parser=argparse.ArgumentParser(description="카메라/LiDAR 점검 · 모터 연결 없음")
    parser.add_argument("--demo",action="store_true")
    parser.add_argument("--start",action="store_true")
    parser.add_argument("--size",default="1280x820")
    args=parser.parse_args()
    root=tk.Tk(); app=App(root,args.demo,args.size)
    if args.start or args.demo: root.after(200,app.start)
    root.mainloop()
    for worker in (app.cam,app.lidar):
        if worker: worker.stop(); worker.thread.join(timeout=2)


if __name__=="__main__":
    main()
