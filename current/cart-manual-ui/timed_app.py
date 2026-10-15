"""기존 앱과 별도로 실행하는 20% 시간 이동 UI. 기본 모의/미연결."""
from __future__ import annotations

import argparse
import ctypes
import json
import pathlib
import sys
import time
import tkinter as tk
from tkinter import messagebox, ttk

sys.dont_write_bytecode = True
from timed_drive import DEFAULT_SECONDS_PER_M, Plan, TimedWorker, export_rotation_records, parse_sequence, describe_plan

BASE = pathlib.Path(__file__).resolve().parent
BG, WHITE, INK, MUTED, BLUE, RED = "#e9edef", "#ffffff", "#26343e", "#5b6873", "#315d80", "#b5333f"


class TimedApp:
    def __init__(self, root, preview_only=False, size="1060x820"):
        self.root, self.preview_only = root, preview_only
        root.title("웨이퍼 대차 · 시간 이동·회전 측정" + (" · 모의 전용" if preview_only else ""))
        root.geometry(size)
        root.minsize(1000, 800)
        root.configure(bg=BG)
        root.option_add("*Font", ("Malgun Gothic", 10))
        self.worker = TimedWorker(preview_only)
        self.closed = self.pending = False
        self.held = None
        self.saved_records = 0
        self.validated_sequence = None
        self.sequence_summary = tk.StringVar(value="입력 검사 후 환산 시간을 확인해 주세요.")
        self.log_path = BASE / "logs" / f"rotation_{time.time_ns()}.csv"
        self.record_note = tk.StringVar(value="회전 기록 없음 · ENC 순서: M1 앞왼 / M2 앞오 / M3 뒤왼 / M4 뒤오")
        self.log_note = tk.StringVar(value="회전 종료 후 CSV 자동 저장 · 실물 각도는 자동 측정하지 않습니다.")
        self.distance = tk.StringVar(value="1")
        self.calibration = tk.StringVar(value=f"{DEFAULT_SECONDS_PER_M:.5f}")
        self.mode = tk.StringVar(value="preview")
        self.port = tk.StringVar(value="COM7")
        self.confirmed = tk.BooleanVar(value=False)
        self.estimate = tk.StringVar()
        self.status = tk.StringVar(value="미연결 · 기본 모의 확인")
        self.remaining = tk.StringVar(value="— 초")
        self.note = tk.StringVar(value="설정 시간 종료는 실제 거리 도착을 뜻하지 않습니다.")
        self.telemetry = tk.StringVar(value="명령 전송 없음")
        self.saved = tk.StringVar(value="기준: 20% 전진 1m 기록 7건 평균 약 8.54초")
        try:
            settings = json.loads((BASE / "timed-settings.json").read_text(encoding="utf-8"))
            Plan(float(settings["metres"]), float(settings["seconds_per_m"]))
            self.distance.set(str(settings["metres"]))
            self.calibration.set(str(settings["seconds_per_m"]))
        except (OSError, ValueError, KeyError, TypeError):
            pass
        self.build()
        self.distance.trace_add("write", self.update_estimate)
        self.calibration.trace_add("write", self.update_estimate)
        self.update_estimate()
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.GetForegroundWindow.restype = ctypes.c_void_p
        self.user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self.user32.GetAncestor.restype = ctypes.c_void_p
        root.update_idletasks()
        self.hwnd = self.user32.GetAncestor(root.winfo_id(), 2)
        root.bind("<space>", lambda e: self.stop())
        root.bind("<Escape>", lambda e: self.stop("estop"))
        root.bind("<ButtonRelease-1>", self.release_hold, add="+")
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.worker.start()
        self.poll()

    def label(self, parent, text=None, variable=None, size=10, bold=False, color=INK, **kw):
        return tk.Label(parent, text=text, textvariable=variable, bg=parent.cget("bg"), fg=color,
                        font=("Malgun Gothic", size, "bold" if bold else "normal"), **kw)

    def button(self, parent, text, command, primary=False, danger=False):
        return tk.Button(parent, text=text, command=command, bg=RED if danger else BLUE if primary else "#edf2f5",
                         fg=WHITE if primary or danger else INK, relief="solid", bd=1, padx=12, pady=9)

    def build(self):
        top = tk.Frame(self.root, bg="#263e50")
        top.pack(fill="x")
        self.label(top, "웨이퍼 대차  /  시간 이동", size=20, bold=True, color=WHITE).pack(side="left", padx=22, pady=10)
        self.label(top, "시간 전진 / 수동 회전 측정 · 출력 20%", color=WHITE).pack(side="right", padx=22)
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=20, pady=8)
        self.label(body, variable=self.status, size=12, bold=True, color=BLUE).pack(anchor="w", pady=(0, 12))
        columns = tk.Frame(body, bg=BG)
        columns.pack(fill="both", expand=True)
        self.tabs = ttk.Notebook(columns)
        self.tabs.pack(side="left", fill="both", expand=True, padx=(0, 10))
        left = tk.Frame(self.tabs, bg=WHITE, padx=16, pady=8)
        route = tk.Frame(self.tabs, bg=WHITE, padx=16, pady=8)
        self.tabs.add(left, text="단일 동작")
        self.tabs.add(route, text="동작 순서")
        self.label(route, "01  이동·회전 순서", size=14, bold=True).pack(anchor="w")
        self.label(route, "한 줄에 한 동작 · 쉼표 또는 →로 구분 가능", color=MUTED).pack(anchor="w", pady=5)
        editor = tk.Frame(route, bg=WHITE)
        editor.pack(fill="x")
        self.sequence_text = tk.Text(editor, height=4, width=32, font=("Malgun Gothic", 12), wrap="word", undo=True)
        self.sequence_text.pack(side="left", fill="x", expand=True)
        editor_scroll = ttk.Scrollbar(editor, command=self.sequence_text.yview)
        editor_scroll.pack(side="right", fill="y")
        self.sequence_text.configure(yscrollcommand=editor_scroll.set)
        self.sequence_text.insert("1.0", "직진 1m\n우회전 90도\n직진 2m\n좌회전 45도\n직진 0.5m")
        self.sequence_text.edit_modified(False)
        self.sequence_text.bind("<<Modified>>", self.sequence_changed)
        self.validate_button = self.button(route, "입력 검사 / 시간 환산", self.validate_sequence)
        self.validate_button.configure(pady=6)
        self.validate_button.pack(fill="x", pady=6)
        listing = tk.Frame(route, bg=WHITE)
        listing.pack(fill="x")
        self.sequence_list = tk.Listbox(listing, height=3, width=32, font=("Malgun Gothic", 10), exportselection=False)
        self.sequence_list.pack(side="left", fill="x", expand=True)
        list_scroll = ttk.Scrollbar(listing, command=self.sequence_list.yview)
        list_scroll.pack(side="right", fill="y")
        self.sequence_list.configure(yscrollcommand=list_scroll.set)
        self.label(route, variable=self.sequence_summary, wraplength=395, justify="left", color=BLUE).pack(anchor="w", pady=5)
        self.sequence_button = self.button(route, "검사한 순서 실행 · 20%", self.start_sequence, primary=True)
        self.sequence_button.configure(pady=6)
        self.sequence_button.pack(fill="x", pady=4)
        self.label(route, "직진 0.1~5m · 좌/우 5~180도 · 최대 20개\n구동 합계 120초 이내 · 구간마다 정지 대기\n직진: 단일 동작 탭의 초/m / 회전: 45도=1초\n시간 비례 예상값 · 장애물 회피 없음\nSpace·창 전환·연결 종료 → 남은 순서 취소", size=9, color=MUTED, justify="left").pack(anchor="w", pady=5)
        right = tk.Frame(columns, bg=WHITE, padx=20, pady=10)
        right.pack(side="left", fill="both", expand=True)
        self.label(left, "01  이동 설정", size=14, bold=True).pack(anchor="w")
        self.label(left, "목표 거리 (m) · 0.1~5m", color=MUTED).pack(anchor="w", pady=(8, 4))
        self.distance_entry = ttk.Entry(left, textvariable=self.distance, width=20, font=("Malgun Gothic", 16))
        self.distance_entry.pack(fill="x")
        presets = tk.Frame(left, bg=WHITE)
        presets.pack(fill="x", pady=5)
        self.presets = []
        for v in (0.5, 1, 2, 3):
            b = self.button(presets, f"{v}m", lambda n=v: self.distance.set(str(n)))
            b.configure(pady=5)
            b.pack(side="left", expand=True, fill="x", padx=2)
            self.presets.append(b)
        self.label(left, "20%에서 1m당 시간 (초)", color=MUTED).pack(anchor="w", pady=(6, 4))
        self.calibration_entry = ttk.Entry(left, textvariable=self.calibration, font=("Malgun Gothic", 16))
        self.calibration_entry.pack(fill="x")
        self.label(left, variable=self.estimate, size=15, bold=True, color=BLUE).pack(anchor="w", pady=6)
        self.save_button = self.button(left, "현재 설정 저장", self.save_settings)
        self.save_button.configure(pady=5)
        self.save_button.pack(anchor="w")
        self.label(left, variable=self.saved, color=MUTED, wraplength=410, justify="left").pack(anchor="w", pady=4)
        self.label(left, "회전 시간 측정 · 누르는 동안만", size=13, bold=True).pack(anchor="w", pady=(10, 4))
        turns = tk.Frame(left, bg=WHITE)
        turns.pack(fill="x")
        self.hold_buttons = []
        for key, text in (("a", "↶ 좌회전 누르기"), ("d", "↷ 우회전 누르기")):
            button = self.button(turns, text, lambda: None, primary=True)
            button.pack(side="left", fill="x", expand=True, padx=2)
            button.bind("<ButtonPress-1>", lambda e, k=key: self.press_hold(k))
            button.bind("<Leave>", self.release_hold)
            self.hold_buttons.append(button)
        self.label(left, "놓기·버튼 밖으로 이동·창 전환 → 정지\n회전 방향은 실차에서 확인해 주세요.", color=MUTED, justify="left").pack(anchor="w", pady=6)
        self.label(right, "02  시간 진행", size=14, bold=True).pack(anchor="w")
        self.label(right, "자동 이동: 남은 시간 / 누름 회전: 경과 시간", color=MUTED).pack(anchor="w", pady=(8, 3))
        self.label(right, variable=self.remaining, size=26, bold=True, color=BLUE).pack(anchor="w")
        self.progress = ttk.Progressbar(right, maximum=100)
        self.progress.pack(fill="x", pady=6)
        self.start_button = self.button(right, "20% 전진 시작", self.start, primary=True)
        self.start_button.pack(fill="x", pady=5)
        self.label(right, "한 번 클릭 → 시간 회전 / 출력 20%", bold=True).pack(anchor="w", pady=(6, 2))
        rotations = tk.Frame(right, bg=WHITE)
        rotations.pack(fill="x")
        self.rotation_buttons = []
        for row, angle in enumerate((45, 90)):
            for col, (direction, caption) in enumerate((("a", "좌"), ("d", "우"))):
                button = self.button(rotations, f"{caption}{angle}° / {angle//45}초", lambda d=direction, a=angle: self.start_rotation(d, a))
                button.configure(pady=6, padx=3, font=("Malgun Gothic", 9))
                button.grid(row=0, column=row*2+col, sticky="ew", padx=2, pady=2)
                rotations.columnconfigure(row*2+col, weight=1)
                self.rotation_buttons.append(button)
        self.label(right, "사용자 시간 기준 · 양방향 임시 적용 / 실제 각도 미측정", color=MUTED, wraplength=400, justify="left").pack(anchor="w")
        self.label(right, variable=self.note, wraplength=400, justify="left", color=MUTED).pack(anchor="w", pady=5)
        self.label(right, "창·키 입력 시 중단 / 장애물 감지·자동 재출발 없음", size=9, color=MUTED, wraplength=400, justify="left").pack(anchor="w", pady=3)
        connection = tk.Frame(body, bg=WHITE, padx=12, pady=8)
        connection.pack(fill="x", pady=(12, 0))
        self.radios = []
        for value, caption in (("preview", "모의 확인"), ("real", "실차 연결")):
            r = tk.Radiobutton(connection, text=caption, variable=self.mode, value=value, bg=WHITE)
            r.pack(side="left")
            self.radios.append(r)
        self.port_entry = ttk.Entry(connection, textvariable=self.port, width=8)
        self.port_entry.pack(side="left", padx=8)
        self.connect_button = self.button(connection, "연결", self.connect)
        self.connect_button.pack(side="left", padx=4)
        self.button(connection, "연결 종료", lambda: self.worker.request("disconnect")).pack(side="left", padx=4)
        self.confirm_box = tk.Checkbutton(body, text="실차 연결 전: 모터 전원 OFF · 퓨즈/물리 차단 · 주변/전진 공간 확인 · 기존 조작 앱 종료", variable=self.confirmed, bg=BG)
        self.confirm_box.pack(side="bottom", before=columns, anchor="w", pady=6)
        connection.pack_configure(side="bottom", before=columns)
        self.label(right, variable=self.telemetry, color=MUTED, wraplength=400, justify="left").pack(anchor="w", pady=(10, 4))
        self.label(right, variable=self.record_note, size=9, color=INK, wraplength=400, justify="left").pack(anchor="w", pady=(4, 2))
        self.label(right, variable=self.log_note, size=9, color=MUTED, wraplength=400, justify="left").pack(anchor="w")
        footer = tk.Frame(self.root, bg="#f6f8f9", padx=20, pady=10)
        footer.pack(side="bottom", before=body, fill="x")
        self.label(footer, "시간 기반 예상 이동입니다.\n실물 정지·도착을 보증하지 않습니다.", color=MUTED, justify="left").pack(side="left")
        self.button(footer, "즉시 정지 / 연결 종료  Esc", lambda: self.stop("estop"), danger=True).pack(side="right")
        self.button(footer, "정지  Space", self.stop).pack(side="right", padx=12)

    def stop(self, action="stop"):
        self.held = None
        self.worker.request(action)

    def press_hold(self, direction):
        s = self.worker.get_status()
        if s["state"] != "ready" or s["timed_active"] or s["sequence_active"] or s["record_pending"] or self.pending:
            return "break"
        self.root.focus_set()
        self.held = direction
        self.publish_input()
        self.worker.request("hold", direction)
        return "break"

    def release_hold(self, event=None):
        if self.held:
            self.stop()

    def plan(self):
        return Plan(float(self.distance.get()), float(self.calibration.get()))

    def update_estimate(self, *args):
        self.validated_sequence = None
        self.sequence_summary.set("설정 변경 후에는 다시 입력 검사해 주세요.")
        try:
            p = self.plan()
            self.estimate.set(f"{p.metres:g}m → {p.duration:.2f}초 / 20%")
        except ValueError as exc:
            self.estimate.set("입력 확인: " + str(exc))

    def save_settings(self):
        if self.worker.get_status()["state"] not in {"disconnected", "fault"}:
            self.saved.set("연결 종료 후 설정을 저장해 주세요.")
            return
        try:
            p = self.plan()
            path = BASE / "timed-settings.json"
            temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps(dict(metres=p.metres, seconds_per_m=p.seconds_per_m), indent=2), encoding="utf-8")
            temp.replace(path)
            self.saved.set("설정 저장 완료 · 다음 실행에도 적용됩니다.")
        except (ValueError, OSError) as exc:
            self.saved.set("설정 저장 실패: " + str(exc))

    def connect(self):
        if self.mode.get() == "real" and not self.confirmed.get():
            messagebox.showwarning("연결 전 확인", "모터 전원 OFF 및 안전 확인란을 먼저 확인해 주세요.", parent=self.root)
            return
        self.pending = True
        self.root.focus_set()
        self.worker.request("connect", self.mode.get(), self.port.get().strip().upper(), self.confirmed.get())

    def start(self):
        try:
            p = self.plan()
        except ValueError as exc:
            messagebox.showwarning("입력 확인", str(exc), parent=self.root)
            return
        self.root.focus_set()
        self.publish_input()
        self.worker.request("start", p.metres, p.seconds_per_m)
        self.pending = True
        self.start_button.configure(state="disabled")

    def sequence_changed(self, event=None):
        if self.sequence_text.edit_modified():
            self.validated_sequence = None
            self.sequence_summary.set("입력이 바뀌었습니다. 다시 검사해 주세요.")
            self.sequence_text.edit_modified(False)

    def validate_sequence(self):
        self.validated_sequence = None
        self.sequence_list.delete(0, "end")
        try:
            text = self.sequence_text.get("1.0", "end-1c")
            calibration = float(self.calibration.get())
            plans = parse_sequence(text, calibration)
            for i, plan in enumerate(plans, 1):
                self.sequence_list.insert("end", f"{i}. {describe_plan(plan)}")
            self.validated_sequence = (text, calibration)
            self.sequence_summary.set(f"검사 완료 · {len(plans)}개 / 구동 {sum(p.duration for p in plans):.2f}초\n구간 정지 대기는 별도 · 실제 도착/각도 미측정")
        except ValueError as exc:
            self.sequence_summary.set("실행 불가: " + str(exc))

    def start_sequence(self):
        status = self.worker.get_status()
        if self.pending or self.held or status["state"] != "ready" or status["timed_active"] or status["sequence_active"] or status["record_pending"]:
            return
        try:
            current = (self.sequence_text.get("1.0", "end-1c"), float(self.calibration.get()))
        except ValueError:
            return
        if current != self.validated_sequence:
            self.sequence_summary.set("먼저 입력 검사 후 환산 시간을 확인해 주세요.")
            return
        self.root.focus_set()
        self.publish_input()
        self.worker.request("sequence", *current)
        self.pending = True

    def publish_input(self):
        foreground = self.user32.GetForegroundWindow() == self.hwnd
        editing = isinstance(self.root.focus_get(), (tk.Entry, ttk.Entry, tk.Text))
        # 키보드 주행은 이 창에서 생성하지 않습니다. 키를 누르면 시간 이동을 중단합니다.
        keys = {str(v) for v in range(8, 256) if self.user32.GetAsyncKeyState(v) & 0x8000}
        if self.held:
            if not foreground or not self.user32.GetAsyncKeyState(1) & 0x8000:
                self.release_hold()
            else:
                keys.add("hold:" + self.held)
        self.worker.publish(keys, foreground and not editing)

    def poll(self):
        if self.closed:
            return
        self.publish_input()
        s = self.worker.get_status()
        if s["state"] in {"stopping", "moving", "fault", "connecting"}:
            self.pending = False
        active = s["timed_active"] or s["sequence_active"]
        connected = s["state"] not in {"disconnected", "fault"}
        tag = "모의 · 실제 출력 없음" if s["mode"] == "preview" else "실차 · 거리 미측정" if s["mode"] == "real" else "미연결"
        names = {"ready": "시작 대기", "moving": "구동 명령 중", "stopping": "정지 확인 대기", "fault": "오류 · 연결 종료", "connecting": "연결 중", "disconnected": "미연결"}
        self.status.set(tag + " / " + names[s["state"]])
        self.note.set(s["result"] if s["state"] != "fault" else s["message"])
        if s["sequence_total"]:
            self.note.set(s["sequence_note"] + "\n" + self.note.get())
        ready = s["state"] == "ready" and not active and not self.pending and not s["record_pending"]
        self.sequence_text.configure(state="disabled" if active or self.pending else "normal")
        self.validate_button.configure(state="disabled" if active or self.pending else "normal")
        self.sequence_button.configure(state="normal" if ready and self.validated_sequence else "disabled")
        self.remaining.set(f'{s["elapsed"] if s["hold_direction"] and not s["rotation_angle"] else s["remaining"]:.2f} 초' if s["duration"] else "— 초")
        self.progress["value"] = min(100, s["elapsed"] / s["duration"] * 100) if s["duration"] else 0
        self.telemetry.set(f'출력 {s["speed"]}% / {s["tx"]} / ENC {s["enc"] if s["enc"] is not None else "미수신"}')
        self.save_records(s)
        for button in self.hold_buttons:
            button.configure(state="normal" if (s["state"] == "ready" and not active and not self.pending and not s["record_pending"]) or self.held else "disabled")
        for button in self.rotation_buttons:
            button.configure(state="normal" if s["state"] == "ready" and not active and not self.pending and not s["record_pending"] and not self.held else "disabled")
        for widget in [self.distance_entry, self.calibration_entry, *self.presets]:
            widget.configure(state="disabled" if active or self.pending else "normal")
        self.start_button.configure(state="normal" if s["state"] == "ready" and not active and not self.pending else "disabled")
        self.connect_button.configure(state="disabled" if connected or self.pending else "normal")
        self.save_button.configure(state="disabled" if connected or self.pending else "normal")
        self.port_entry.configure(state="disabled" if connected or self.pending else "normal")
        for i, radio in enumerate(self.radios):
            radio.configure(state="disabled" if connected or self.pending or (i == 1 and self.preview_only) else "normal")
        self.poll_id = self.root.after(25, self.poll)

    def save_records(self, status):
        rows = status["records"]
        if not rows:
            return
        row = rows[-1]
        direction = {"a": "좌회전", "d": "우회전", "w": "직진"}[row["direction"]]
        mode = "모의" if row["mode"] == "preview" else "실차"
        delta = row["delta"] if row["delta"] is not None else "미확인(통신/종료 중단)"
        self.record_note.set(f'{len(rows)}건 · {mode} {direction} {row["seconds"]:.3f}초 · ΔENC {delta}\nM1 앞왼 / M2 앞오 / M3 뒤왼 / M4 뒤오 · 실제 각도 미측정')
        if len(rows) != self.saved_records:
            try:
                export_rotation_records(rows, self.log_path)
                self.saved_records = len(rows)
                self.log_note.set("자동 저장: logs/" + self.log_path.name)
            except OSError as exc:
                self.log_note.set("저장 실패 · 기록은 앱에 남아 있습니다: " + str(exc))

    def start_rotation(self, direction, angle):
        status = self.worker.get_status()
        if self.pending or self.held or status["state"] != "ready" or status["timed_active"] or status["sequence_active"] or status["record_pending"]:
            return
        self.root.focus_set()
        self.publish_input()
        self.worker.request("rotate", direction, angle)
        self.pending = True
        for button in self.rotation_buttons:
            button.configure(state="disabled")

    def close(self):
        self.closed = True
        if getattr(self,"poll_id",None):
            self.root.after_cancel(self.poll_id)
        self.worker.publish(set(), False)
        self.worker.quit.set()
        self.worker.join(3)
        self.save_records(self.worker.session.snapshot())
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview-only", action="store_true")
    parser.add_argument("--size", choices=["1060x820", "1000x800"], default="1060x820")
    args = parser.parse_args()
    root = tk.Tk()
    TimedApp(root, args.preview_only, args.size)
    root.mainloop()


if __name__ == "__main__":
    main()
