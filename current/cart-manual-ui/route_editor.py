"""버튼형 경로 편집기. 통신 없이 검증된 명령 문자열만 전달합니다."""
import tkinter as tk
from tkinter import ttk

from timed_drive import DEFAULT_SECONDS_PER_M, parse_sequence, describe_plan


class RouteEditor(tk.Frame):
    def __init__(self, parent, start):
        super().__init__(parent, bg="white", padx=10, pady=8)
        self.start_callback = start
        self.items = []
        self.validated = None
        self.busy = False
        self.enabled_state = None
        self.operation = tk.StringVar(value="직진")
        self.amount = tk.StringVar(value="1")
        self.calibration = tk.StringVar(value=f"{DEFAULT_SECONDS_PER_M:.5f}")
        self.note = tk.StringVar(value="동작을 추가한 뒤 입력 검사를 눌러 주세요.")
        self.progress = tk.StringVar(value="순서 주행 대기 · 실제 거리/각도 미측정")
        self.widgets = []
        self.columnconfigure(1, weight=1)
        left = tk.Frame(self, bg="white")
        left.grid(row=0, column=0, sticky="ns", padx=(0,10))
        middle = tk.Frame(self, bg="white")
        middle.grid(row=0, column=1, sticky="nsew")
        right = tk.Frame(self, bg="white")
        right.grid(row=0, column=2, sticky="ns", padx=(10,0))
        tk.Label(left, text="동작 추가", bg="white", font=("Malgun Gothic",11,"bold")).pack(anchor="w")
        kinds = tk.Frame(left, bg="white")
        kinds.pack(fill="x")
        for i, kind in enumerate(("직진", "좌회전", "우회전", "왼쪽 평행", "오른쪽 평행")):
            b = tk.Radiobutton(kinds, text=kind, value=kind, variable=self.operation, bg="white", command=self.kind_changed)
            b.grid(row=i//3, column=i%3, sticky="w")
            self.widgets.append(b)
        row = tk.Frame(left, bg="white")
        row.pack(fill="x", pady=3)
        entry = ttk.Entry(row, textvariable=self.amount, width=10)
        entry.pack(side="left")
        self.unit = tk.Label(row, text="m · 0.1~5", bg="white")
        self.unit.pack(side="left", padx=6)
        self.widgets.append(entry)
        self.add_button = self.button(left, "＋ 동작 추가", self.add)
        self.add_button.pack(fill="x", pady=3)
        tk.Label(left, text="20% 직진 1m당 시간 (초)", bg="white").pack(anchor="w")
        calibration = ttk.Entry(left, textvariable=self.calibration, width=20)
        calibration.pack(fill="x")
        self.widgets.append(calibration)
        tk.Label(left, text="회전 45도=1초 · 시간 비례 예상\n평행이동: 입력한 초만큼 · 거리 미측정", bg="white", fg="#5b6873", justify="left", font=("Malgun Gothic",9)).pack(anchor="w", pady=3)
        self.listbox = tk.Listbox(middle, height=6, width=28, exportselection=False)
        self.listbox.pack(side="top", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(middle, orient="horizontal", command=self.listbox.xview)
        scrollbar.pack(fill="x")
        self.listbox.configure(xscrollcommand=scrollbar.set)
        actions = tk.Frame(middle, bg="white")
        actions.pack(fill="x")
        for caption, callback in (("↑ 위", lambda:self.move(-1)), ("↓ 아래", lambda:self.move(1)), ("선택 삭제", self.delete), ("전체 비우기", self.clear)):
            self.button(actions, caption, callback).pack(side="left", expand=True, fill="x", padx=1)
        self.validate_button = self.button(right, "입력 검사 / 시간 환산", self.validate)
        self.validate_button.pack(fill="x")
        tk.Label(right, textvariable=self.note, bg="white", fg="#315d80", wraplength=250, justify="left", height=4).pack(fill="x", pady=3)
        self.start_button = tk.Button(right, text="전체 순서 실행 · 20%", command=self.start, bg="#315d80", fg="white", pady=7)
        self.start_button.pack(fill="x")
        tk.Label(right, text="최대 20개 / 구동 합계 120초\nSpace·창 전환 → 남은 순서 취소\n장애물 회피 없음 · 구간마다 정지 대기", bg="white", fg="#5b6873", justify="left", font=("Malgun Gothic",9)).pack(anchor="w", pady=4)
        tk.Label(self, textvariable=self.progress, bg="white", fg="#315d80", anchor="w").grid(row=1,column=0,columnspan=3,sticky="ew",pady=(5,0))
        self.calibration.trace_add("write", self.invalidate)
        self.set_state(False, False)

    def button(self, parent, text, callback):
        button = tk.Button(parent, text=text, command=callback, pady=4, bg="#edf2f5")
        self.widgets.append(button)
        return button

    def kind_changed(self):
        if self.operation.get() in {"왼쪽 평행", "오른쪽 평행"}:
            self.unit.configure(text="초 · 0.5~60")
            self.amount.set("1")
            return
        turn = self.operation.get() != "직진"
        self.unit.configure(text="도 · 5~180" if turn else "m · 0.1~5")
        self.amount.set("90" if turn else "1")

    def invalidate(self, *args):
        self.validated = None
        self.enabled_state = None
        self.start_button.configure(state="disabled")
        self.note.set("목록/기준 변경 · 다시 검사해 주세요.")

    def render(self, selected=None):
        self.listbox.delete(0,"end")
        for i, item in enumerate(self.items,1):
            self.listbox.insert("end", f"{i}. {item}")
        if selected is not None and self.items:
            self.listbox.selection_set(selected)
            self.listbox.see(selected)
        self.invalidate()

    def add(self):
        if self.busy:
            return
        unit = "초" if self.operation.get() in {"왼쪽 평행", "오른쪽 평행"} else "m" if self.operation.get()=="직진" else "도"
        item = f"{self.operation.get()} {self.amount.get().strip()}{unit}"
        try:
            parse_sequence("\n".join([*self.items,item]),float(self.calibration.get()))
        except ValueError as exc:
            self.note.set("추가 불가: "+str(exc))
            return
        self.items.append(item)
        self.render(len(self.items)-1)

    def move(self, offset):
        if self.busy or not self.listbox.curselection():
            return
        i = self.listbox.curselection()[0]
        j = i+offset
        if 0 <= j < len(self.items):
            self.items[i], self.items[j] = self.items[j], self.items[i]
            self.render(j)

    def delete(self):
        if not self.busy and self.listbox.curselection():
            i = self.listbox.curselection()[0]
            self.items.pop(i)
            self.render(min(i,len(self.items)-1) if self.items else None)

    def clear(self):
        if not self.busy:
            self.items.clear()
            self.render()

    def validate(self):
        if self.busy:
            return
        self.invalidate()
        try:
            text, rate = "\n".join(self.items), float(self.calibration.get())
            plans = parse_sequence(text,rate)
            self.validated = (text,rate)
            self.listbox.delete(0,"end")
            for i,plan in enumerate(plans,1):
                self.listbox.insert("end",f"{i}. {describe_plan(plan)}")
            self.note.set(f"검사 완료 · {len(plans)}개 / {sum(p.duration for p in plans):.2f}초\n정지 대기 별도 · 도착/각도 미검증")
        except ValueError as exc:
            self.note.set("실행 불가: "+str(exc))

    def start(self):
        if not self.busy and self.validated and str(self.start_button.cget("state")) == "normal":
            if self.validated != ("\n".join(self.items),float(self.calibration.get())):
                self.invalidate()
                return
            self.start_callback(*self.validated)

    def set_state(self, ready, busy, progress=None):
        self.busy = busy
        state = (bool(ready and self.validated and not busy),bool(busy))
        if state != self.enabled_state:
            for widget in self.widgets:
                widget.configure(state="disabled" if busy else "normal")
            self.start_button.configure(state="normal" if state[0] else "disabled")
            self.enabled_state = state
        if progress is not None and progress != self.progress.get():
            self.progress.set(progress)
