import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import json
import os
import sys
import winsound
from PIL import Image, ImageTk, ImageGrab
import cv2
import numpy as np
import ctypes
import pygetwindow as gw
import win32gui
import win32process
import win32api


def get_data_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_FILE = os.path.join(get_data_dir(), 'config.json')
TEMPLATE_FILE = os.path.join(get_data_dir(), 'template.png')


def get_window_at_point(x, y):
    try:
        hwnd = win32gui.WindowFromPoint((x, y))
        if hwnd:
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
            except:
                pid = None
            root = win32gui.GetAncestor(hwnd, 2)
            title = win32gui.GetWindowText(root) if root else None
            return title or None, pid
    except:
        pass
    return None, None


class WindowPicker:
    def __init__(self, parent, callback):
        self.parent = parent
        self.callback = callback
        self.done = False

        self.parent.iconify()
        self.parent.update()

        sw = parent.winfo_screenwidth()
        sh = parent.winfo_screenheight()

        self.info = tk.Toplevel(parent)
        self.info.overrideredirect(True)
        self.info.attributes('-topmost', True)
        self.info.configure(bg='#222222')
        self.info.geometry(f"340x70+{(sw-340)//2}+80")
        self.info.attributes('-alpha', 0.92)

        tk.Label(self.info, text="将鼠标移到目标窗口后单击左键",
                font=('Microsoft YaHei', 13),
                bg='#222222', fg='white').pack(expand=True)

        self.info.lift()
        self.info.focus_force()
        self.info.update()

        threading.Thread(target=self.click_wait_loop, daemon=True).start()

    def click_wait_loop(self):
        while True:
            if self.done:
                return
            if win32api.GetAsyncKeyState(0x01) & 0x8000:
                while win32api.GetAsyncKeyState(0x01) & 0x8000:
                    if self.done:
                        return
                    time.sleep(0.01)
                x, y = win32api.GetCursorPos()
                title, pid = get_window_at_point(x, y)
                self.done = True
                try:
                    self.info.destroy()
                except:
                    pass
                self.parent.after(0, lambda t=title, p=pid: self.finish_pick(t, p))
                return
            time.sleep(0.01)

    def finish_pick(self, title, pid):
        self.restore()
        self.callback(title, pid)

    def restore(self):
        self.parent.deiconify()
        self.parent.lift()
        self.parent.focus_force()

    def cleanup(self):
        self.done = True
        try:
            self.info.destroy()
        except:
            pass
        self.restore()

