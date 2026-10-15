"""별도 Windows 수동 UI. 정상 구동 원본을 읽기만 하며 기본은 미연결입니다."""
from __future__ import annotations

import argparse
import ctypes
import pathlib
import sys
import time
import tkinter as tk
from tkinter import messagebox, ttk

sys.dont_write_bytecode = True
from driver_adapter import Worker, motor
from travel_log import TravelLog, LATERAL, MOTIONS, motion_direction
from timed_drive import TimedWorker, MainSession, export_rotation_records
from route_editor import RouteEditor
from screen_recording import WindowRecorder

BG, WHITE, INK, MUTED = "#e9edef", "#ffffff", "#26343e", "#5b6873"
BLUE, LINE, RED = "#315d80", "#cbd3d9", "#b5333f"
LABELS = {"disconnected": "미연결", "connecting": "연결 확인 중", "stopping": "정지 확인 대기",
          "ready": "입력 대기 · 실물 정지 미확정", "moving": "구동 명령 전송 중", "fault": "정지 / 연결 종료"}


def set_changed(variable, value):
    if variable.get() != value:
        variable.set(value)


def configure_changed(widget, **values):
    changed = {key: value for key, value in values.items()
               if str(widget.cget(key)) != str(value)}
    if changed:
        widget.configure(**changed)


