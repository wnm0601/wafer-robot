"""표적 중앙 맞춤 · 영상 전용. Arduino/COM/모터 모듈을 가져오지 않습니다."""
import sys
sys.dont_write_bytecode = True
import argparse
import hashlib
from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog

import cv2
from PIL import Image, ImageTk
from target_core import Alignment, Detection, demo_frame, detect_color, pick_color, pick_detection, left_camera_guidance

DEFAULT_WEIGHTS = Path(__file__).resolve().parent.parent / "six_class_detection_training/runs/segment/train/weights/best.pt"
CAPTURE_PROFILES = {
    "Full HD · 1920×1080": (1920, 1080, 30),
    "HD · 1280×720": (1280, 720, 30),
    "기존 · 640×480": (640, 480, 15),
}
DEFAULT_PROFILE = next(iter(CAPTURE_PROFILES))


def configure_capture(cap, profile):
    """해상도는 요청값일 뿐입니다. 실제 해상도는 수신 프레임으로 확인합니다."""
    width, height, fps = CAPTURE_PROFILES[profile]
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)


def capture_caption(frame, profile, demo=False):
    height, width = frame.shape[:2]
    rw, rh, _ = CAPTURE_PROFILES[profile]
    if demo:
        return f"모의 {width}×{height} · 카메라 성능 아님"
    mismatch = " · 요청과 다름" if (width, height) != (rw, rh) else ""
    return f"실제 수신 {width}×{height}{mismatch} · 전체 영상 / 자르기 없음"


def box_caption(detection, width, target_x, yolo=True):
    error_x = detection.center[0] - width * target_x
    confidence = f" {detection.score:.0%}" if yolo else ""
    return f"{detection.label}{confidence} | X {error_x:+.0f}px"


class CameraWorker:
    """캡처와 선택적 YOLO 추론은 Tk 바깥에서 처리합니다. 한 작업만 카메라를 소유합니다."""
    def __init__(self, index, backend, mode, weights="", demo=False, profile=DEFAULT_PROFILE):
        self.index, self.backend, self.mode, self.weights, self.demo = index, backend, mode, weights, demo
        self.profile = profile
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.packet = None
        self.error = ""
        self.selected = None
        self.generation = 0
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()

    def select(self, label):
        with self.lock:
            self.selected = label
            self.generation += 1
            self.packet = None

    def snapshot(self):
        with self.lock:
            return self.packet, self.error

    def stop(self):
        self.stop_event.set()

    def run(self):
        cap = None
        try:
            model = None
            if self.mode == "YOLO" and not self.demo:
                if not Path(self.weights).is_file() or Path(self.weights).suffix.lower() != ".pt":
                    raise ValueError("기존 로컬 YOLO .pt 모델 파일을 선택해 주세요. 자동 다운로드하지 않습니다.")
                from ultralytics import YOLO
                model = YOLO(self.weights)
            if not self.demo:
                backend = cv2.CAP_DSHOW if self.backend == "DSHOW" else cv2.CAP_MSMF
                cap = cv2.VideoCapture(self.index, backend)
                if not cap.isOpened():
                    raise RuntimeError("카메라 열기 실패: 인덱스·USB·다른 앱의 점유를 확인해 주세요.")
                configure_capture(cap, self.profile)
            seq, old_digest, unchanged_since = 0, None, None
            started = time.monotonic()
            while not self.stop_event.is_set():
                with self.lock:
                    selected, generation = self.selected, self.generation
                if self.demo:
                    elapsed = time.monotonic()-started
                    x = int(320+170*__import__('math').sin(elapsed*0.35))
                    frame = demo_frame(x)
                    ok = True
                    self.stop_event.wait(0.05)
                else:
                    ok, frame = cap.read()
                stamp = time.monotonic()
                if not ok or frame is None:
                    raise RuntimeError("영상 수신 실패: 카메라를 닫은 뒤 USB와 카메라 번호를 확인해 주세요.")
                digest = hashlib.blake2b(frame.tobytes(), digest_size=8).digest()
                if digest != old_digest:
                    old_digest, unchanged_since = digest, stamp
                frozen = not self.demo and stamp-unchanged_since >= 2.0
                if model is not None:
                    predictions = model.predict(frame, conf=0.5, imgsz=640, verbose=False)
                    boxes = predictions[0].boxes if predictions else None
                    detections = []
                    if boxes is not None:
                        for box, score, cls in zip(boxes.xyxy.tolist(), boxes.conf.tolist(), boxes.cls.tolist()):
                            detections.append(Detection(tuple(box), model.names[int(cls)], score))
                else:
                    detections = detect_color(frame, selected) if selected else []
                seq += 1
                if self.stop_event.is_set():
                    break
                with self.lock:
                    if generation == self.generation:
                        self.packet = (frame, detections, seq, stamp, frozen)
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
                self.packet = None
        finally:
            if cap is not None:
                cap.release()