class RegionSelector:
    def __init__(self, parent, callback):
        self.parent = parent
        self.callback = callback
        self.start_x = None
        self.start_y = None
        self.end_x = None
        self.end_y = None
        self.dragging = False
        self.done = False

        self.parent.iconify()
        self.parent.update()

        sw = parent.winfo_screenwidth()
        sh = parent.winfo_screenheight()

        self.screenshot = ImageGrab.grab()

        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.attributes('-topmost', True)
        self.win.geometry(f"{sw}x{sh}+0+0")

        self.canvas = tk.Canvas(self.win, highlightthickness=0, cursor='crosshair')
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.tk_image = ImageTk.PhotoImage(self.screenshot)
        self.canvas.create_image(0, 0, image=self.tk_image, anchor=tk.NW)

        self.canvas.create_text(
            sw // 2, 30,
            text="按住鼠标左键拖拽选择识别区域，松开完成选择 | 按 ESC 取消",
            fill='white', font=('Microsoft YaHei', 13)
        )

        self.win.bind('<Escape>', self.on_escape)
        self.win.lift()
        self.win.focus_force()
        self.win.update()

        self.parent.after(100, self.poll_mouse)

    def poll_mouse(self):
        if self.done:
            return
        state = ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000
        pt = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))

        if state:
            if not self.dragging:
                self.dragging = True
                self.start_x = pt.x
                self.start_y = pt.y
                self.canvas.delete('rect')
                self.rect_id = self.canvas.create_rectangle(
                    self.start_x, self.start_y, pt.x, pt.y,
                    outline='red', width=3, tags='rect'
                )
            else:
                if self.rect_id:
                    self.canvas.coords(self.rect_id, self.start_x, self.start_y, pt.x, pt.y)
            self.parent.after(30, self.poll_mouse)
        else:
            if self.dragging:
                self.dragging = False
                self.done = True
                x1, y1 = min(self.start_x, pt.x), min(self.start_y, pt.y)
                x2, y2 = max(self.start_x, pt.x), max(self.start_y, pt.y)
                try:
                    self.win.destroy()
                except:
                    pass
                if x2 - x1 < 10 or y2 - y1 < 10:
                    self.parent.after(0, self.restore)
                    return
                self.parent.after(0, lambda: self.do_capture(x1, y1, x2, y2))
            else:
                self.parent.after(50, self.poll_mouse)

    def do_capture(self, x1, y1, x2, y2):
        try:
            region = self.screenshot.crop((x1, y1, x2, y2))
            self.callback(region)
        except Exception as e:
            messagebox.showerror("错误", f"截取区域失败: {e}")
        self.restore()

    def restore(self):
        self.parent.deiconify()
        self.parent.lift()
        self.parent.focus_force()

    def on_escape(self, event):
        self.done = True
        try:
            self.win.destroy()
        except:
            pass
        self.restore()


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("识图响应")
        self.root.geometry("520x580")
        self.root.resizable(False, False)

        self.monitoring = False
        self.monitor_thread = None
        self.template_image = None
        self.template_cv = None
        self.template_gray = None
        self.tk_preview = None

        self.picker = None
        self.similarity = tk.DoubleVar(value=80.0)
        self.play_sound = tk.BooleanVar(value=True)
        self.selected_window = tk.StringVar()
        self.selected_pid = tk.StringVar()
        self.status_var = tk.StringVar(value="就绪")
        self.match_count = 0

        self.setup_ui()
        self.load_config()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_ui(self):
        main = ttk.Frame(self.root, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text="目标窗口（可选）", font=('', 10, 'bold')).pack(anchor=tk.W)
        wf = ttk.Frame(main)
        wf.pack(fill=tk.X, pady=(3, 0))
        self.win_display = ttk.Entry(wf, textvariable=self.selected_window, state='readonly', width=35)
        self.win_display.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(wf, text="点击选择", command=self.pick_window, width=10).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(wf, text="清除", command=self.clear_window, width=6).pack(side=tk.LEFT, padx=(5, 0))
        pif = ttk.Frame(main)
        pif.pack(fill=tk.X, pady=(2, 10))
        self.pid_lbl = ttk.Label(pif, textvariable=self.selected_pid, foreground='#888', font=('', 9))
        self.pid_lbl.pack(side=tk.LEFT)
        self.bind_status_lbl = ttk.Label(pif, text="未绑定", foreground='#999', font=('', 9))
        self.bind_status_lbl.pack(side=tk.RIGHT)

        ttk.Label(main, text="识别图片", font=('', 10, 'bold')).pack(anchor=tk.W)
        tf = ttk.Frame(main)
        tf.pack(fill=tk.X, pady=(3, 5))
        ttk.Button(tf, text="框选截图", command=self.start_capture, width=12).pack(side=tk.LEFT)
        ttk.Button(tf, text="加载图片", command=self.load_image, width=12).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(tf, text="清除", command=self.clear_template, width=8).pack(side=tk.LEFT, padx=(5, 0))

        self.preview_lbl = ttk.Label(
            main, text="未设置识别图片\n点击「框选截图」或「加载图片」",
            relief=tk.SUNKEN, anchor=tk.CENTER,
            background='#f5f5f5', foreground='#999'
        )
        self.preview_lbl.pack(fill=tk.X, pady=(0, 10), ipady=35)

        ttk.Label(main, text="识别相似度", font=('', 10, 'bold')).pack(anchor=tk.W)
        sf = ttk.Frame(main)
        sf.pack(fill=tk.X, pady=(3, 10))
        self.sim_scale = ttk.Scale(sf, from_=0, to=100, variable=self.similarity,
                                    orient=tk.HORIZONTAL, command=self.on_sim_change)
        self.sim_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.sim_val_lbl = ttk.Label(sf, text="80%", width=5)
        self.sim_val_lbl.pack(side=tk.LEFT, padx=(10, 0))

        self.sound_cb = ttk.Checkbutton(main, text="匹配成功时播放提示音", variable=self.play_sound)
        self.sound_cb.pack(anchor=tk.W, pady=(0, 10))

        cf = ttk.Frame(main)
        cf.pack(fill=tk.X, pady=(10, 5))
        self.btn_start = ttk.Button(cf, text="开始监控", command=self.start_monitoring, width=15)
        self.btn_start.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_stop = ttk.Button(cf, text="停止监控", command=self.stop_monitoring, width=15, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT)

        ttk.Separator(main, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(10, 5))
        status_f = ttk.Frame(main)
        status_f.pack(fill=tk.X)
        ttk.Label(status_f, textvariable=self.status_var, foreground='#666').pack(side=tk.LEFT)
        self.match_count_lbl = ttk.Label(status_f, text="", foreground='green')
        self.match_count_lbl.pack(side=tk.RIGHT)

    def pick_window(self):
        if self.monitoring:
            self.stop_monitoring()

        self.picker = WindowPicker(self.root, self.on_window_selected)

    def on_window_selected(self, title, pid):
        if title and title != '识图响应':
            self.selected_window.set(title)
            self.selected_pid.set(f"PID: {pid}" if pid else "")
            self.bind_status_lbl.config(text="已绑定")
            self.status_var.set(f"已绑定窗口: {title}  (PID: {pid})")
        else:
            self.selected_window.set('')
            self.selected_pid.set('')
            self.bind_status_lbl.config(text="未绑定", foreground='#999')
            self.status_var.set("未选择有效窗口（将全屏识别）")
        self.root.lift()
        self.root.focus_force()

    def clear_window(self):
        self.selected_window.set('')
        self.selected_pid.set('')
        self.bind_status_lbl.config(text="未绑定", foreground='#999')
        self.status_var.set("已清除窗口绑定（将全屏识别）")

    def start_capture(self):
        if self.monitoring:
            self.stop_monitoring()
        RegionSelector(self.root, self.on_region_captured)

    def on_region_captured(self, screenshot):
        self.template_image = screenshot
        arr = np.array(screenshot)
        self.template_cv = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        self.template_gray = cv2.cvtColor(self.template_cv, cv2.COLOR_BGR2GRAY)
        self.update_preview(screenshot)
        self.status_var.set(f"已截取区域: {screenshot.width}\u00d7{screenshot.height}")

    def load_image(self):
        path = filedialog.askopenfilename(title="选择图片", filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp")])
        if not path:
            return
        try:
            img = Image.open(path)
            self.template_image = img
            arr = np.array(img.convert('RGB'))
            self.template_cv = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            self.template_gray = cv2.cvtColor(self.template_cv, cv2.COLOR_BGR2GRAY)
            self.update_preview(img)
            self.status_var.set(f"已加载图片: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("错误", f"加载图片失败: {e}")

    def clear_template(self):
        self.template_image = None
        self.template_cv = None
        self.template_gray = None
        self.tk_preview = None
        self.preview_lbl.config(text="未设置识别图片\n点击「框选截图」或「加载图片」", image='')
        self.match_count = 0
        self.match_count_lbl.config(text="")
        self.status_var.set("已清除识别图片")

    def update_preview(self, img):
        max_w, max_h = 460, 80
        w, h = img.size
        ratio = min(max_w / w, max_h / h, 1.0)
        nw, nh = int(w * ratio), int(h * ratio)
        img_small = img.resize((nw, nh), Image.LANCZOS)
        self.tk_preview = ImageTk.PhotoImage(img_small)
        self.preview_lbl.config(image=self.tk_preview, text='', compound=tk.NONE)

    def on_sim_change(self, val):
        self.sim_val_lbl.config(text=f"{int(float(val))}%")

    def start_monitoring(self):
        if self.template_cv is None:
            messagebox.showwarning("提示", "请先设置识别图片")
            return

        self.monitoring = True
        self.match_count = 0
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.status_var.set("监控中...")
        self.match_count_lbl.config(text="")

        self.monitor_thread = threading.Thread(target=self.monitoring_loop, daemon=True)
        self.monitor_thread.start()

    def stop_monitoring(self):
        self.monitoring = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.status_var.set("已停止")

    def monitoring_loop(self):
        threshold = self.similarity.get() / 100.0
        sound_on = self.play_sound.get()
        win_title = self.selected_window.get()
        target_pid_str = self.selected_pid.get()
        template = self.template_gray.copy()
        th, tw = template.shape[:2]

        while self.monitoring:
            try:
                bbox = None
                if win_title and target_pid_str:
                    try:
                        pid_str = target_pid_str.replace('PID: ', '')
                        target_pid = int(pid_str)
                        hwnds = []
                        def enum_cb(hwnd, _):
                            try:
                                _, found = win32process.GetWindowThreadProcessId(hwnd)
                                if found == target_pid and win32gui.IsWindowVisible(hwnd):
                                    hwnds.append(hwnd)
                            except:
                                pass
                            return True
                        win32gui.EnumWindows(enum_cb, None)
                        if hwnds:
                            hwnd = hwnds[0]
                            rect = win32gui.GetWindowRect(hwnd)
                            bbox = (rect[0], rect[1], rect[2], rect[3])
                    except:
                        try:
                            wins = gw.getWindowsWithTitle(win_title)
                            if wins and wins[0].visible:
                                w = wins[0]
                                if w.width > 0 and w.height > 0:
                                    bbox = (w.left, w.top, w.left + w.width, w.top + w.height)
                        except:
                            pass

                screen = ImageGrab.grab(bbox=bbox)
                screen_cv = cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2GRAY)

                if screen_cv.shape[0] < th or screen_cv.shape[1] < tw:
                    time.sleep(0.3)
                    continue

                result = cv2.matchTemplate(screen_cv, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)

                if max_val >= threshold:
                    self.match_count += 1
                    if sound_on:
                        winsound.Beep(1200, 150)
                    self.root.after(0, self.on_match, max_val)
                    time.sleep(0.8)
                else:
                    self.root.after(0, lambda v=float(max_val): self.status_var.set(f"监控中... 最高相似度: {v:.0%}"))

                time.sleep(0.3)

            except Exception as e:
                self.root.after(0, lambda: self.status_var.set(f"错误: {str(e)[:40]}"))
                time.sleep(1)

    def on_match(self, similarity):
        self.status_var.set(f"\u2713 匹配成功! 相似度: {similarity:.1%}")
        self.match_count_lbl.config(text=f"已匹配: {self.match_count} 次")

    def load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                self.similarity.set(cfg.get('similarity', 80))
                self.play_sound.set(cfg.get('play_sound', True))
                self.selected_window.set(cfg.get('window', ''))
                self.selected_pid.set(cfg.get('pid', ''))
                if self.selected_window.get() and self.selected_pid.get():
                    self.bind_status_lbl.config(text="已绑定")
                else:
                    self.bind_status_lbl.config(text="未绑定", foreground='#999')

                if os.path.exists(TEMPLATE_FILE):
                    self.template_image = Image.open(TEMPLATE_FILE)
                    arr = np.array(self.template_image.convert('RGB'))
                    self.template_cv = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                    self.template_gray = cv2.cvtColor(self.template_cv, cv2.COLOR_BGR2GRAY)
                    self.update_preview(self.template_image)
        except:
            pass

    def save_config(self):
        try:
            cfg = {
                'similarity': self.similarity.get(),
                'play_sound': self.play_sound.get(),
                'window': self.selected_window.get(),
                'pid': self.selected_pid.get()
            }
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            if self.template_image:
                self.template_image.save(TEMPLATE_FILE)
        except:
            pass

    def on_close(self):
        self.monitoring = False
        if self.picker:
            self.picker.cleanup()
        time.sleep(0.2)
        self.save_config()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    App().run()
