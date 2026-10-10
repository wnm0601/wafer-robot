"""Tk map and manual controls for the firmware-backed simulation."""
from __future__ import annotations

import json
import math
from pathlib import Path
import time
import tkinter as tk
from tkinter import ttk, messagebox

from .manual_simulation import ManualSimulation
from .manual_commissioning import PHYSICAL_BLOCKERS, compare_measurement
from .manual_hardware import ManualHardware, open_manual_serial
from .manual_first_drive import parse_command_percent


class SimulatorWindow:
    def __init__(self, root_path: Path, *, ui_test=False, hardware_ui_test=False, real_backend=None):
        self.sim = real_backend if real_backend is not None else ManualSimulation(root_path,load_saved=not ui_test)
        if ui_test:
            self.sim.saved_path = root_path/'data/output/manual_speed_ui_fixture_settings.json'
        self.hardware_ui_test=hardware_ui_test
        self.fixture_counts=[0]*4
        self.fixture_motion=False
        if hardware_ui_test:
            from .firmware_simulator import FirmwareSimulatorWire
            self.sim.close()
            wire=FirmwareSimulatorWire(root_path,manual_fixture=True)
            wire.power_feedback(False)
            self.sim=ManualHardware(root_path,wire=wire,percent=10,mapping_verified=True)
            wire.power_feedback(True)
            self.sim.drive.select_mode('vector')
            self.fixture_wire=wire
        self.root_path = root_path
        self.root = tk.Tk()
        self.root.title("웨이퍼 대차 · 수동 조작 / 모의 시험")
        self.root.geometry("1120x720")
        self.root.minsize(940, 720)
        self.root.configure(bg="#edf1f4")
        self.closing = False
        self.held = set()
        self.blocked_keys = set()
        self.pointer_key = None
        self.edit_point = None
        self.error = ""
        self.ui_test = ui_test
        self.ui_test_result = None
        self.transport_fault=False
        self.connection_text=tk.StringVar(value="PC 전용 MANUAL_ONLY 시험 · 실제 COM 없음" if hardware_ui_test else "현재 연결: PC 펌웨어 시뮬레이션")
        self.banner_text=tk.StringVar(value='펌웨어 C++ 제어 코드 실행 · 가상 주행 모델 · 실차 미연결')
        if real_backend is not None:
            self.connection_text.set('실제 Arduino 연결 · 가상 주행 아님 · 위치 미추정')
            self.banner_text.set('실차 수동시험 · 전원/물리 급정지 미감지 · 복구 전 조작 해제/재연결 · 자동주행/카메라 안전 미연결')
            if self.sim.drive.keyboard_hold:
                self.banner_text.set('실차 키 홀드 · 최초 안전 확인 완료 · 누르면 동작/놓으면 정지 · 4륜 잠금 · 전원/물리 급정지 미감지')
        self.status = tk.StringVar(value="정지 · 수동 준비 후 조작하세요")
        self.telemetry = tk.StringVar()
        self.wheel_text = tk.StringVar()
        self.point_text = tk.StringVar()
        self.mode = tk.StringVar(value=self.sim.drive.mode)
        self.motor = tk.IntVar(value=1)
        self.percent = tk.DoubleVar(value=self.sim.drive.percent)
        self.speed_input = tk.StringVar(value=str(self.sim.drive.percent))
        self.speed_text = tk.StringVar()
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background="#edf1f4")
        style.configure("TLabel", background="#edf1f4", foreground="#203342", font=("Malgun Gothic",10))
        style.configure("TButton", font=("Malgun Gothic",10), padding=4)
        style.configure("TRadiobutton", background="#edf1f4", font=("Malgun Gothic",10))
        style.configure("TLabelframe", background="#edf1f4")
        style.configure("TLabelframe.Label", background="#edf1f4", font=("Malgun Gothic",10,"bold"))
        style.configure("Title.TLabel", font=("Malgun Gothic",19,"bold"))
        style.configure("Muted.TLabel", foreground="#627584", font=("Malgun Gothic",9))
        style.configure("Status.TLabel", background="#dce9e1", padding=9, font=("Malgun Gothic",10,"bold"))
        outer = ttk.Frame(self.root,padding=14)
        outer.pack(fill="both",expand=True)
        ttk.Label(outer,text="대차 수동 조작 · 주행 시험",style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer,textvariable=self.banner_text,
                  style="Muted.TLabel").pack(anchor="w",pady=(2,10))
        tools=ttk.Frame(outer)
        tools.pack(fill="x",pady=(0,6))
        ttk.Label(tools,textvariable=self.connection_text,style="Muted.TLabel").pack(side="left")
        ttk.Button(tools,text="실차 연결 / 모의 전환",command=self.connection_dialog).pack(side="right",padx=3)
        ttk.Button(tools,text="실측 오차 기록",command=self.measurement_dialog).pack(side="right",padx=3)
        footer=ttk.Frame(outer)
        footer.pack(side="bottom",fill="x")
        body = ttk.Frame(outer)
        body.pack(fill="both",expand=True)
        body.columnconfigure(0,weight=1)
        body.rowconfigure(0,weight=1)
        map_panel = ttk.Frame(body)
        map_panel.grid(row=0,column=0,sticky="nsew",padx=(0,14))
        bar = ttk.Frame(map_panel)
        bar.pack(fill="x",pady=(0,7))
        ttk.Label(bar,text="부스 지도",font=("Malgun Gothic",12,"bold")).pack(side="left")
        ttk.Button(bar,text="출발지 설정",command=lambda:self.start_edit("home")).pack(side="right",padx=3)
        ttk.Button(bar,text="목적지 설정",command=lambda:self.start_edit("destination")).pack(side="right",padx=3)
        self.canvas = tk.Canvas(map_panel,bg="#fafcfd",highlightthickness=1,highlightbackground="#c3cdd5")
        self.canvas.pack(fill="both",expand=True)
        self.canvas.bind("<Configure>",lambda _:self.draw_map())
        self.canvas.bind("<ButtonPress-1>",self.on_map_click)
        ttk.Label(map_panel,textvariable=self.point_text,style="Muted.TLabel").pack(anchor="w",pady=(5,0))
        ttk.Label(map_panel,text="테이블 길이 1.8m: 사용자 제공 / 지도·운동 모델: 가상 / 대차 외곽: CAD 참고",
                  style="Muted.TLabel",wraplength=690).pack(anchor="w",pady=(3,0))
        sidebar = ttk.Frame(body,width=300)
        sidebar.grid(row=0,column=1,sticky="ns")
        mode_box=ttk.LabelFrame(sidebar,text="조작 모드",padding=7)
        mode_box.pack(fill="x",pady=(0,6))
        for name,label in (("vector","4륜 주행"),("single","한 모터씩 시험")):
            ttk.Radiobutton(mode_box,text=label,value=name,variable=self.mode,
                            command=self.change_mode).pack(side="left",padx=3)
        motor_box=ttk.LabelFrame(sidebar,text="모터 선택 · 위치는 같은 번호 배선 시 추정",padding=7)
        motor_box.pack(fill="x",pady=(0,6))
        for channel,position in ((1,'왼쪽 뒤'),(2,'오른쪽 뒤'),(3,'왼쪽 앞'),(4,'오른쪽 앞')):
            ttk.Radiobutton(motor_box,text=f"M{channel} · {position}(추정)",value=channel,variable=self.motor,
                command=lambda c=channel:self.change_motor(c)).grid(row=(channel-1)//2,column=(channel-1)%2,sticky='w',padx=3)
        speed_box=ttk.LabelFrame(sidebar,text="속도 조절 · 출력 명령 %",padding=7)
        speed_box.pack(fill="x",pady=(0,6))
        self.speed_scale=ttk.Scale(speed_box,from_=1,to=self.sim.drive.max_percent,variable=self.percent,
                                  command=self.on_speed_slider)
        self.speed_scale.pack(fill="x")
        speed_row=ttk.Frame(speed_box)
        speed_row.pack(fill="x",pady=4)
        self.speed_entry=ttk.Spinbox(speed_row,from_=1,to=self.sim.drive.max_percent,width=5,textvariable=self.speed_input)
        self.speed_entry.pack(side="left")
        ttk.Label(speed_row,text=" %").pack(side="left")
        self.speed_apply=ttk.Button(speed_row,text="정지 중 적용",command=self.apply_speed)
        self.speed_apply.pack(side="right")
        self.speed_input.trace_add('write',lambda *_:self.update_speed_text())
        self.speed_entry.bind('<Return>',lambda _:self.apply_speed())
        ttk.Label(speed_box,textvariable=self.speed_text,style="Muted.TLabel",wraplength=265).pack(anchor="w")
        self.update_speed_text()
        self.pad=ttk.LabelFrame(sidebar,text="키 또는 버튼을 누르는 동안 이동",padding=7)
        self.pad.pack(fill="x",pady=(0,6))
        self.pad_buttons={}
        for key,label,row,col in (("q","↶ Q",0,0),("w","↑ W",0,1),("e","↷ E",0,2),
                                   ("a","← A",1,0),("s","↓ S",1,1),("d","D →",1,2),
                                   ("up","M ↑",2,0),("down","M ↓",2,2)):
            button=tk.Button(self.pad,text=label,font=("Malgun Gothic",11),bg="#ffffff",fg="#203342",
                             activebackground="#d9e8f2",relief="solid",bd=1,width=6,pady=5)
            button.grid(row=row,column=col,padx=3,pady=3,sticky="ew")
            button.bind("<ButtonPress-1>",lambda e,k=key:self.pointer_press(e,k))
            button.bind("<ButtonRelease-1>",self.pointer_release)
            button.bind("<Leave>",self.pointer_release)
            self.pad_buttons[key]=button
        for col in range(3):self.pad.columnconfigure(col,weight=1)
        controls=ttk.Frame(sidebar)
        controls.pack(fill="x")
        for text,action,row,col in (("안전 확인 완료" if self.sim.drive.keyboard_hold else "수동 준비",self.prepare,0,0),("정지 · Space",self.stop,0,1),
                ("비상정지 · X",lambda:self.run(self.sim.drive.estop),1,0),
                ("위치 초기화",lambda:self.run(self.sim.reset_pose),1,1)):
            button=ttk.Button(controls,text=text,command=action)
            button.grid(row=row,column=col,sticky="ew",padx=2,pady=3)
            if row == 0 and col == 0:self.prepare_button=button
        for col in range(2):controls.columnconfigure(col,weight=1)
        ttk.Label(footer,textvariable=self.telemetry,font=("Consolas",11)).pack(anchor="w",pady=(8,3))
        ttk.Label(footer,textvariable=self.wheel_text,style="Muted.TLabel").pack(anchor="w")
        ttk.Label(footer,textvariable=self.status,style="Status.TLabel",wraplength=1200).pack(fill="x",pady=(5,0))
        self.root.bind("<KeyPress>",self.on_press)
        self.root.bind("<KeyRelease>",self.on_release)
        self.root.bind("<FocusOut>",self.on_focus_out)
        self.root.bind("<FocusIn>",self.on_focus_in)
        self.root.bind("<Unmap>",lambda _:self.stop())
        self.root.bind("<ButtonRelease-1>",self.pointer_release,add="+")
        self.root.protocol("WM_DELETE_WINDOW",self.close)
        self.root.after(25,self.tick)
        self.refresh()
        if ui_test:self.root.after(300,self.test_begin)

    def connection_dialog(self):
        self.stop()
        dialog=tk.Toplevel(self.root)
        dialog.title("실차 수동 연결 · 출력 전 준비 확인")
        dialog.geometry(f"680x500+{self.root.winfo_x()+40}+{self.root.winfo_y()+40}")
        dialog.transient(self.root)
        dialog.grab_set()
        box=ttk.Frame(dialog,padding=16)
        box.pack(fill="both",expand=True)
        ttk.Label(box,text="실차 수동 연결 · 업로드와 하드웨어 시험은 별도",
                  font=("Malgun Gothic",12,"bold")).pack(anchor="w")
        for reason in PHYSICAL_BLOCKERS:
            ttk.Label(box,text="• "+reason,wraplength=630).pack(anchor="w",pady=6)
        row=ttk.Frame(box)
        row.pack(fill="x",pady=8)
        ttk.Label(row,text="시험 예정 COM 포트").pack(side="left")
        port=tk.StringVar(value="")
        ttk.Entry(row,textvariable=port,width=15).pack(side="left",padx=8)
        confirmed=tk.BooleanVar(value=False)
        ttk.Checkbutton(box,text="담당자 준비, 출력 firmware 설정/업로드, 전원·비상정지 확인을 마쳤습니다",
                        variable=confirmed).pack(anchor='w',pady=5)
        result=tk.StringVar(value="실차 연결 버튼은 실제 COM을 엽니다. 연결만으로 ARM하거나 주행하지 않습니다.")
        def connect():
            wire=None
            try:
                if self.ui_test:raise ValueError('UI 시험에서는 실제 포트를 열지 않습니다')
                if getattr(self.sim,'is_physical',False):raise ValueError('먼저 모의 모드로 전환해 기존 COM을 닫으세요')
                if not self.sim.is_stopped():raise ValueError('완전히 정지한 뒤 연결하세요')
                measurements=json.loads((self.root_path/'src/wafer_cart_mapping/config/measurements.json').read_text(encoding='utf-8-sig'))
                wire=open_manual_serial(port.get(),operator_confirmed=confirmed.get())
                backend=ManualHardware(self.root_path,wire=wire,percent=1,
                                      mapping_verified=measurements.get('firmware_wheel_mapping_verified') is True)
                old=self.sim
                self.sim=backend
                old.close()
                self.mode.set('single');self.motor.set(1);self.percent.set(1)
                self.speed_input.set('1')
                self.speed_scale.configure(to=self.sim.drive.max_percent)
                self.speed_entry.configure(to=self.sim.drive.max_percent)
                self.held.clear();self.pointer_key=None;self.transport_fault=False;self.error=''
                self.connection_text.set('실차 수동 연결 · '+port.get().upper()+' · 위치 미추정')
                self.banner_text.set('실차 모드 · 수동 출력 가능 · 자동주행/카메라 안전 제어 미연결')
                dialog.destroy();self.refresh()
            except Exception as error:
                if wire is not None and not getattr(self.sim,'is_physical',False):wire.close()
                result.set('연결하지 못했습니다: '+str(error))
        def simulate():
            try:
                backend=ManualSimulation(self.root_path)
                old=self.sim;self.sim=backend;old.close()
                self.held.clear();self.pointer_key=None;self.transport_fault=False;self.error=''
                self.mode.set('vector');self.motor.set(1);self.percent.set(self.sim.drive.percent)
                self.speed_input.set(str(self.sim.drive.percent))
                self.speed_scale.configure(to=self.sim.drive.max_percent)
                self.speed_entry.configure(to=self.sim.drive.max_percent)
                self.connection_text.set('현재 연결: PC 펌웨어 시뮬레이션')
                self.banner_text.set('펌웨어 C++ 제어 코드 실행 · 가상 주행 모델 · 실차 미연결')
                dialog.destroy();self.refresh()
            except Exception as error:result.set(str(error))
        ttk.Button(row,text="실차 연결",command=connect).pack(side="left")
        ttk.Button(box,text="실차 해제 / 모의 모드",command=simulate).pack(anchor='w',pady=8)
        ttk.Label(box,textvariable=result,wraplength=630).pack(anchor="w",pady=8)
        ttk.Button(box,text="닫기 · 정지 유지",command=dialog.destroy).pack(anchor="e")

    def measurement_dialog(self):
        if getattr(self.sim,'is_physical',False):
            self.error='실차 위치 추정이 연결되지 않아 가상 결과와 비교하지 않습니다';self.refresh();return
        if not self.sim.is_stopped():
            self.run(lambda: (_ for _ in ()).throw(ValueError("완전히 정지한 뒤 실측을 기록하세요")))
            return
        self.stop()
        # Freeze the model result at dialog creation; do not compare a moving pose.
        snapshot=self.sim.snapshot()
        distance=snapshot['distance_m']
        home_yaw=self.sim.booth['home'][2]
        yaw=snapshot['pose']['yaw_rad']-home_yaw
        degrees=math.degrees(math.atan2(math.sin(yaw),math.cos(yaw)))
        dialog=tk.Toplevel(self.root)
        dialog.title("실측 비교 기록 · 자동 교정 없음")
        dialog.geometry(f"640x430+{self.root.winfo_x()+40}+{self.root.winfo_y()+40}")
        dialog.transient(self.root)
        dialog.grab_set()
        box=ttk.Frame(dialog,padding=16)
        box.pack(fill="both",expand=True)
        ttk.Label(box,text=f"현재 가상 이동 경로 {distance:.4f} m / 시작 대비 방향 {degrees:+.2f}°").pack(anchor="w")
        ttk.Label(box,text="같은 명령·시간·속도로 시험한 실물 값을 입력하세요.\n거리: 누적 경로 길이 / 각도: 순 방향 변화(-180~180°), 여러 바퀴 회전은 제외",
                  wraplength=600,style="Muted.TLabel").pack(anchor="w",pady=8)
        unit=tk.StringVar(value="m")
        row=ttk.Frame(box);row.pack(fill="x")
        ttk.Radiobutton(row,text="이동거리 m",value="m",variable=unit).pack(side="left")
        ttk.Radiobutton(row,text="방향 변화 deg",value="deg",variable=unit).pack(side="left",padx=10)
        measured=tk.StringVar(); source=tk.StringVar(); repeats=tk.StringVar(value="1")
        for label,var in (("실측값 (미측정이면 비워 두세요)",measured),("측정 방법·동일 시험 조건",source),("반복 시험 횟수",repeats)):
            ttk.Label(box,text=label).pack(anchor="w",pady=(8,0))
            ttk.Entry(box,textvariable=var).pack(fill="x")
        result=tk.StringVar(value="미측정 값은 저장하지 않습니다. 기존 모델값·엔코더 설정은 변경되지 않습니다.")
        def save():
            try:
                value=float(measured.get())
                if unit.get()=='deg' and not -180<=value<=180:
                    raise ValueError("방향 변화는 -180~180°로 입력해 주세요")
                record=compare_measurement(predicted=distance if unit.get()=='m' else degrees,
                    measured=value,unit=unit.get(),source=source.get(),repeated_trials=int(repeats.get()))
                record.update(recorded_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),snapshot=snapshot,
                              model=dict(self.sim.plant.model),command=self.sim.last_command)
                path=self.root_path/('data/output/measurement_ui_fixture.json' if self.ui_test
                                     else 'data/manual_measurement_comparisons.json')
                records=json.loads(path.read_text(encoding='utf-8')) if path.is_file() else []
                if not isinstance(records,list):raise ValueError("기존 실측 기록 형식을 확인하세요")
                records.append(record)
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(json.dumps(records,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
                result.set(f"저장했습니다. 오차(가상-실측): {record['error_predicted_minus_measured']:+.4f} {unit.get()} · 자동 교정 없음")
            except (ValueError,OSError) as error:result.set("저장하지 못했습니다: "+str(error))
        ttk.Label(box,textvariable=result,wraplength=600).pack(anchor="w",pady=10)
        ttk.Button(box,text="비교·저장",command=save).pack(side="left")
        ttk.Button(box,text="닫기",command=dialog.destroy).pack(side="right")
        self.measurement_form={'measured':measured,'source':source,'repeats':repeats,
                               'result':result,'save':save}

    def run(self,action):
        try:
            action()
            if not self.sim.drive.latched and not self.transport_fault:self.error=""
        except Exception as error:
            self.error=self.sim.drive.first_error or str(error)
            print('수동 조작 오류: '+self.error,flush=True)
        self.refresh()

    def update_speed_text(self):
        draft = self.speed_input.get()
        if getattr(self.sim,'is_physical',False):
            self.speed_text.set(f"입력 {draft}% / 적용 {self.sim.drive.percent}%\n실차 m/s 미교정 · 펌웨어 상한 적용")
        else:self.speed_text.set(f"입력 {draft}% / 적용 {self.sim.drive.percent}%\n모의 전용 · 실차 속도 실측값 아님")

    def on_speed_slider(self, value):
        self.speed_input.set(str(round(float(value))))

    def apply_speed(self):
        def apply():
            if self.transport_fault or self.sim.drive.latched:
                raise ValueError('오류/비상정지 잠금 상태에서는 변경할 수 없습니다')
            percent = parse_command_percent(self.speed_input.get(), self.sim.drive.max_percent)
            self.sim.set_speed(percent)
            self.percent.set(percent)
            self.speed_input.set(str(percent))
        self.run(apply)

    def change_mode(self):
        self.stop()
        self.run(lambda:self.sim.drive.select_mode(self.mode.get()))
        self.mode.set(self.sim.drive.mode)

    def change_motor(self,channel):
        self.stop()
        self.run(lambda:self.sim.drive.select_motor(channel))

    def prepare(self):
        if self.sim.drive.keyboard_hold:
            return  # CLI CONNECT already provided the one-time safety confirmation.
        if self.sim.gateway.expected_mode == 'MANUAL_UNMONITORED':
            self.stop()
            if not messagebox.askyesno('실차 수동 준비 · 전원 미감지',
                    '물리 비상정지 해제 및 모터 전원을 직접 확인하셨습니까?\n'
                    '프로그램은 전원 차단/복구를 감지하지 못합니다.\n'
                    '차단 시 키를 놓고 창을 종료한 뒤, 복구 후 재연결하십시오.\n'
                    '주변과 선택 모터를 확인한 경우에만 준비하십시오.', parent=self.root):
                return
            self.root.focus_set()
            # Modal focus loss stops the drive; wait for real FocusIn before prepare.
            self.root.after(50, lambda:self.run(self.sim.drive.prepare))
            return
        self.edit_point=None
        self.sim.collision_stop=False
        self.run(self.sim.drive.prepare)

    def stop(self):
        self.blocked_keys.update(self.held)
        self.held.clear()
        self.pointer_key=None
        self.run(self.sim.drive.stop)

    def start_edit(self,name):
        def select():
            if not self.sim.is_stopped():raise ValueError("완전히 정지한 뒤 지점을 설정하세요")
            self.edit_point=name
        self.run(select)

    def transform(self):
        w,h=self.canvas.winfo_width(),self.canvas.winfo_height()
        scale=max(1,min(w-60,h-60)/(2*self.sim.booth['half_extent']))
        return w/2,h/2,scale

    def screen(self,x,y):
        cx,cy,scale=self.transform()
        return cx+x*scale,cy-y*scale

    def on_map_click(self,event):
        if not self.edit_point:return
        cx,cy,scale=self.transform()
        name=self.edit_point
        def update():
            self.sim.set_point(name,(event.x-cx)/scale,(cy-event.y)/scale)
            self.edit_point=None
        self.run(update)

    def on_press(self,event):
        key=event.keysym.lower()
        if key=='space':self.stop();return "break"
        if key=='x':self.held.clear();self.run(self.sim.drive.estop);return "break"
        if key=='escape':self.stop();self.edit_point=None;return "break"
        if event.widget in (self.speed_entry,self.speed_scale):return
        if key in {'w','s','a','d','q','e','up','down'}:
            if key in self.blocked_keys:return "break"
            self.held.add(key)
            self.sim.drive.set_keys(self.held)
            self.run(self.sim.drive.step)
            if self.sim.drive.last_command:self.sim.last_command=self.sim.drive.last_command
            return "break"

    def on_release(self,event):
        key=event.keysym.lower()
        blocked=key in self.blocked_keys
        self.blocked_keys.discard(key)
        if key in self.held or blocked:
            self.held.discard(key)
            self.sim.drive.set_keys(self.held)
            self.run(self.sim.drive.step)
            return "break"

    def pointer_press(self,event,key):
        self.pointer_key=key
        self.on_press(type('Event',(),{'keysym':key,'widget':event.widget})())
        return "break"

    def pointer_release(self,event=None):
        if self.pointer_key:
            key,self.pointer_key=self.pointer_key,None
            self.on_release(type('Event',(),{'keysym':key})())

    def on_focus_out(self,_event):
        def check():
            if not self.closing and self.root.focus_get() is None:
                self.blocked_keys.update(self.held)
                self.held.clear()
                self.pointer_key=None
                self.run(lambda:self.sim.drive.set_keys(set(),focused=False))
        self.root.after(10,check)

    def on_focus_in(self,_event):
        if not self.sim.drive.focused:
            self.held.clear()
            self.sim.drive.set_keys(set(),focused=True)

    def tick(self):
        if self.closing:return
        try:
            if not self.transport_fault:self.sim.tick()
            if self.hardware_ui_test and not self.transport_fault:
                for i,value in enumerate(self.sim.plant.outputs):
                    if value:self.fixture_counts[i]+=1 if value>0 else -1;self.fixture_motion=True
                self.fixture_wire.encoder_feedback(self.fixture_counts)
            if self.sim.collision_stop:self.held.clear();self.pointer_key=None
        except Exception as error:
            self.transport_fault=True
            self.blocked_keys.update(self.held)
            self.held.clear()
            try:self.sim.drive.abort(error)
            except Exception:pass
            self.error=self.sim.drive.first_error or str(error)
            print('수동 조작 최초 오류: '+self.error,flush=True)
        self.refresh()
        self.root.after(25,self.tick)

    def refresh(self):
        if self.closing:return
        self.update_speed_text()
        p=self.sim.plant.pose
        physical=getattr(self.sim,'is_physical',False)
        self.telemetry.set(('실차 위치·거리·각도 미추정 · 상태 '+str(self.sim.device_status[1] if self.sim.device_status else '연결 대기')
                            if physical else f"X {p.x:+.3f} m    Y {p.y:+.3f} m    방향 {math.degrees(p.yaw):+.1f}°    이동 {self.sim.plant.distance:.3f} m"))
        prefix="바퀴 출력/가상 ENC  "
        if physical:
            age=time.monotonic()-self.sim.last_encoder['received_monotonic_s'] if self.sim.last_encoder else None
            prefix=('수신 중단 · 마지막 출력/ENC ' if self.transport_fault else '실제 출력/ENC ')
            if age is not None:prefix+=f'({age:.1f}s 전) '
        self.wheel_text.set(prefix+"   ".join(f"M{i+1}: {v:+d} / {self.sim.plant.counts[i]}" for i,v in enumerate(self.sim.plant.outputs)))
        a,b=self.sim.booth['home'],self.sim.booth['destination']
        self.point_text.set('모의 부스 배치 참고용 · 실차 출발지/목적지 좌표 미등록' if physical else f"출발 ({a[0]:.2f}, {a[1]:.2f}) m · 목적지 ({b[0]:.2f}, {b[1]:.2f}) m · +X 오른쪽 / +Y 위쪽")
        if self.sim.drive.latched:self.status.set("오류/비상정지 잠금 · 최초 원인: "+(self.sim.drive.first_error or self.error or '원인 미수신')+" · 모터 전원 OFF 후 앱 재연결")
        elif self.error:self.status.set("확인 필요 · "+self.error)
        elif self.sim.collision_stop:self.status.set("충돌 방지 정지 · "+str(self.sim.plant.collision)+" · 반대 방향으로 수동 재준비하세요")
        elif self.edit_point:self.status.set(("출발지" if self.edit_point=='home' else "목적지")+"를 지도에서 클릭하세요 · Esc 취소")
        elif self.sim.drive.moving:self.status.set("수동 주행 · "+str(self.sim.drive.last_command))
        elif any(self.sim.plant.outputs):self.status.set("감속 중 · 바퀴 출력이 0이 될 때까지 기다리세요")
        elif self.sim.drive.prepared:self.status.set("수동 준비 · 키 또는 방향 버튼을 누르세요")
        elif self.sim.drive.keyboard_hold and self.sim.drive.session_confirmed:self.status.set("키 홀드 대기 · 선택 모터만 ↑/↓ · 키 해제/Space 정지 · X 비상정지")
        else:self.status.set("정지 · 최근 명령 "+str(self.sim.last_command)+" · 다음 조작은 수동 준비")
        self.prepare_button.configure(text='안전 확인 완료' if self.sim.drive.keyboard_hold else '수동 준비',
            state='disabled' if self.sim.drive.keyboard_hold else 'normal')
        locked=(self.transport_fault or self.sim.drive.latched or self.sim.drive.moving
                or self.sim.drive.prepared or bool(self.sim.drive.keys) or any(self.sim.plant.outputs))
        self.speed_entry.configure(state="disabled" if locked else "normal")
        self.speed_scale.configure(state="disabled" if locked else "normal")
        self.speed_apply.configure(state="disabled" if locked else "normal")
        for key,button in self.pad_buttons.items():
            if (self.sim.drive.mode=='single') == (key in ('up','down')):button.grid()
            else:button.grid_remove()
        self.draw_map()

    def draw_map(self):
        c=self.canvas
        c.delete('all')
        half=self.sim.booth['half_extent']
        for i in range(-int(half),int(half)+1):
            c.create_line(*self.screen(i,-half),*self.screen(i,half),fill="#e2e8ed")
            c.create_line(*self.screen(-half,i),*self.screen(half,i),fill="#e2e8ed")
        c.create_rectangle(*self.screen(-half,half),*self.screen(half,-half),outline="#9aabb9",width=2)
        c.create_text(13,15,text="가상 MAP  ·  1 grid = 1m",anchor='nw',fill="#627584",font=("Malgun Gothic",9))
        for obs in self.sim.booth['obstacles']:
            x,y,w,h=obs['x'],obs['y'],obs['width'],obs['depth']
            c.create_rectangle(*self.screen(x-w/2,y+h/2),*self.screen(x+w/2,y-h/2),fill="#c9d3dc" if obs['kind']=='wall' else '#d8bb92',outline='#536777',width=2)
            c.create_text(*self.screen(x,y),text=obs['name'],fill='#263846',font=("Malgun Gothic",10,'bold'))
        trail=[n for point in self.sim.plant.trail for n in self.screen(*point)]
        if len(trail)>=4:c.create_line(*trail,fill='#c58531',width=2)
        for name,label,color in (('home','출발','#276bd1'),('destination','목적지','#ca4040')):
            x,y,_=self.sim.booth[name]
            sx,sy=self.screen(x,y)
            r=9
            if name=='home' and math.hypot(self.sim.plant.pose.x-x,self.sim.plant.pose.y-y)<.3:
                r=max(16,self.transform()[2]*.46)
            c.create_oval(sx-r,sy-r,sx+r,sy+r,outline=color,width=3)
            c.create_text(sx-16 if name=='home' else sx,sy+r+17,text=label,fill=color,font=("Malgun Gothic",10,'bold'))
        if getattr(self.sim,'is_physical',False):
            c.create_text(13,42,text='실차 위치 미연결 · 대차 위치는 표시하지 않습니다',anchor='nw',fill='#b23b28',font=('Malgun Gothic',11,'bold'))
            return
        poly=[n for point in self.sim.plant.corners() for n in self.screen(*point)]
        c.create_polygon(*poly,fill='#167b80',outline='#12494c',width=2)
        p=self.sim.plant.pose
        c.create_line(*self.screen(p.x,p.y),*self.screen(p.x+.32*math.cos(p.yaw),p.y+.32*math.sin(p.yaw)),arrow='last',fill='white',width=3)
        length=max(abs(v[0]) for v in self.sim.plant.footprint)
        width=max(abs(v[1]) for v in self.sim.plant.footprint)
        for i,(x,y) in enumerate(((length,width),(length,-width),(-length,width),(-length,-width))):
            wx=p.x+x*math.cos(p.yaw)-y*math.sin(p.yaw)
            wy=p.y+x*math.sin(p.yaw)+y*math.cos(p.yaw)
            sx,sy=self.screen(wx,wy)
            c.create_oval(sx-4,sy-4,sx+4,sy+4,fill='#f7c849' if self.sim.plant.outputs[i] else '#263c4b',outline='white')
        c.create_text(*self.screen(p.x+.65,p.y+.3),text='대차',fill='#12585c',font=("Malgun Gothic",9,'bold'))

    def test_begin(self):
        # Real Tk controls with PC-only firmware: no physical COM is opened.
        original_percent=self.sim.drive.percent
        self.speed_input.set('7')
        self.speed_apply.invoke()
        assert self.sim.drive.percent==7 and self.percent.get()==7
        self.speed_input.set('nan')
        self.speed_apply.invoke()
        assert self.sim.drive.percent==7 and self.error
        self.on_speed_slider('9.2')
        self.speed_apply.invoke()
        assert self.sim.drive.percent==9
        self.prepare()
        assert str(self.speed_apply.cget('state'))=='disabled'
        self.stop()
        self.speed_input.set(str(original_percent))
        self.speed_apply.invoke()
        assert self.sim.drive.percent==original_percent
        self.connection_dialog()
        self.root.update_idletasks()
        dialogs=[w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel)]
        assert len(dialogs)==1 and dialogs[0].winfo_width()==680
        dialogs[0].destroy()
        if self.hardware_ui_test:
            self.root.focus_force();self.prepare();self.root.event_generate('<KeyPress-w>')
            self.root.after(1600,self.test_release)
            return
        self.measurement_dialog()
        self.root.update_idletasks()
        dialogs=[w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel)]
        assert len(dialogs)==1 and dialogs[0].winfo_width()==640
        self.measurement_form['measured'].set('nan')
        self.measurement_form['source'].set('UI test fixture; not physical measurement')
        self.measurement_form['save']()
        assert self.measurement_form['result'].get().startswith('저장하지 못했습니다')
        self.measurement_form['measured'].set('0.1')
        self.measurement_form['save']()
        assert self.measurement_form['result'].get().startswith('저장했습니다')
        dialogs[0].destroy()
        self.root.focus_force()
        self.before=self.sim.plant.pose.x
        self.prepare()
        self.root.event_generate('<KeyPress-w>')
        self.root.after(1600,self.test_release)

    def test_release(self):
        self.root.event_generate('<KeyRelease-w>')
        self.root.after(400,self.test_check)

    def test_check(self):
        try:
            if self.hardware_ui_test:
                if not self.fixture_motion:raise AssertionError('manual backend UI did not send motion')
            elif self.sim.plant.pose.x-self.before<0.05:raise AssertionError('UI held key did not move plant')
            if not self.sim.is_stopped():raise AssertionError('key release did not settle to STOP')
            stopped_x=self.sim.plant.pose.x
            self.root.event_generate('<KeyPress-w>')
            self.root.event_generate('<KeyRelease-w>')
            self.ui_test_result={"result":"PASS","tk_key_hold_s":1.6,"release_stopped":True,
                "speed_controls":"numeric/slider apply, invalid input rejection, prepared lock: PASS",
                "dialogs_rendered":True,"measurement_input_save_test":"not applicable" if self.hardware_ui_test else "synthetic fixture only",
                "snapshot":self.sim.snapshot(),"x_after_no_reprepare":self.sim.plant.pose.x}
            if self.sim.plant.pose.x!=stopped_x:raise AssertionError('auto restart')
        except Exception as error:
            self.ui_test_result={"result":"FAIL","error":str(error),"snapshot":self.sim.snapshot()}
        target=self.root_path/('data/output/manual_hardware_ui_fixture.json' if self.hardware_ui_test else 'data/output/manual_simulator_ui_current.json')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(self.ui_test_result,ensure_ascii=False,indent=2),encoding='utf-8')
        self.close()

    def close(self):
        if self.closing:return
        self.closing=True
        try:self.sim.drive.stop()
        finally:self.sim.close();self.root.destroy()

    def mainloop(self):
        self.root.mainloop()
        if self.ui_test_result:
            print(json.dumps(self.ui_test_result,ensure_ascii=False))
            return 0 if self.ui_test_result['result']=='PASS' else 1
        return 0
