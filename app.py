"""
家纺情报 · 桌面助手
依赖: Python 自带 (tkinter, webbrowser, subprocess)
用法: python app.py
"""
import tkinter as tk
from tkinter import ttk, scrolledtext
import subprocess, webbrowser, threading, sys, os, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run_cmd(cmd: list, timeout=120) -> tuple[str, str]:
    """运行命令，返回 (stdout, stderr)"""
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
    return r.stdout, r.stderr


class App:
    def __init__(self):
        self.win = tk.Tk()
        self.win.title("🏠 家纺情报助手")
        self.win.geometry("860x620")
        self.win.configure(bg="#0f172a")

        # 样式
        self.bg = "#0f172a"
        self.fg = "#e2e8f0"
        self.accent = "#3b82f6"
        self.font = ("Segoe UI", 10)
        self.font_mono = ("Consolas", 10)

        # ── 顶部输入区 ──
        top = tk.Frame(self.win, bg=self.bg)
        top.pack(fill="x", padx=14, pady=(14, 6))

        tk.Label(top, text="关键词", fg="#64748b", bg=self.bg, font=self.font).pack(side="left")
        self.keyword_entry = tk.Entry(top, width=22, font=self.font,
                                      bg="#1e293b", fg=self.fg, insertbackground=self.fg,
                                      relief="flat", bd=8)
        self.keyword_entry.pack(side="left", padx=(6, 14))
        self.keyword_entry.insert(0, "cooling sheets")

        tk.Label(top, text="排序", fg="#64748b", bg=self.bg, font=self.font).pack(side="left")
        self.sort_var = tk.StringVar(value="likes")
        sort_menu = ttk.Combobox(top, textvariable=self.sort_var, values=["likes", "comments"],
                                 width=8, font=self.font, state="readonly")
        sort_menu.pack(side="left", padx=(6, 14))

        tk.Label(top, text="条数", fg="#64748b", bg=self.bg, font=self.font).pack(side="left")
        self.limit_var = tk.StringVar(value="10")
        limit_spin = tk.Spinbox(top, from_=3, to=50, textvariable=self.limit_var,
                                 width=4, font=self.font, bg="#1e293b", fg=self.fg,
                                 buttonbackground="#334155", relief="flat", bd=6)
        limit_spin.pack(side="left", padx=(6, 14))

        self.search_btn = tk.Button(top, text="🔍 搜索", command=self.search,
                                    bg=self.accent, fg="white", font=("Segoe UI", 10, "bold"),
                                    relief="flat", padx=16, pady=4, cursor="hand2")
        self.search_btn.pack(side="left")

        # ── 结果区域 ──
        result_frame = tk.Frame(self.win, bg=self.bg)
        result_frame.pack(fill="both", expand=True, padx=14, pady=6)

        # 列标题
        hdr = tk.Frame(result_frame, bg="#1e293b")
        hdr.pack(fill="x")
        for i, (w, t) in enumerate([(38, "#"), (60, "来源"), (400, "标题"), (60, "互动"), (300, "链接")]):
            lbl = tk.Label(hdr, text=t, width=w, anchor="w", fg="#64748b", bg="#1e293b",
                           font=("Segoe UI", 9, "bold"))
            lbl.pack(side="left", padx=(0, 4))

        # 可滚动列表
        list_frame = tk.Frame(result_frame, bg=self.bg)
        list_frame.pack(fill="both", expand=True)

        scrollbar = tk.Scrollbar(list_frame, orient="vertical")
        self.listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set,
                                  bg="#0f172a", fg=self.fg, font=self.font_mono,
                                  selectbackground="#1e293b", selectforeground="#60a5fa",
                                  relief="flat", bd=0, highlightthickness=0,
                                  exportselection=False)
        scrollbar.config(command=self.listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.listbox.pack(fill="both", expand=True)

        self.listbox.bind("<Double-Button-1>", self.open_selected)
        self.listbox.bind("<Return>", self.open_selected)

        # 状态栏
        self.status_bar = tk.Frame(self.win, bg="#1e293b")
        self.status_bar.pack(fill="x")

        self.status_label = tk.Label(self.status_bar, text="就绪", fg="#64748b",
                                      bg="#1e293b", font=("Segoe UI", 9))
        self.status_label.pack(side="left", padx=10, pady=4)

        # 底部按钮
        btn_frame = tk.Frame(self.status_bar, bg="#1e293b")
        btn_frame.pack(side="right", padx=6)

        self.llm_btn = tk.Button(btn_frame, text="🤖 LLM 分析", command=self.run_llm,
                                  bg="#334155", fg="#94a3b8", font=("Segoe UI", 9),
                                  relief="flat", padx=10, pady=2, state="disabled", cursor="hand2")
        self.llm_btn.pack(side="left", padx=2)

        self.dash_btn = tk.Button(btn_frame, text="📊 看板", command=self.open_dashboard,
                                   bg="#334155", fg="#94a3b8", font=("Segoe UI", 9),
                                   relief="flat", padx=10, pady=2, cursor="hand2")
        self.dash_btn.pack(side="left", padx=2)

        # 数据
        self.urls: list[str] = []
        self.last_batch_id: str = ""

        # 键盘快捷键
        self.win.bind("<Return>", lambda e: self.search())
        self.win.bind("<Escape>", lambda e: self.win.quit())

    # ─────────────── 方法 ───────────────

    def log(self, msg: str):
        self.status_label.config(text=msg)
        self.win.update_idletasks()

    def search(self):
        keyword = self.keyword_entry.get().strip()
        if not keyword:
            self.log("⚠️ 请输入关键词")
            return

        sort = self.sort_var.get()
        limit = self.limit_var.get()

        self.search_btn.config(state="disabled", text="⏳ 搜索中...")
        self.listbox.delete(0, "end")
        self.urls.clear()
        self.log(f"🔍 搜索: {keyword} ({sort}, top {limit})")

        def worker():
            try:
                stdout, stderr = run_cmd([
                    sys.executable, "main.py",
                    "--keyword", keyword,
                    "--sort", sort,
                    "--limit", str(limit),
                    "--sources", "reddit,twitter,tiktok,amazon,shein",
                ], timeout=180)

                # 解析 batch_id
                batch_match = re.search(r"batch_id=([\S]+)", stdout)
                if batch_match:
                    self.last_batch_id = batch_match.group(1)

                # 从 DB 读取本批次数据
                import sqlite3
                conn = sqlite3.connect(str(ROOT / "db" / "textiles.db"))
                rows = conn.execute(
                    """SELECT source, title, url, score, num_comments, image_url,
                              metadata FROM raw_posts WHERE batch_id=? ORDER BY score DESC LIMIT 60""",
                    (self.last_batch_id,)
                ).fetchall()
                conn.close()

                self.win.after(0, lambda: self.display_results(rows))
            except Exception as e:
                self.win.after(0, lambda: self.log(f"❌ 搜索失败: {e}"))
                self.win.after(0, lambda: self.search_btn.config(state="normal", text="🔍 搜索"))

        threading.Thread(target=worker, daemon=True).start()

    def display_results(self, rows):
        self.listbox.delete(0, "end")
        self.urls.clear()

        for i, row in enumerate(rows, 1):
            src, title, url, score, comments = row[0], row[1] or "", row[2] or "", row[3], row[4]
            meta = json.loads(row[6]) if row[6] else {}
            price = meta.get("price", 0)
            rating = meta.get("rating", 0)
            reviews = meta.get("reviews", 0)

            icon = {"reddit": "🔴", "twitter": "🐦", "tiktok": "🎵", "amazon": "📦", "shein": "👗"}.get(src, "📄")
            title_short = title[:55] + ".." if len(title) > 55 else title

            # 互动指标
            if src in ("amazon", "shein"):
                engagement = f"⭐{rating} 💬{reviews:,}" if reviews else f"⭐{rating}"
                if price:
                    engagement = f"${price:.0f} " + engagement
            else:
                engagement = f"❤️{score} 💬{comments}"

            display = f" {icon} {src:8s} {title_short:55s} {engagement:15s}"
            self.listbox.insert("end", display)
            self.urls.append(url)

        self.log(f"✅ {len(rows)} 条数据")
        self.search_btn.config(state="normal", text="🔍 搜索")
        if self.last_batch_id:
            self.llm_btn.config(state="normal")

    def open_selected(self, event=None):
        sel = self.listbox.curselection()
        if sel and sel[0] < len(self.urls) and self.urls[sel[0]]:
            webbrowser.open(self.urls[sel[0]])

    def run_llm(self):
        if not self.last_batch_id:
            return
        self.llm_btn.config(state="disabled", text="⏳ 分析中...")
        self.log("🤖 LLM 分析中...")

        def worker():
            try:
                stdout, stderr = run_cmd(["node", "router/src/router.js", "--batch", self.last_batch_id], timeout=120)
                self.win.after(0, lambda: self.log("✅ LLM 分析完成，结果已保存到数据库"))
            except Exception as e:
                self.win.after(0, lambda: self.log(f"❌ LLM 失败: {e}"))
            self.win.after(0, lambda: self.llm_btn.config(state="normal", text="🤖 LLM 分析"))

        threading.Thread(target=worker, daemon=True).start()

    def open_dashboard(self):
        dash = ROOT / "reports" / "dashboard.html"
        if dash.exists():
            webbrowser.open(str(dash))
            self.log("📊 已打开看板")
        else:
            # 生成
            def worker():
                try:
                    run_cmd([sys.executable, "scripts/generate_dashboard.py"], timeout=30)
                    self.win.after(0, lambda: webbrowser.open(str(dash)))
                    self.win.after(0, lambda: self.log("✅ 看板已生成并打开"))
                except Exception as e:
                    self.win.after(0, lambda: self.log(f"❌ 看板生成失败: {e}"))

            self.log("⏳ 生成看板中...")
            threading.Thread(target=worker, daemon=True).start()

    def run(self):
        self.win.mainloop()


if __name__ == "__main__":
    App().run()