class App:
    def __init__(self, root, preview_only=False, size="1280x860"):
        self.root = root
        self.preview_only = preview_only
        self.root.title("웨이퍼 대차 · 통합 제어 UI" + (" · 모의 전용" if preview_only else ""))
        root.geometry(size)
        root.minsize(1040, 780)
        root.configure(bg=BG)
        root.option_add("*Font", ("Malgun Gothic", 10))
        self.worker = TimedWorker(preview_only, session_factory=MainSession)
        self.control_mode = tk.StringVar(value="manual")
        self.sequence_pending = False
        self.output_pending = None
        self.sequence_saved = 0
        self.sequence_log_path = pathlib.Path(__file__).parent / "logs" / f"sequence_{time.time_ns()}.csv"
        self.recorder = WindowRecorder()
        self.record_text = tk.StringVar(value="앱 창만 녹화 · 무음 / 최대 30분")
        self.travel_log = TravelLog()
        self.timing_keys = set()
        self.timing_text = tk.StringVar(value="명령 시간 0.00초 · 완료 기록 0건")
        self.timing_note = tk.StringVar(value=self.travel_log.note)
        self.timing_recent = tk.StringVar(value="최근 기록 없음 · 최근 500건 보관 / 종료 전 CSV 저장")
        self.mouse_key = None
        self.pulse_key = None
        self.last_status = None
        self.closed = False
        self.connecting = False
        self.speed_keys = set()
        self.mode = tk.StringVar(value="preview")
        self.port = tk.StringVar(value="COM7")
        self.confirmed = tk.BooleanVar(value=False)
        self.speed = tk.StringVar(value="10")
        self.status_text = tk.StringVar(value="미연결")
        self.detail = tk.StringVar(value="기본 미연결 · 모의 확인 후 실차 연결을 선택해 주세요.")
        self.enc = tk.StringVar(value="M1 앞왼 —     M2 앞오 —     M3 뒤왼 —     M4 뒤오 —")
        self.tx = tk.StringVar(value="명령 전송 없음")
        self.input_text = tk.StringVar(value="키보드 입력 대기")
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.GetForegroundWindow.restype = ctypes.c_void_p
        self.user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self.user32.GetAncestor.restype = ctypes.c_void_p
        self.user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user32.GetAsyncKeyState.restype = ctypes.c_short
        self.build()
        root.update_idletasks()
        self.hwnd = self.user32.GetAncestor(root.winfo_id(), 2)
        root.bind_all("<ButtonRelease-1>", self.release_mouse, add="+")
        root.bind("<KeyPress>", self.speed_key_down, add="+")
        root.bind("<KeyRelease>", self.speed_key_up, add="+")
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.worker.start()
        self.poll()

    def label(self, parent, text=None, size=10, bold=False, fg=INK, bg=WHITE, **kw):
        return tk.Label(parent, text=text, fg=fg, bg=bg,
                        font=("Malgun Gothic", size, "bold" if bold else "normal"), **kw)

    def button(self, parent, text, command=None, primary=False, danger=False, **kw):
        color = RED if danger else BLUE if primary else "#edf2f5"
        return tk.Button(parent, text=text, command=command, bg=color,
                         fg=WHITE if primary or danger else INK, activebackground="#dce7ee",
                         relief="solid", bd=1, highlightthickness=0,
                         padx=14, pady=9, cursor="hand2", takefocus=True, **kw)

    def panel(self, parent):
        return tk.Frame(parent, bg=WHITE, highlightthickness=1, highlightbackground=LINE)

    def build(self):
        header = tk.Frame(self.root, bg="#263e50", height=60)
        header.pack(fill="x")
        self.label(header, "웨이퍼 이송 대차", 19, True, WHITE, "#263e50").pack(side="left", padx=22, pady=8)
        self.record_button = self.button(header, "● 화면 녹화 시작", self.toggle_recording)
        self.record_button.pack(side="right", padx=16,pady=5)
        self.label(header, "수동 / 순서 주행 · 원본 코드 유지", 10, fg="#dbe6ed", bg="#263e50").pack(side="right", padx=12)
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=8)
        payload = self.panel(body)
        payload.pack(fill="x", pady=(0, 6))
        title = tk.Frame(payload, bg=WHITE)
        title.pack(side="left", padx=18)
        self.label(title, "웨이퍼 적재", 14, True).pack(anchor="w")
        self.label(title, "로봇팔 수량·완료 신호 미연결", 9, fg=MUTED).pack(anchor="w", pady=4)
        self.label(payload, "— / —", 24, True, BLUE).pack(side="left", padx=20)
        wafer = tk.Canvas(payload, width=330, height=92, bg=WHITE, highlightthickness=0)
        wafer.pack(side="left", padx=10, pady=2)
        for i in range(5):
            x = 8 + i*64
            wafer.create_oval(x, 4, x+48, 52, fill="#f1f4f8", outline="#9bafc3", width=2, dash=(3, 3))
            wafer.create_oval(x+15, 19, x+33, 37, outline="#b8c7d6")
            wafer.create_oval(x+21, 50, x+27, 54, fill=WHITE, outline=WHITE)
            wafer.create_text(x+24, 68, text=f"슬롯 {i+1}", font=("Malgun Gothic", 9, "bold"), fill=INK)
            wafer.create_text(x+24, 84, text="미수신", font=("Malgun Gothic", 8), fill=MUTED)
        self.label(payload, "5개 슬롯은 화면 구성 기준입니다.\n수량·자동 출발 미연결", 9, fg=MUTED, justify="left", wraplength=190).pack(side="right", padx=16)
        status = tk.Frame(body, bg=BG)
        status.pack(fill="x", pady=(0, 10))
        self.control_radios = []
        for value, caption in (("manual","키보드 수동"),("sequence","순서 주행 20%")):
            button = tk.Radiobutton(status,text=caption,variable=self.control_mode,value=value,bg=BG,command=self.select_control)
            button.pack(side="left")
            self.control_radios.append(button)
        self.state_label = self.label(status, size=12, bold=True, bg=BG, textvariable=self.status_text)
        self.state_label.pack(side="left", padx=22)
        self.label(status, "방식 전환: 연결 종료 후 / 장애물 자동 정지 없음", 9, fg=MUTED, bg=BG).pack(side="right")
        self.monitor_tabs = ttk.Notebook(body)
        self.monitor_tabs.pack(fill="both", expand=True)
        monitors = tk.Frame(self.monitor_tabs, bg=BG)
        self.manual_page = monitors
        self.monitor_tabs.add(monitors,text="대차 최종본 · 주행 기록")
        self.route_page = tk.Frame(self.monitor_tabs,bg=WHITE)
        route_canvas = tk.Canvas(self.route_page,bg=WHITE,highlightthickness=0)
        route_scroll = ttk.Scrollbar(self.route_page,command=route_canvas.yview)
        route_scroll.pack(side="right",fill="y")
        route_canvas.pack(side="left",fill="both",expand=True)
        route_canvas.configure(yscrollcommand=route_scroll.set)
        self.route_editor = RouteEditor(route_canvas,self.start_sequence)
        route_window = route_canvas.create_window(0,0,window=self.route_editor,anchor="nw")
        def route_region(event):
            bounds = route_canvas.bbox("all")
            if bounds and str(route_canvas.cget("scrollregion")) != " ".join(map(str,bounds)):
                route_canvas.configure(scrollregion=bounds)
        def route_width(event):
            if int(float(route_canvas.itemcget(route_window,"width"))) != event.width:
                route_canvas.itemconfigure(route_window,width=event.width)
        self.route_editor.bind("<Configure>",route_region)
        route_canvas.bind("<Configure>",route_width)
        self.monitor_tabs.add(self.route_page,text="동작 순서 · 버튼으로 추가")
        self.build_lateral_page()
        self.monitor_tabs.bind("<<NotebookTabChanged>>",self.tab_changed)
        monitors.columnconfigure((0, 1), weight=1, uniform="monitor")
        monitors.rowconfigure(0, weight=1)
        mp = self.panel(monitors)
        mp.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        cp = self.panel(monitors)
        cp.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        model_tabs = ttk.Notebook(mp)
        model_tabs.pack(fill="both", expand=True, padx=8, pady=6)
        model = tk.Frame(model_tabs, bg=WHITE)
        booth = tk.Frame(model_tabs, bg=WHITE)
        model_tabs.add(model, text="대차 최종본 · CAD")
        model_tabs.add(booth, text="부스 배치 참고")
        self.cad_image = None
        self.cad_photo = None
        self.cad_size = None
        self.cad_canvas = tk.Canvas(model, bg="#e5e5e5", highlightthickness=0, height=210)
        self.cad_canvas.pack(fill="both", expand=True)
        self.cad_canvas.bind("<Configure>", self.draw_cad)
        model_note = tk.Frame(model, bg=WHITE)
        model_note.pack(side="bottom", before=self.cad_canvas, fill="x")
        self.label(model_note, "정적 CAD · 실시간 위치 아님", size=9, fg=MUTED).pack(side="left")
        self.cad_expand = self.button(model_note, "확대", self.expand_cad)
        self.cad_expand.configure(padx=6, pady=2)
        self.cad_expand.pack(side="right")
        try:
            from PIL import Image
            with Image.open(pathlib.Path(__file__).parent / "assets" / "cart-final.png") as source:
                self.cad_image = source.convert("RGB")
        except (OSError, ImportError) as exc:
            self.cad_error = "CAD 미리보기 불러오기 실패: " + str(exc)
            self.cad_expand.configure(state="disabled")
        self.map = tk.Canvas(booth, bg="#f8fafb", highlightthickness=0, height=210)
        self.map.pack(fill="both", expand=True, padx=12)
        self.map.bind("<Configure>", self.draw_map)
        self.label(booth, "SLAM·위치 미연결 / 부스 배치 참고용", 9, fg=MUTED).pack(side="bottom", before=self.map, pady=5)
        self.label(cp, "주행 시간 기록   /   카메라 미연결", 11, True, anchor="w").pack(fill="x", padx=12, pady=6)
        video = tk.Frame(cp, bg="#263039", height=190)
        video.pack(fill="both", expand=True, padx=12)
        self.label(video, "카메라 영상 미연결", 15, fg="#dbe1e7", bg="#263039").place(relx=.5, rely=.43, anchor="center")
        self.label(video, "이번 UI는 수동 구동만 연결합니다.", 10, fg="#afbfcb", bg="#263039").place(relx=.5, rely=.62, anchor="center")
        self.label(cp, "사람 감지·거리·카메라 보호 정지 미연결", 9, fg=MUTED).pack(side="bottom", before=video, pady=3)
        control = self.panel(body)
        control.pack(side="bottom", before=self.monitor_tabs, fill="x", pady=(8, 0))
        control.columnconfigure(0, weight=3)
        control.columnconfigure(1, weight=2)
        control.columnconfigure(2, weight=3)
        connection = tk.Frame(control, bg=WHITE)
        connection.grid(row=0, column=0, sticky="nsew", padx=14, pady=12)
        self.label(connection, "01  연결", 11, True).pack(anchor="w")
        modes = tk.Frame(connection, bg=WHITE)
        modes.pack(anchor="w", pady=5)
        self.radios = []
        for value, label in (("preview", "모의 확인"), ("real", "실차 COM")):
            r = tk.Radiobutton(modes, text=label, variable=self.mode, value=value, bg=WHITE,
                               command=self.mode_changed, takefocus=False)
            r.pack(side="left")
            self.radios.append(r)
        row = tk.Frame(connection, bg=WHITE)
        row.pack(fill="x")
        self.port_entry = ttk.Entry(row, textvariable=self.port, width=9)
        self.port_entry.pack(side="left", padx=(0, 6), ipady=5)
        self.connect_button = self.button(row, "모의 시작", self.connect, primary=True)
        self.connect_button.pack(side="left")
        self.disconnect_button = self.button(row, "연결 종료", lambda: self.worker.request("disconnect"))
        self.disconnect_button.pack(side="left", padx=5)
        self.confirm_box = tk.Checkbutton(connection, text="전원 OFF·퓨즈·차단 수단·주변 확인", variable=self.confirmed,
                                          bg=WHITE, anchor="w", takefocus=False)
        self.confirm_box.pack(anchor="w", pady=(8, 0))
        self.label(connection, "기존 터미널/앱 종료 후 연결하세요.\nCOM 포트는 이 UI만 사용해야 합니다.", 9, fg=MUTED, justify="left").pack(anchor="w", pady=5)
        output = tk.Frame(control, bg=WHITE)
        output.grid(row=0, column=1, sticky="nsew", padx=10, pady=12)
        self.label(output, "02  출력 조절", 11, True).pack(anchor="w")
        level = tk.Frame(output, bg=WHITE)
        level.pack(pady=6)
        self.minus = self.button(level, "−", lambda: self.worker.request("speed", -5))
        self.minus.pack(side="left")
        self.label(level, textvariable=self.speed, size=30, bold=True, fg=BLUE, width=3).pack(side="left", padx=6)
        self.plus = self.button(level, "+", lambda: self.worker.request("speed", 5))
        self.plus.pack(side="left")
        self.label(output, "명령 비율 %   /   5 ~ 40", 10, fg=MUTED).pack()
        self.label(output, "정지 후 [ / ] 또는 − / +\n실측 속도·전류 제한값이 아닙니다.", 9, fg=MUTED).pack(pady=8)
        movement = tk.Frame(control, bg=WHITE)
        movement.grid(row=0, column=2, sticky="nsew", padx=14, pady=12)
        self.label(movement, "03  누르는 동안만 이동", 11, True).pack(anchor="w")
        pad = tk.Frame(movement, bg=WHITE)
        pad.pack(fill="x", pady=6)
        pad.columnconfigure((0, 1, 2), weight=1)
        self.move_buttons = []
        for row, col, key, caption in ((0,0,"a","A  ↶ 좌회전"),(0,1,"w","W  ↑ 전진"),(0,2,"d","D  ↷ 우회전"),
                                       (1,0,"z","Z  ← 평행"),(1,1,"s","S  ↓ 후진"),(1,2,"c","C  → 평행")):
            b = self.button(pad, caption)
            b.grid(row=row, column=col, sticky="ew", padx=2, pady=2)
            b.bind("<ButtonPress-1>", lambda e, k=key: self.hold_mouse(k))
            b.bind("<Leave>", self.release_mouse)
            self.move_buttons.append(b)
        self.label(movement, textvariable=self.input_text, size=9, fg=MUTED, wraplength=280, justify="left").pack(anchor="w")
        self.label(movement, "한 키씩 · 키 해제/다른 창 전환 시 정지", 9, fg=MUTED).pack(anchor="w", pady=3)
        telemetry = tk.Frame(body, bg=BG)
        telemetry.pack(side="bottom", before=control, fill="x", pady=(8, 0))
        self.label(telemetry, textvariable=self.enc, size=9, bg=BG).pack(anchor="w")
        self.label(telemetry, textvariable=self.tx, size=9, fg=MUTED, bg=BG).pack(anchor="w", pady=3)
        # 작은 창에서도 지도/정지 조작이 밀리지 않도록 미연결 영상 영역 일부를 사용합니다.
        timing = self.panel(cp)
        timing.pack(side="bottom", before=video, fill="x", padx=12, pady=(4, 6))
        timing_row = tk.Frame(timing, bg=WHITE)
        timing_row.pack(fill="x", padx=6, pady=(0, 0))
        self.label(timing, textvariable=self.timing_text, size=11, bold=True, fg=BLUE).pack(before=timing_row, anchor="w", padx=8, pady=4)
        self.export_button = self.button(timing_row, "CSV 저장", self.export_timing)
        self.export_button.pack(side="right", padx=3)
        self.button(timing_row, "기록 취소", self.cancel_timing).pack(side="right", padx=3)
        self.arrive_button = self.button(timing_row, "F9  1m 도착 기록", self.arrive_timing)
        self.arrive_button.pack(side="right", padx=3)
        self.arm_button = self.button(timing_row, "F8  1m 대기", self.arm_timing)
        self.arm_button.pack(side="right", padx=3)
        for button in timing_row.winfo_children():
            button.configure(padx=5, pady=5, font=("Malgun Gothic", 9))
        self.label(timing, textvariable=self.timing_note, size=9, fg=MUTED, wraplength=430, justify="left").pack(anchor="w", padx=8, pady=3)
        self.label(timing, textvariable=self.timing_recent, size=9, fg=MUTED, wraplength=430, justify="left").pack(anchor="w", padx=8, pady=(0, 6))
        video.pack_forget()  # 영상 미연결 표시는 제목/하단에 유지합니다.
        timing.pack_configure(side="top", fill="both", expand=True)
        footer = tk.Frame(self.root, bg="#f6f8f9", highlightthickness=1, highlightbackground=LINE)
        footer.pack(side="bottom", before=body, fill="x")
        text = tk.Frame(footer, bg="#f6f8f9")
        text.pack(side="left", fill="x", expand=True, padx=18, pady=6)
        self.detail_label = self.label(text, textvariable=self.detail, size=10, bg="#f6f8f9", anchor="w", justify="left", wraplength=740)
        self.detail_label.pack(anchor="w")
        self.label(text, "화면 정지는 물리 전원 차단을 대신하지 않습니다. 오류 후 자동 재출발하지 않습니다.", 9, fg=MUTED, bg="#f6f8f9").pack(anchor="w", pady=4)
        self.record_label = self.label(text,textvariable=self.record_text,size=9,fg=BLUE,bg="#f6f8f9",wraplength=700,justify="left")
        self.record_label.pack(anchor="w")
        self.button(footer, "정지  Space", self.stop).pack(side="left", padx=6)
        self.button(footer, "즉시 정지 / 종료  Esc", self.estop, danger=True).pack(side="left", padx=(6, 18), pady=10)
        self.mode_changed()

    def build_lateral_page(self):
        self.lateral_page = tk.Frame(self.monitor_tabs, bg=WHITE)
        self.monitor_tabs.add(self.lateral_page, text="주행별 시간 · 6방향")
        canvas = tk.Canvas(self.lateral_page, bg=WHITE, highlightthickness=0)
        scroll = ttk.Scrollbar(self.lateral_page, command=canvas.yview)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        content = tk.Frame(canvas, bg=WHITE)
        window = canvas.create_window(0, 0, window=content, anchor="nw")
        def region(event):
            bounds = canvas.bbox("all")
            if bounds and str(canvas.cget("scrollregion")) != " ".join(map(str, bounds)):
                canvas.configure(scrollregion=bounds)
        def width(event):
            if int(float(canvas.itemcget(window, "width"))) != event.width:
                canvas.itemconfigure(window, width=event.width)
        content.bind("<Configure>", region)
        canvas.bind("<Configure>", width)
        self.lateral_clock = tk.StringVar(value="대기 · 0.00초")
        self.lateral_values, self.lateral_buttons, self.lateral_confirm = {}, {}, {}
        self.label(content, "6방향 주행 · 누르면 측정 / 놓으면 정지·기록", 13, True).pack(anchor="w", padx=14, pady=(6, 0))
        self.label(content, textvariable=self.lateral_clock, size=18, bold=True, fg=BLUE).pack(anchor="w", padx=14)
        output_row = tk.Frame(content, bg=WHITE)
        output_row.pack(fill="x", padx=14, pady=4)
        self.output_choice = tk.StringVar(value="20")
        self.label(output_row, "측정 출력 (%)", bold=True).pack(side="left")
        self.output_box = ttk.Combobox(output_row, textvariable=self.output_choice,
                                       values=tuple(str(n) for n in range(5, 41, 5)),
                                       width=5, state="readonly")
        self.output_box.pack(side="left", padx=8)
        self.output_apply = self.button(output_row, "정지 중 적용", self.apply_measurement_output)
        self.output_apply.configure(pady=3)
        self.output_apply.pack(side="left")
        self.output_status = tk.StringVar(value="현재 적용 10% · 6방향 공통 / 순서 주행은 20% 고정")
        self.label(output_row, textvariable=self.output_status, size=9, fg=BLUE).pack(side="left", padx=10)
        self.output_note = tk.StringVar(value="값 선택 후 적용해 주세요. 출력 %는 실제 이동 속도가 아닙니다.")
        self.label(content, textvariable=self.output_note, size=9, fg=MUTED).pack(anchor="w", padx=14)
        columns = tk.Frame(content, bg=WHITE)
        columns.pack(fill="x", padx=12)
        columns.columnconfigure((0, 1, 2), weight=1, uniform="timing")
        for index, (key, caption) in enumerate(MOTIONS.items()):
            cell = tk.Frame(columns, bg=WHITE)
            cell.grid(row=index // 3, column=index % 3, sticky="nsew", padx=3, pady=3)
            button = self.button(cell, f"{key.upper()}  {caption} · 누르는 동안", primary=True)
            button.configure(pady=4)
            button.pack(fill="x")
            button.bind("<ButtonPress-1>", lambda e, k=key: self.hold_mouse(k))
            button.bind("<Leave>", self.release_mouse)
            self.lateral_buttons[key] = button
            self.lateral_values[key] = tk.StringVar(value="마지막 기록 없음")
            self.label(cell, textvariable=self.lateral_values[key], size=9, justify="left", wraplength=280).pack(anchor="w", pady=2)
            if key in LATERAL:
                confirm = self.button(cell, "방금 이동을 실제 1m로 확인", lambda k=key: self.confirm_lateral(k))
                confirm.configure(pady=3, state="disabled")
                confirm.pack(fill="x")
                self.lateral_confirm[key] = confirm
        self.label(content, "놓기·Space·창/탭 전환 → 정지 / 명령 시간이며 실제 거리·정지 시점은 자동 측정하지 않습니다.", size=9, fg=MUTED).pack(anchor="w", padx=14, pady=2)
        self.label(content, textvariable=self.timing_note, size=9, fg=BLUE, wraplength=900, justify="left").pack(anchor="w", padx=14)
        self.lateral_export = self.button(content, "연결 종료 후 CSV 저장", self.export_timing)
        self.lateral_export.configure(pady=3)
        self.lateral_export.pack(anchor="w", padx=14, pady=3)

    def confirm_lateral(self, direction):
        status = self.worker.get_status()
        if not self.travel_log.can_confirm_lateral(direction, status):
            return
        row = self.travel_log.lateral_candidates[direction]
        if messagebox.askyesno("실제 거리 확인", f'{LATERAL[direction]} 평행 / 20% / {row["경과초"]}초\n대차가 실제로 1m 이동한 것을 확인하셨나요?\n자동 측정이나 순서 주행 적용이 아닌 사용자 확인 기록입니다.', parent=self.root):
            self.travel_log.confirm_lateral(direction, self.worker.get_status())

    def apply_measurement_output(self):
        state = self.worker.get_status()
        if self.output_pending is not None:
            return
        try:
            value = int(self.output_choice.get())
            if value not in range(5, 41, 5):
                raise ValueError
        except ValueError:
            self.output_note.set("출력은 5~40% 사이에서 5% 단위로 선택해 주세요.")
            return
        held = any(self.user32.GetAsyncKeyState(vk) & 0x8000 for vk in motor.VK.values())
        if (self.connecting or state["control_mode"] != "manual"
                or state["state"] not in {"ready", "disconnected"} or self.mouse_key or held):
            self.output_note.set("수동 모드에서 주행 키·버튼을 놓고 정지한 뒤 적용해 주세요.")
            return
        if state["speed"] == value:
            self.output_note.set(f"현재 {value}%가 적용되어 있습니다.")
            return
        self.output_pending = value
        self.output_deadline = time.monotonic() + 1.0
        self.output_note.set(f"{value}% 적용 요청 중 · 주행 키를 놓아 주세요.")
        self.worker.publish(set(), False)
        self.worker.request("manual_speed", value)

    def update_lateral(self, state):
        def value_if_changed(variable, value):
            if variable.get() != value:
                variable.set(value)
        def state_if_changed(widget, enabled):
            value = "normal" if enabled else "disabled"
            if str(widget.cget("state")) != value:
                widget.configure(state=value)
        active = self.travel_log.active
        direction = motion_direction(active["identity"][2], active["identity"][1]) if active else None
        value_if_changed(self.lateral_clock, f'{MOTIONS[direction]} · {self.travel_log.elapsed():.2f}초 / {state["speed"]}%' if direction else "주행 대기 · 방향별 마지막 결과는 아래에 유지됩니다")
        if self.output_pending is not None:
            if state["speed"] == self.output_pending:
                self.output_note.set(f"{self.output_pending}% 적용 완료 · 새로 키/버튼을 누르면 측정합니다.")
                self.output_pending = None
            elif state["state"] == "fault" or time.monotonic() > self.output_deadline:
                self.output_note.set("출력 적용 중단 · 연결 상태를 확인해 주세요.")
                self.output_pending = None
        value_if_changed(self.output_status, f'현재 적용 {state["speed"]}% · 6방향 공통 / 순서 주행은 20% 고정')
        editable = (state["control_mode"] == "manual" and state["state"] in {"ready", "disconnected"}
                    and not self.connecting and self.output_pending is None)
        configure_changed(self.output_box, state="readonly" if editable else "disabled")
        state_if_changed(self.output_apply, editable)
        allowed = state["control_mode"] == "manual" and state["state"] in {"ready", "moving"} and self.output_pending is None
        for key in MOTIONS:
            row = self.travel_log.motion_last.get(key)
            calibration = self.travel_log.lateral_calibration.get(key)
            text = f'{row["모드"]} 최근 {row["경과초"]}초 / {row["명령비율"]}%' if row else "마지막 기록 없음"
            if row:
                text += f'\n종료: {row["종료사유"]} · 실제 이동 미확정'
            if key in LATERAL:
                text += f'\n20% 사용자 확인: {calibration["사용자확인초_m"]}초/m' if calibration else "\n20% 실제 1m 미확인 · 자동 적용 안 함"
            value_if_changed(self.lateral_values[key], text)
            state_if_changed(self.lateral_buttons[key], allowed)
            if key in LATERAL:
                state_if_changed(self.lateral_confirm[key], self.travel_log.can_confirm_lateral(key, state))
        state_if_changed(self.lateral_export, self.travel_log.rows and not self.connecting and state["state"] in {"disconnected", "fault"})

    def draw_cad(self, event=None):
        canvas = self.cad_canvas
        size = (max(1, canvas.winfo_width()), max(1, canvas.winfo_height()))
        if size == self.cad_size:
            return
        self.cad_size = size
        canvas.delete("all")
        if self.cad_image is None:
            canvas.create_text(size[0]/2, size[1]/2, text=self.cad_error, width=max(50,size[0]-20), fill=RED)
            return
        from PIL import Image, ImageTk
        picture = self.cad_image.copy()
        picture.thumbnail(size, Image.Resampling.LANCZOS)
        self.cad_photo = ImageTk.PhotoImage(picture, master=self.root)
        canvas.create_image(size[0]/2, size[1]/2, image=self.cad_photo)

    def expand_cad(self):
        if self.cad_image is None:
            return
        # 주행 중 팝업으로 제어 초점을 빼앗지 않습니다.
        if self.worker.get_status()["state"] not in {"disconnected", "fault"}:
            return
        from PIL import Image, ImageTk
        window = tk.Toplevel(self.root)
        window.title("대차 최종본 · CAD 참고 이미지 / 실시간 위치 아님")
        picture = self.cad_image.copy()
        picture.thumbnail((900,600), Image.Resampling.LANCZOS)
        window.photo = ImageTk.PhotoImage(picture, master=window)
        tk.Label(window, image=window.photo).pack()
        tk.Label(window, text="대차 최종본.SLDASM에서 생성 · 모델/실차 이동과 연동되지 않습니다.").pack(pady=6)

    def draw_map(self, event=None):
        c = self.map
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        left, top, right, bottom = w*.14, 25, w*.87, h-25
        for i in range(7):
            x = left+(right-left)*i/6
            y = top+(bottom-top)*i/6
            c.create_line(x, top, x, bottom, fill="#e0e7eb")
            c.create_line(left, y, right, y, fill="#e0e7eb")
        c.create_rectangle(left, top, right, bottom, outline="#94a9b8", width=2)
        c.create_rectangle(w*.54, h*.24, w*.77, h*.43, fill="#d2b68a", outline="#8b785b")
        c.create_text(w*.655, h*.335, text="테이블", fill=INK, font=("Malgun Gothic", 10))
        for x, caption, color in ((w*.46,"출발",BLUE),(w*.7,"목적지",RED)):
            y = h*.66
            c.create_oval(x-9,y-9,x+9,y+9, outline=color, width=2)
            c.create_text(x,y+24,text=caption,fill=color,font=("Malgun Gothic",9))
        c.create_text(12,12,anchor="w",text="기존 부스 배치 참고 · 축척/좌표 미확정",fill=MUTED,font=("Malgun Gothic",9))

    def mode_changed(self):
        if self.preview_only:
            self.mode.set("preview")
            self.radios[1].configure(state="disabled")
        real = self.mode.get() == "real"
        self.confirmed.set(False)
        self.port_entry.configure(state="normal" if real else "disabled")
        self.confirm_box.configure(state="normal" if real else "disabled")
        self.connect_button.configure(text="실차 연결" if real else "모의 시작")

    def connect(self):
        mode = self.mode.get()
        if mode == "real":
            if not self.confirmed.get():
                messagebox.showwarning("연결 전 확인", "모터 전원 OFF, 퓨즈·물리 차단 수단·주변 안전을 확인해 주세요.", parent=self.root)
                return
            if not self.port.get().strip().upper().startswith("COM"):
                messagebox.showerror("포트", "확인된 COM 포트를 입력해 주세요.", parent=self.root)
                return
        self.connect_button.configure(state="disabled")
        self.connecting = True
        self.root.focus_set()
        self.worker.request("connect", mode, self.port.get().strip().upper(), self.confirmed.get())

    def hold_mouse(self, key):
        if self.worker.get_status().get("control_mode") != "manual":
            return
        self.root.focus_set()
        self.mouse_key = key

    def select_control(self):
        status = self.worker.get_status()
        if self.connecting or status["state"] not in {"disconnected","fault"}:
            self.control_mode.set(status["control_mode"])
            return
        self.mouse_key = None
        self.worker.request("control_mode",self.control_mode.get())
        if self.control_mode.get() == "sequence":
            self.monitor_tabs.select(self.route_page)
        else:
            self.monitor_tabs.select(self.manual_page)

    def tab_changed(self, event=None):
        if self.worker.get_status()["state"] not in {"disconnected","fault"}:
            self.stop()

    def start_sequence(self,text,rate):
        status = self.worker.get_status()
        if self.sequence_pending or status["control_mode"] != "sequence" or status["state"] != "ready" or status["sequence_active"]:
            return
        self.mouse_key = None
        self.root.focus_set()
        keys = {str(v) for v in range(8,256) if self.user32.GetAsyncKeyState(v) & 0x8000}
        if keys:
            self.route_editor.note.set("모든 키를 놓은 뒤 실행해 주세요.")
            return
        self.worker.publish(keys,self.user32.GetForegroundWindow()==self.hwnd)
        self.worker.request("sequence",text,rate)
        self.sequence_pending = True

    def toggle_recording(self):
        if self.recorder.snapshot()["active"]:
            self.recorder.stop()
        else:
            self.recorder.start(self.hwnd,pathlib.Path(__file__).parent / "recordings")

    def speed_key_down(self, event):
        if event.keysym in {"F8", "F9"}:
            if event.keysym not in self.timing_keys:
                self.timing_keys.add(event.keysym)
                (self.arm_timing if event.keysym == "F8" else self.arrive_timing)()
            return "break"
        if event.keysym == "Escape":
            self.estop()
            return "break"
        if event.keysym == "space":
            self.stop()
            return "break"
        changes = {"bracketright": 5, "bracketleft": -5, "plus": 5, "equal": 5, "minus": -5}
        if event.keysym in changes and event.keysym not in self.speed_keys:
            if self.output_pending is not None:
                return "break"
            if not isinstance(self.root.focus_get(), (tk.Entry, ttk.Entry, tk.Text)):
                self.speed_keys.add(event.keysym)
                if self.worker.get_status().get("control_mode","manual") == "manual":
                    self.worker.request("speed", changes[event.keysym])
                return "break"

    def speed_key_up(self, event):
        self.timing_keys.discard(event.keysym)
        self.speed_keys.discard(event.keysym)

    def arm_timing(self):
        self.travel_log.arm(self.worker.get_status())

    def arrive_timing(self):
        self.travel_log.arrive(self.worker.get_status())

    def cancel_timing(self):
        self.travel_log.cancel()

    def export_timing(self):
        # 파일 I/O가 주행 중 UI heartbeat에 영향을 주지 않도록 연결 종료 후에만 저장합니다.
        if self.connecting or self.worker.get_status()["state"] not in {"disconnected", "fault"}:
            self.travel_log.note = "CSV 저장은 연결을 종료한 뒤 가능합니다."
            return
        try:
            path = self.travel_log.export(pathlib.Path(__file__).parent / "logs")
            self.travel_log.note = "저장 완료: logs/" + path.name
        except (OSError, ValueError) as exc:
            self.travel_log.note = "CSV 저장 실패: " + str(exc)

    def release_mouse(self, event=None):
        self.mouse_key = None

    def stop(self):
        self.mouse_key = None
        self.worker.request("stop")

    def estop(self):
        self.mouse_key = None
        self.worker.request("estop")

    def poll(self):
        if self.closed:
            return
        foreground = self.user32.GetForegroundWindow() == self.hwnd
        focus = self.root.focus_get()
        text_edit = isinstance(focus, (tk.Entry, ttk.Entry, tk.Text))
        focused = foreground and not text_edit
        keys = {k for k, vk in motor.VK.items() if self.user32.GetAsyncKeyState(vk) & 0x8000}
        keys -= {"+", "-", "[", "]"}  # 출력 조절은 짧은 키 입력도 받는 Tk 이벤트로 전달합니다.
        previous = self.worker.get_status()
        manual_page = self.monitor_tabs.select() in {str(self.manual_page), str(self.lateral_page)}
        if previous["control_mode"] == "manual" and not manual_page:
            focused = False
        if self.output_pending is not None:
            focused = False
        if previous["control_mode"] == "sequence":
            keys = {str(v) for v in range(8,256) if self.user32.GetAsyncKeyState(v) & 0x8000}
        # 실제 누름 상태를 주기적으로 읽어 키 반복/키 해제 이벤트 누락을 피합니다.
        if not foreground:
            self.mouse_key = None
            self.speed_keys.clear()
            self.timing_keys.clear()
        if self.mouse_key:
            keys.add(self.mouse_key)
        # 종료/정지 키는 입력칸에 초점이 있어도 우선합니다.
        if foreground and keys & {"esc", "x", "q", "e"} and not text_edit:
            self.estop()
            keys.clear()
        self.worker.publish(keys, focused)
        state = self.worker.get_status()
        sequence_busy = state["sequence_active"] or state["timed_active"]
        if state["state"] in {"moving","stopping","fault","disconnected"}:
            self.sequence_pending = False
        sequence_busy = sequence_busy or self.sequence_pending
        progress = state["sequence_note"]
        if state["sequence_active"]:
            progress += f' / 현재 구간 {state["remaining"]:.2f}초 남음'
        self.route_editor.set_state(state["control_mode"]=="sequence" and state["state"]=="ready" and not state["record_pending"],sequence_busy,progress)
        recording = self.recorder.snapshot()
        configure_changed(self.record_button, text="■ 녹화 중지 / 저장" if recording["active"] else "● 화면 녹화 시작")
        recording_message = recording["message"]
        if recording_message.startswith("저장 완료:") and recording["path"]:
            recording_message = "녹화 저장 완료: recordings/" + pathlib.Path(recording["path"]).name
        set_changed(self.record_text, recording_message)
        configure_changed(self.record_label, wraplength=max(280,self.root.winfo_width()-430))
        if state["state"] in {"disconnected","fault"}:
            self.save_sequence_records(state)
        self.travel_log.observe(state)
        self.update_lateral(state)
        set_changed(self.timing_text, f"명령 시간 {self.travel_log.elapsed():.2f}초 · 기록 {len(self.travel_log.rows)}건")
        set_changed(self.timing_note, self.travel_log.note)
        if self.travel_log.rows:
            row = self.travel_log.rows[-1]
            set_changed(self.timing_recent, f'최근: {row["모드"]} / {row.get("주행방향", "미분류")} / {row["명령비율"]}% / {row["경과초"]}초 / {row["종료사유"]} · 최근 500건, 종료 전 CSV 저장')
        configure_changed(self.arm_button, state="normal" if state["state"] == "ready" else "disabled")
        configure_changed(self.arrive_button, state="normal" if self.travel_log.trial else "disabled")
        configure_changed(self.export_button, state="normal" if self.travel_log.rows and not self.connecting and state["state"] in {"disconnected", "fault"} else "disabled")
        configure_changed(self.detail_label, wraplength=max(280, self.root.winfo_width()-430))
        tag = "모의 / 출력 없음" if state["mode"] == "preview" else "실차" if state["mode"] == "real" else "미연결"
        set_changed(self.status_text, tag + "  ·  " + LABELS.get(state["state"], state["state"]))
        configure_changed(self.state_label, fg=RED if state["state"] == "fault" else BLUE)
        set_changed(self.speed, str(state["speed"]))
        set_changed(self.detail, state["message"])
        set_changed(self.tx, "최근 송수신: " + state["tx"] + "   |   최근 주행: " + state["last_motion"])
        counts = state["enc"]
        freshness = "미수신" if state["age"] is None else f'{state["age"]:.1f}초 전'
        stale = state["age"] is not None and state["age"] > .5
        set_changed(self.enc, ("가상 ENC" if state["mode"] == "preview" else "ENC") + "  ·  " + freshness + (" / 오래된 값" if stale else "") + "  |  " + "    ".join(f"{motor.POSITIONS[i+1]} {counts[i] if counts else '—'}" for i in range(4)))
        set_changed(self.input_text, ("이 창 활성 · " if focused else "키 입력 비활성 · ") + (" + ".join(sorted(keys)).upper() if keys and focused else "키를 놓은 뒤 새로 누르세요"))
        active = state["state"] not in {"disconnected", "fault"}
        if active or state["state"] == "fault":
            self.connecting = False
        busy = active or self.connecting or self.output_pending is not None
        configure_changed(self.cad_expand, state="normal" if not busy and self.cad_image is not None else "disabled")
        for radio in self.control_radios:
            configure_changed(radio, state="disabled" if busy else "normal")
        for button in (self.minus,self.plus):
            configure_changed(button, state="normal" if state["control_mode"]=="manual" and self.output_pending is None else "disabled")
        configure_changed(self.connect_button, state="disabled" if busy else "normal")
        for index, radio in enumerate(self.radios):
            configure_changed(radio, state="disabled" if busy or (index == 1 and self.preview_only) else "normal")
        configure_changed(self.port_entry, state="normal" if not active and self.mode.get() == "real" else "disabled")
        for b in self.move_buttons:
            configure_changed(b, state="normal" if manual_page and state["control_mode"]=="manual" and state["state"] in {"ready", "moving"} and self.output_pending is None else "disabled")
        if self.last_status and self.last_status["state"] not in {"fault", "disconnected"} and state["state"] in {"fault", "disconnected"}:
            self.confirmed.set(False)
        self.last_status = state
        self.poll_id = self.root.after(25, self.poll)

    def save_sequence_records(self, state):
        if len(state["records"]) == self.sequence_saved:
            return
        try:
            export_rotation_records(state["records"],self.sequence_log_path)
            self.sequence_saved = len(state["records"])
        except OSError as exc:
            self.route_editor.note.set("CSV 저장 실패: "+str(exc))

    def close(self):
        self.closed = True
        if getattr(self,"poll_id",None):
            self.root.after_cancel(self.poll_id)
        self.recorder.stop()
        self.worker.publish(set(), False)
        self.worker.quit.set()
        self.worker.join(timeout=3.0)
        self.save_sequence_records(self.worker.session.snapshot())
        if self.recorder.thread:
            self.recorder.thread.join(timeout=3.0)
        self.travel_log.finish("앱 종료 · 실물 정지 미확정")
        if self.travel_log.count != self.travel_log.saved_count:
            try:
                self.travel_log.export(pathlib.Path(__file__).parent / "logs")
            except OSError as exc:
                messagebox.showwarning("기록 저장 실패", str(exc), parent=self.root)
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description="기존 구동 코드 보존형 대차 UI")
    parser.add_argument("--preview-only", action="store_true", help="실차 연결을 비활성화한 화면 검증")
    parser.add_argument("--size", choices=["1280x860", "1040x780"], default="1280x860")
    args = parser.parse_args()
    root = tk.Tk()
    App(root, args.preview_only, args.size)
    root.mainloop()


if __name__ == "__main__":
    main()
