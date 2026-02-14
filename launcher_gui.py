import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox
from tkinter.scrolledtext import ScrolledText


APP_TITLE = "FireMail 一键启动器"
CREATE_NO_WINDOW = 0x08000000
ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def get_runtime_root() -> str:
    # In PyInstaller onefile mode, scripts should be resolved beside the exe.
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


ROOT_DIR = get_runtime_root()


class FiremailLauncher:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("860x560")
        self.root.minsize(820, 520)

        self.backend_proc: subprocess.Popen | None = None
        self.frontend_proc: subprocess.Popen | None = None

        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()

        self.status_text = tk.StringVar(value="就绪")
        self.backend_text = tk.StringVar(value="后端状态: 未运行")
        self.frontend_text = tk.StringVar(value="前端状态: 未运行")

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)
        self.root.after(100, self._drain_log_queue)
        self.root.after(1000, self._poll_process_state)

    def _build_ui(self) -> None:
        top = tk.Frame(self.root, padx=12, pady=10)
        top.pack(fill=tk.X)

        tk.Label(top, text="FireMail 前后端启动面板", font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w")
        tk.Label(top, textvariable=self.backend_text, anchor="w").pack(fill=tk.X, pady=1)
        tk.Label(top, textvariable=self.frontend_text, anchor="w").pack(fill=tk.X, pady=1)
        tk.Label(top, textvariable=self.status_text, anchor="w", fg="#1b6ac9").pack(fill=tk.X, pady=4)

        btn1 = tk.Frame(self.root, padx=12, pady=4)
        btn1.pack(fill=tk.X)
        btn2 = tk.Frame(self.root, padx=12, pady=4)
        btn2.pack(fill=tk.X)

        tk.Button(btn1, text="启动后端", width=16, command=self.start_backend).pack(side=tk.LEFT, padx=4)
        tk.Button(btn1, text="启动前端", width=16, command=self.start_frontend).pack(side=tk.LEFT, padx=4)
        tk.Button(btn1, text="启动全部", width=16, command=self.start_all).pack(side=tk.LEFT, padx=4)

        tk.Button(btn2, text="停止后端", width=16, command=self.stop_backend).pack(side=tk.LEFT, padx=4)
        tk.Button(btn2, text="停止前端", width=16, command=self.stop_frontend).pack(side=tk.LEFT, padx=4)
        tk.Button(btn2, text="停止全部", width=16, command=self.stop_all).pack(side=tk.LEFT, padx=4)
        tk.Button(btn2, text="清空日志", width=16, command=self.clear_log).pack(side=tk.LEFT, padx=4)

        log_frame = tk.Frame(self.root, padx=12, pady=8)
        log_frame.pack(fill=tk.BOTH, expand=True)

        split = tk.PanedWindow(log_frame, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        split.pack(fill=tk.BOTH, expand=True)

        backend_panel = tk.Frame(split)
        frontend_panel = tk.Frame(split)
        split.add(backend_panel, minsize=300)
        split.add(frontend_panel, minsize=300)

        tk.Label(backend_panel, text="后端输出", anchor="w").pack(fill=tk.X)
        self.backend_log_text = ScrolledText(backend_panel, wrap=tk.WORD, font=("Consolas", 10))
        self.backend_log_text.pack(fill=tk.BOTH, expand=True)
        self.backend_log_text.configure(state=tk.DISABLED)

        tk.Label(frontend_panel, text="前端输出", anchor="w").pack(fill=tk.X)
        self.frontend_log_text = ScrolledText(frontend_panel, wrap=tk.WORD, font=("Consolas", 10))
        self.frontend_log_text.pack(fill=tk.BOTH, expand=True)
        self.frontend_log_text.configure(state=tk.DISABLED)

    def _append_log(self, channel: str, line: str) -> None:
        self.log_queue.put((channel, line))

    def _drain_log_queue(self) -> None:
        drained = False
        while True:
            try:
                channel, line = self.log_queue.get_nowait()
            except queue.Empty:
                break
            drained = True
            target = self.backend_log_text if channel == "backend" else self.frontend_log_text
            target.configure(state=tk.NORMAL)
            target.insert(tk.END, line)
            target.see(tk.END)
            target.configure(state=tk.DISABLED)

        if drained:
            self._refresh()
        self.root.after(100, self._drain_log_queue)

    def _spawn(self, name: str, script_name: str) -> subprocess.Popen:
        script_path = os.path.join(ROOT_DIR, script_name)
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"找不到脚本: {script_path}")

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0

        proc = subprocess.Popen(
            ["cmd.exe", "/c", script_path],
            cwd=ROOT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            creationflags=CREATE_NO_WINDOW,
            startupinfo=startupinfo
        )
        self._append_log(name, f"进程已启动，PID={proc.pid}\n")
        threading.Thread(target=self._stream_output, args=(name, proc), daemon=True).start()
        return proc

    @staticmethod
    def _decode_output(raw: bytes) -> str:
        for enc in ("utf-8", "gb18030", "cp936"):
            try:
                return ANSI_ESCAPE_RE.sub("", raw.decode(enc))
            except UnicodeDecodeError:
                continue
        return ANSI_ESCAPE_RE.sub("", raw.decode("utf-8", errors="replace"))

    def _stream_output(self, name: str, proc: subprocess.Popen) -> None:
        if proc.stdout is None:
            return
        for raw in iter(proc.stdout.readline, b""):
            line = self._decode_output(raw)
            if not line:
                break
            self._append_log(name, line)

        code = proc.wait()
        self._append_log(name, f"进程退出，退出码={code}\n")

    @staticmethod
    def _alive(proc: subprocess.Popen | None) -> bool:
        return proc is not None and proc.poll() is None

    @staticmethod
    def _kill_tree(proc: subprocess.Popen | None) -> None:
        if proc is None or proc.poll() is not None:
            return
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )

    def _refresh(self) -> None:
        self.backend_text.set("后端状态: 运行中" if self._alive(self.backend_proc) else "后端状态: 未运行")
        self.frontend_text.set("前端状态: 运行中" if self._alive(self.frontend_proc) else "前端状态: 未运行")

    def _poll_process_state(self) -> None:
        self._refresh()
        self.root.after(1000, self._poll_process_state)

    def start_backend(self) -> None:
        if self._alive(self.backend_proc):
            self.status_text.set("后端已在运行")
            return
        try:
            self.backend_proc = self._spawn("backend", "一键启动后端.bat")
            self.status_text.set("后端启动命令已发送")
            self._refresh()
        except Exception as exc:
            messagebox.showerror("启动失败", str(exc))

    def start_frontend(self) -> None:
        if self._alive(self.frontend_proc):
            self.status_text.set("前端已在运行")
            return
        try:
            self.frontend_proc = self._spawn("frontend", "一键启动前端.bat")
            self.status_text.set("前端启动命令已发送")
            self._refresh()
        except Exception as exc:
            messagebox.showerror("启动失败", str(exc))

    def start_all(self) -> None:
        self.start_backend()
        self.start_frontend()
        self.status_text.set("前后端启动命令已发送")

    def stop_backend(self) -> None:
        self._kill_tree(self.backend_proc)
        self.backend_proc = None
        self.status_text.set("后端已停止")
        self._append_log("backend", "用户已停止后端进程\n")
        self._refresh()

    def stop_frontend(self) -> None:
        self._kill_tree(self.frontend_proc)
        self.frontend_proc = None
        self.status_text.set("前端已停止")
        self._append_log("frontend", "用户已停止前端进程\n")
        self._refresh()

    def stop_all(self) -> None:
        self.stop_backend()
        self.stop_frontend()
        self.status_text.set("前后端均已停止")

    def clear_log(self) -> None:
        self.backend_log_text.configure(state=tk.NORMAL)
        self.backend_log_text.delete("1.0", tk.END)
        self.backend_log_text.configure(state=tk.DISABLED)
        self.frontend_log_text.configure(state=tk.NORMAL)
        self.frontend_log_text.delete("1.0", tk.END)
        self.frontend_log_text.configure(state=tk.DISABLED)

    def on_exit(self) -> None:
        if self._alive(self.backend_proc) or self._alive(self.frontend_proc):
            answer = messagebox.askyesno("退出确认", "检测到服务仍在运行，是否停止全部后退出？")
            if answer:
                self.stop_all()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    FiremailLauncher(root)
    root.mainloop()


if __name__ == "__main__":
    if sys.platform != "win32":
        raise SystemExit("仅支持 Windows 系统。")
    main()
