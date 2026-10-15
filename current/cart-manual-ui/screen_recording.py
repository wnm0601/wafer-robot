"""앱 HWND만 녹화하는 별도 작업 스레드. 데스크톱 전체 캡처 대체 경로 없음."""
import ctypes
import pathlib
import threading
import time


class WindowRecorder:
    def __init__(self):
        self.lock = threading.Lock()
        self.event = threading.Event()
        self.thread = None
        self.info = dict(active=False, message="앱 창만 녹화 · 무음 AVI · 최대 30분", path=None, frames=0)

    def snapshot(self):
        with self.lock:
            return dict(self.info)

    def update(self, **values):
        with self.lock:
            self.info.update(values)

    def start(self, hwnd, directory, capture=None):
        if self.thread and self.thread.is_alive():
            return False
        self.event.clear()
        self.update(active=True, message="녹화 준비 중 · 앱 창만 / 무음", path=None, frames=0)
        self.thread = threading.Thread(target=self.run, args=(hwnd,pathlib.Path(directory),capture),daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.event.set()

    def run(self, hwnd, directory, capture):
        writer, path, frames, failure = None, None, 0, None
        try:
            import cv2
            import numpy as np
            from PIL import ImageGrab
            if capture is None:
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                user32.IsWindow.argtypes = [ctypes.c_void_p]
                user32.IsIconic.argtypes = [ctypes.c_void_p]
                def capture():
                    if not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
                        raise RuntimeError("창 닫힘/최소화로 녹화 종료")
                    return ImageGrab.grab(window=hwnd)
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"cart_screen_{time.time_ns()}.avi"
            size, started = None, time.monotonic()
            fps = 5
            while not self.event.is_set() and time.monotonic()-started < 1800:
                image = capture().convert("RGB")
                if image.width < 2 or image.height < 2:
                    raise RuntimeError("유효한 앱 화면을 받지 못했습니다.")
                rgb = np.asarray(image)
                if size is None:
                    size = (image.width//2*2, image.height//2*2)
                    writer = cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*"MJPG"),fps,size)
                    if not writer.isOpened():
                        raise RuntimeError("AVI 저장 장치를 열지 못했습니다.")
                    started = time.monotonic()
                scale = min(size[0]/image.width,size[1]/image.height)
                resized = cv2.resize(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR), (max(1,int(image.width*scale)),max(1,int(image.height*scale))))
                frame = np.zeros((size[1],size[0],3),dtype=np.uint8)
                y,x = (size[1]-resized.shape[0])//2,(size[0]-resized.shape[1])//2
                frame[y:y+resized.shape[0],x:x+resized.shape[1]] = resized
                target = int((time.monotonic()-started)*fps)+1
                for _ in range(max(1,target-frames)):
                    writer.write(frame)
                    frames += 1
                self.update(message=f"● 녹화 중 {frames/fps:.1f}초 · 앱 화면 / 무음",path=str(path),frames=frames)
                self.event.wait(max(0,started+frames/fps-time.monotonic()))
        except Exception as exc:
            failure = str(exc)
        finally:
            if writer is not None:
                writer.release()
            saved = path is not None and path.exists() and path.stat().st_size > 0 and frames > 0
            if failure:
                message = "녹화 종료/오류: "+failure+(" · 일부 영상 저장: "+str(path) if saved else " · 저장 영상 없음")
            else:
                message = "저장 완료: "+str(path) if saved else "녹화 취소 · 저장 영상 없음"
            self.update(active=False,message=message,path=str(path) if saved else None,frames=frames)