MESSAGES = {
    "SELECT": "영상에서 표적을 클릭해 주세요",
    "LEFT": "표적이 목표선 왼쪽에 있습니다",
    "RIGHT": "표적이 목표선 오른쪽에 있습니다",
    "SETTLING": "수평 허용 범위 안 · 안정 확인 중",
    "CENTERED": "수평 중앙 일치 · 주차 완료 판정 아님",
    "LOST": "표적 상실 · 판단 중지 / 다시 선택 가능",
    "AMBIGUOUS": "같은 색/종류 표적이 여러 개 · 판단 중지",
    "STALE": "최신 영상 없음 · 판단 중지",
    "FROZEN": "동일 영상 반복 의심 · 판단 중지",
    "WAIT": "다음 새 프레임 대기",
    "INVALID": "입력값 오류 · 판단 중지",
}


class PreviewApp:
    def __init__(self, root):
        self.root = root
        root.title("대차 표적 중앙 맞춤 · 화면 전용 / MOTOR DISCONNECTED")
        root.geometry("1280x900")
        root.minsize(960, 720)
        root.configure(bg="#edf2f6")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#edf2f6")
        style.configure("TLabel", background="#edf2f6", foreground="#203b50", font=("맑은 고딕", 10))
        style.configure("TButton", font=("맑은 고딕", 10), padding=7)
        self.worker = None
        self.packet = None
        self.alignment = Alignment()
        self.selected = None
        self.last_seq = None
        self.started_at = 0
        self.index = tk.StringVar(value="0")
        self.mode = tk.StringVar(value="YOLO")
        self.backend = tk.StringVar(value="DSHOW")
        self.profile = tk.StringVar(value=DEFAULT_PROFILE)
        self.capture_text = tk.StringVar(value="실제 수신 해상도 — · 넓은 촬영 시야 보장은 아닙니다")
        self.large_view = False
        self.weights = tk.StringVar(value=str(DEFAULT_WEIGHTS))
        self.model_label = tk.StringVar(value="기존 6종 학습 모델 · best.pt")
        self.tolerance = tk.IntVar(value=8)
        self.target_x = 0.5
        self.status = tk.StringVar(value="미연결 · 카메라 번호를 선택한 뒤 시작해 주세요")
        self.error_text = tk.StringVar(value="수평 오차 — px     세로 오차 — px     실제 거리·각도 미측정")
        self.detail = tk.StringVar(value="표적 미선택 · 실제 영상 저장/전송 없음")
        self.mount_confirmed = tk.BooleanVar(value=False)
        self.mirrored = tk.BooleanVar(value=False)
        self.position_text = tk.StringVar(value="표적 위치 —")
        self.guidance_text = tk.StringVar(value="이동 안내 보류 · 좌측 장착 방향을 확인해 주세요")
        body = ttk.Frame(root, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="표적 중앙 맞춤", font=("맑은 고딕", 23, "bold")).pack(anchor="w")
        ttk.Label(body, text="화면 전용  |  COM 연결 없음 · 모터 명령 없음 · 거리/주차 판정 없음",
                  foreground="#b04123").pack(anchor="w", pady=(0, 5))
        controls = ttk.Frame(body)
        controls.pack(fill="x")
        ttk.Label(controls, text="카메라 번호").pack(side="left")
        self.index_box = ttk.Spinbox(controls, from_=0, to=20, width=4, textvariable=self.index)
        self.index_box.pack(side="left", padx=6)
        self.backend_box = ttk.Combobox(controls, textvariable=self.backend, values=("DSHOW", "MSMF"), width=8, state="readonly")
        self.backend_box.pack(side="left", padx=4)
        self.mode_box = ttk.Combobox(controls, textvariable=self.mode, values=("색상 클릭", "YOLO"), width=10, state="readonly")
        self.mode_box.pack(side="left", padx=4)
        self.start_button = ttk.Button(controls, text="카메라 시작", command=self.start)
        self.start_button.pack(side="left", padx=4)
        ttk.Button(controls, text="카메라 종료", command=self.stop).pack(side="left", padx=4)
        self.demo_button = ttk.Button(controls, text="모의 영상", command=lambda: self.start(demo=True))
        self.demo_button.pack(side="left", padx=4)
        self.large_button = ttk.Button(controls, text="영상 크게 · F11", command=self.toggle_large_view)
        self.large_button.pack(side="left", padx=4)
        quality_row = ttk.Frame(body)
        quality_row.pack(fill="x", pady=(5, 0))
        ttk.Label(quality_row, text="영상 품질").pack(side="left")
        self.profile_box = ttk.Combobox(quality_row, textvariable=self.profile, values=tuple(CAPTURE_PROFILES),
                                       width=23, state="readonly")
        self.profile_box.pack(side="left", padx=6)
        ttk.Label(quality_row, textvariable=self.capture_text).pack(side="left", padx=4)
        model_row = ttk.Frame(body)
        model_row.pack(fill="x", pady=6)
        self.model_row = model_row
        self.model_button = ttk.Button(model_row, text="기존 YOLO 모델 선택", command=self.browse)
        self.model_button.pack(side="left")
        ttk.Label(model_row, textvariable=self.model_label, wraplength=550).pack(side="left", padx=8)
        mount_row = ttk.Frame(body)
        mount_row.pack(fill="x")
        self.mount_row = mount_row
        ttk.Checkbutton(mount_row, text="카메라 직립 · 대차 좌측 바깥을 봄 확인", variable=self.mount_confirmed,
                        command=self.refresh_guidance).pack(side="left")
        ttk.Checkbutton(mount_row, text="입력 영상이 좌우 반전됨", variable=self.mirrored,
                        command=self.refresh_guidance).pack(side="left", padx=12)
        self.canvas = tk.Canvas(body, bg="#172630", highlightthickness=0, height=240)
        self.canvas.pack(fill="both", expand=True, pady=8)
        self.canvas.bind("<Button-1>", self.click)
        self.canvas.bind("<Button-3>", lambda _e: self.clear())
        self.canvas.create_text(380, 160, text="카메라 시작 → YOLO 검출 박스를 클릭\n기존 6종 학습 모델 · 모터 연결 없음",
                                fill="white", font=("맑은 고딕", 15), tags="placeholder")
        ttk.Label(body, textvariable=self.status, font=("맑은 고딕", 15, "bold"), wraplength=1000).pack(anchor="w")
        ttk.Label(body, textvariable=self.error_text).pack(anchor="w", pady=4)
        ttk.Label(body, textvariable=self.position_text, foreground="#245d78").pack(anchor="w")
        self.guidance_label = ttk.Label(body, textvariable=self.guidance_text,
                                       font=("맑은 고딕", 12, "bold"), foreground="#17634e", wraplength=900)
        self.guidance_label.pack(anchor="w", pady=3)
        options = ttk.Frame(body)
        options.pack(fill="x", pady=5)
        self.options_row = options
        ttk.Button(options, text="표적 해제", command=self.clear).pack(side="left")
        ttk.Button(options, text="현재 표적 X를 목표로", command=self.set_goal).pack(side="left", padx=5)
        ttk.Button(options, text="화면 중앙으로 복원", command=self.center_goal).pack(side="left")
        tolerance_row = ttk.Frame(body)
        tolerance_row.pack(fill="x", pady=3)
        self.tolerance_row = tolerance_row
        ttk.Label(tolerance_row, text="수평 허용 오차(px)").pack(side="left")
        self.tol_label = ttk.Label(tolerance_row, text="8 px", width=7)
        ttk.Scale(tolerance_row, from_=2, to=30, variable=self.tolerance, command=self.tolerance_changed).pack(side="left", fill="x", expand=True)
        self.tol_label.pack(side="left")
        ttk.Label(body, textvariable=self.detail, wraplength=1000).pack(anchor="w")
        self.display_rect = None
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<F11>", lambda _event: self.toggle_large_view())
        root.bind("<Escape>", lambda _event: self.toggle_large_view() if self.large_view else None)
        root.after(50, self.tick)

    def toggle_large_view(self):
        self.large_view = not self.large_view
        self.root.attributes("-fullscreen", self.large_view)
        self.large_button.configure(text="기본 화면 · Esc" if self.large_view else "영상 크게 · F11")
        if self.large_view:
            for row in (self.model_row, self.mount_row, self.options_row, self.tolerance_row):
                row.pack_forget()
        else:
            self.model_row.pack(fill="x", pady=6, before=self.canvas)
            self.mount_row.pack(fill="x", before=self.canvas)
            self.options_row.pack(fill="x", pady=5, after=self.guidance_label)
            self.tolerance_row.pack(fill="x", pady=3, after=self.options_row)

    def browse(self):
        path = filedialog.askopenfilename(title="기존 로컬 YOLO 모델", filetypes=[("YOLO", "*.pt")])
        if path:
            self.weights.set(path)
            self.model_label.set(f"선택 모델: {Path(path).name}")

    def start(self, demo=False):
        if self.worker and self.worker.thread.is_alive():
            self.status.set("기존 카메라 종료가 완료된 뒤 다시 시작해 주세요")
            return
        try:
            index = int(self.index.get())
            if not 0 <= index <= 20:
                raise ValueError()
        except ValueError:
            self.status.set("카메라 번호는 0~20 정수로 입력해 주세요")
            return
        if self.profile.get() not in CAPTURE_PROFILES:
            self.status.set("목록에서 영상 품질을 선택해 주세요")
            return
        self.clear()
        self.packet, self.last_seq = None, None
        self.started_at = time.monotonic()
        self.capture_text.set("요청 " + self.profile.get() + " · 실제 수신 확인 중")
        self.worker = CameraWorker(index, self.backend.get(), "색상 클릭" if demo else self.mode.get(), self.weights.get(), demo,
                                   self.profile.get())
        self.worker.start()
        self.status.set("모의 영상 시작 중" if demo else "카메라/모델 여는 중 · 모터 연결 없음")
        self.lock_settings(True)

    def lock_settings(self, locked):
        for widget in (self.start_button, self.demo_button, self.model_button, self.index_box):
            widget.configure(state="disabled" if locked else "normal")
        for widget in (self.backend_box, self.mode_box, self.profile_box):
            widget.configure(state="disabled" if locked else "readonly")

    def stop(self):
        if self.worker:
            self.worker.stop()
        self.clear()
        self.packet = None
        self.capture_text.set("카메라 종료 · 실제 수신 해상도 —")
        self.canvas.delete("all")
        self.status.set("카메라 종료 요청 · 영상 판단 중지")
        self.error_text.set("수평 오차 — px     세로 오차 — px     실제 거리·각도 미측정")

    def clear(self):
        self.selected = None
        self.alignment.reset()
        self.last_seq = None
        if self.worker:
            self.worker.select(None)
        self.detail.set("표적 미선택 · 다시 클릭해 주세요")
        self.status.set(MESSAGES["SELECT"])
        self.error_text.set("수평 오차 — px     세로 오차 — px     실제 거리·각도 미측정")
        self.position_text.set("표적 위치 —")
        self.guidance_text.set("이동 안내 중지 · 표적을 선택해 주세요")

    def refresh_guidance(self):
        if self.packet is None or self.worker is None or self.worker.stop_event.is_set():
            self.position_text.set("표적 위치 —")
            self.guidance_text.set("이동 안내 중지 · 최신 영상과 표적이 필요합니다")
            return
        frame, detections, _, stamp, frozen = self.packet
        position, advice = left_camera_guidance(
            detections, self.selected, frame.shape[1], frame.shape[0], stamp, time.monotonic(),
            float(self.tolerance.get()), frozen, self.mount_confirmed.get(), self.mirrored.get())
        self.position_text.set(position)
        self.guidance_text.set(("[모의] " if self.worker.demo else "") + advice)

    def tolerance_changed(self, value):
        self.tol_label.configure(text=f"{float(value):.0f} px")
        self.alignment.reset()
        self.last_seq = None

    def center_goal(self):
        self.target_x = 0.5
        self.alignment.reset()
        self.last_seq = None

    def set_goal(self):
        if self.packet is None or time.monotonic()-self.packet[3] > 0.5 or self.packet[4]:
            self.status.set("최신 표적 1개가 있어야 목표를 설정할 수 있습니다")
            return
        candidates = [d for d in self.packet[1] if d.label == self.selected]
        if len(candidates) != 1:
            self.status.set("표적 1개를 먼저 선택해 주세요")
            return
        self.target_x = candidates[0].center[0] / self.packet[0].shape[1]
        self.alignment.reset()
        self.last_seq = None

    def click(self, event):
        if self.packet is None or self.display_rect is None or time.monotonic()-self.packet[3] > 0.5 or self.packet[4]:
            self.status.set("최신 영상이 있어야 표적을 선택할 수 있습니다")
            return
        ox, oy, scale, dw, dh = self.display_rect
        if not (ox <= event.x < ox+dw and oy <= event.y < oy+dh):
            return
        x, y = int((event.x-ox)/scale), int((event.y-oy)/scale)
        frame, detections, *_ = self.packet
        if self.worker.mode == "YOLO":
            chosen = pick_detection(detections, x, y)
            label = chosen.label if chosen else None
        else:
            label = pick_color(frame, x, y)
        self.clear()
        if label is None:
            self.status.set("선택 불가: 색상 모드는 선명한 단색, YOLO는 검출 박스 안을 클릭해 주세요")
            return
        self.selected = label
        self.worker.select(label)
        self.detail.set(f"선택: {label} · 같은 색/종류가 여러 개면 판단 중지")

    def tick(self):
        if self.worker:
            packet, error = self.worker.snapshot()
            if error:
                self.packet = None
                self.canvas.delete("all")
                self.status.set(error)
                self.error_text.set("수신 오류 · 오차 표시 무효 · 모터 연결 없음")
                self.alignment.reset()
                self.capture_text.set("수신 실패 · 다른 앱 종료 또는 HD 품질로 재시도")
            elif not self.worker.stop_event.is_set() and packet:
                self.packet = packet
                frame, detections, seq, stamp, frozen = packet
                now = time.monotonic()
                is_new = seq != self.last_seq
                if is_new or now-stamp > 0.5 or frozen:
                    code, delta = self.alignment.update(detections, self.selected, frame.shape[1], frame.shape[0], seq, stamp, now,
                                                       float(self.tolerance.get()), self.target_x, frozen)
                    self.status.set(("[모의 영상] " if self.worker.demo else "") + MESSAGES[code])
                    self.error_text.set(f"수평 오차 {delta[0]:+.1f} px     세로 오차 {delta[1]:+.1f} px     실제 거리·각도 미측정"
                                        if delta else "수평 오차 — px     세로 오차 — px     실제 거리·각도 미측정")
                    self.last_seq = seq
                self.draw(frame, detections, now-stamp > 0.5 or frozen)
                self.capture_text.set(capture_caption(frame, self.worker.profile, self.worker.demo))
                self.detail.set(f"{'모의' if self.worker.demo else '실제 카메라'} · 선택 {self.selected or '없음'} · frame {seq} · "
                                f"영상 수신 후 {now-stamp:.2f}초 · 목표 X {self.target_x*100:.1f}% · 모터 연결 없음")
            elif not self.worker.stop_event.is_set() and time.monotonic()-self.started_at > 5:
                self.status.set("영상 대기 중 · 카메라 점유/번호 또는 모델 로딩을 확인해 주세요")
            if not self.worker.thread.is_alive():
                self.lock_settings(False)
        self.refresh_guidance()
        self.root.after(60, self.tick)

    def draw(self, frame, detections, invalid):
        h, w = frame.shape[:2]
        image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        cw, ch = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        scale = min(cw/w, ch/h)
        dw, dh = max(1, int(w*scale)), max(1, int(h*scale))
        ox, oy = (cw-dw)/2, (ch-dh)/2
        self.display_rect = (ox, oy, scale, dw, dh)
        self.photo = ImageTk.PhotoImage(Image.fromarray(image).resize((dw, dh), Image.Resampling.LANCZOS))
        self.canvas.delete("all")
        self.canvas.create_image(ox, oy, image=self.photo, anchor="nw")
        gx = ox+self.target_x*w*scale
        tolerance = float(self.tolerance.get())*scale
        self.canvas.create_rectangle(gx-tolerance, oy, gx+tolerance, oy+dh, outline="#ffd16a", dash=(4, 4))
        self.canvas.create_line(gx, oy, gx, oy+dh, fill="#ffd16a", width=2)
        self.canvas.create_line(ox, oy+dh/2, ox+dw, oy+dh/2, fill="#6f8b9d", dash=(5, 5))
        if self.target_x != .5:
            self.canvas.create_line(ox+dw/2, oy, ox+dw/2, oy+dh, fill="white", dash=(5, 5))
        self.canvas.create_text(ox+dw/2, oy+dh-16, text="화면 중앙",
                                fill="white", font=("맑은 고딕", 10))
        if not invalid:
            for d in detections:
                x1, y1, x2, y2 = d.box
                color = "#59e2b8" if d.label == self.selected else "#94a9bc"
                self.canvas.create_rectangle(ox+x1*scale, oy+y1*scale, ox+x2*scale, oy+y2*scale, outline=color, width=2)
                cx, cy = d.center
                self.canvas.create_oval(ox+cx*scale-4, oy+cy*scale-4, ox+cx*scale+4, oy+cy*scale+4, fill=color)
                caption = box_caption(d, w, self.target_x, self.worker.mode == "YOLO")
                anchor = "e" if x1 > w/2 else "w"
                label_x = ox+(x2 if anchor == "e" else x1)*scale
                self.canvas.create_text(label_x, max(oy+14, oy+y1*scale-12), text=caption, fill=color, anchor=anchor)
        else:
            self.canvas.create_text(cw/2, ch/2, text="영상 무효 · 판단 중지", fill="#ff8f79", font=("맑은 고딕", 24, "bold"))
        self.canvas.create_text(ox+12, oy+16, anchor="w", text="모의 영상" if self.worker.demo else "실제 카메라 · 화면 전용",
                                fill="white", font=("맑은 고딕", 11, "bold"))

    def close(self):
        if self.worker:
            self.worker.stop()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description="표적 중앙 맞춤 화면 전용 · 모터/COM 연결 없음")
    parser.add_argument("--demo", action="store_true", help="카메라를 열지 않는 모의 영상")
    args = parser.parse_args()
    root = tk.Tk()
    app = PreviewApp(root)
    if args.demo:
        root.after(100, lambda: app.start(demo=True))
    root.mainloop()


if __name__ == "__main__":
    main()
