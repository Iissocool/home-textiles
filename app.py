"""
跨境产品情报 · 桌面助手 v5
开源采集 x OpenCLI x 智能分析
"""
import tkinter as tk
from tkinter import ttk
import subprocess, webbrowser, threading, sys, os, json, re, sqlite3
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent

ALL_SOURCES = [
    ("reddit",  "🔴 Reddit"),
    ("twitter", "🐦 X"),
    ("tiktok",  "🎵 TikTok"),
    ("amazon",  "📦 Amazon"),
    ("shein",   "👗 SHEIN"),
]


def bg(cmd, timeout=300):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
    return r.stdout, r.stderr


def short_bid(bid):
    parts = bid.split("_")
    if len(parts) >= 3:
        return f"{parts[0]}_{parts[1]}_{parts[-1]}"
    return bid


class App:
    def __init__(self):
        self.win = tk.Tk()
        self.win.title("🌐 跨境产品情报助手")
        self.win.geometry("740x560")
        self.win.configure(bg="#0f172a")
        self.win.option_add("*Font", ("Segoe UI", 10))

        self.bg, self.fg = "#0f172a", "#e2e8f0"

        # ── 顶部：搜索输入 ──
        top = tk.Frame(self.win, bg=self.bg)
        top.pack(fill="x", padx=14, pady=(14, 4))

        tk.Label(top, text="关键词", fg="#64748b", bg=self.bg).pack(side="left")
        self.kw = tk.Entry(top, width=18, bg="#1e293b", fg=self.fg,
                           insertbackground=self.fg, relief="flat", bd=8)
        self.kw.pack(side="left", padx=(6, 8))
        self.kw.insert(0, "cooling sheets")

        tk.Label(top, text="排序", fg="#64748b", bg=self.bg).pack(side="left")
        self.sort_v = tk.StringVar(value="likes")
        ttk.Combobox(top, textvariable=self.sort_v, values=["likes", "comments"],
                     width=6, state="readonly").pack(side="left", padx=(6, 8))

        tk.Label(top, text="条数", fg="#64748b", bg=self.bg).pack(side="left")
        self.limit_v = tk.StringVar(value="10")
        tk.Spinbox(top, from_=3, to=50, textvariable=self.limit_v,
                   width=3, bg="#1e293b", fg=self.fg,
                   buttonbackground="#334155", relief="flat", bd=6).pack(side="left", padx=(6, 8))

        self.btn = tk.Button(top, text="🔍 搜索", command=self.search,
                             bg="#3b82f6", fg="white", font=(None, 10, "bold"),
                             relief="flat", padx=14, pady=3, cursor="hand2")
        self.btn.pack(side="left")

        # ── 数据源选择 ──
        src_frame = tk.Frame(self.win, bg=self.bg)
        src_frame.pack(fill="x", padx=14, pady=(2, 4))
        tk.Label(src_frame, text="数据源:", fg="#64748b", bg=self.bg).pack(side="left")
        self.src_vars = {}
        for key, label in ALL_SOURCES:
            var = tk.BooleanVar(value=True)
            self.src_vars[key] = var
            cb = tk.Checkbutton(src_frame, text=label, variable=var,
                                bg=self.bg, fg="#94a3b8", selectcolor="#0f172a",
                                activebackground=self.bg, activeforeground="#e2e8f0",
                                relief="flat", bd=0, padx=0, highlightthickness=0)
            cb.pack(side="left", padx=(6, 0))

        # ── 搜索记录 ──
        hdr = tk.Frame(self.win, bg=self.bg)
        hdr.pack(fill="x", padx=14, pady=(6, 2))
        tk.Label(hdr, text="📋 搜索记录", fg="#94a3b8",
                 font=(None, 11, "bold"), bg=self.bg).pack(side="left")

        lst_frame = tk.Frame(self.win, bg=self.bg)
        lst_frame.pack(fill="both", expand=True, padx=14, pady=(0, 6))

        cols = ("批次", "关键词", "日期", "条数")
        self.tree = ttk.Treeview(lst_frame, columns=cols, show="headings",
                                  selectmode="browse", height=12)
        for c, w in zip(cols, [120, 140, 80, 50]):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="w")

        vsb = ttk.Scrollbar(lst_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self.open_batch)
        self.tree.bind("<Return>", self.open_batch)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Button-3>", self.copy_bid)

        # ── 底部按钮 ──
        bot = tk.Frame(self.win, bg="#1e293b")
        bot.pack(fill="x")

        self.stat = tk.Label(bot, text="就绪", fg="#64748b", bg="#1e293b")
        self.stat.pack(side="left", padx=10, pady=5)

        # OpenCLI 状态指示灯
        self.ocli_status = tk.Label(bot, text="⚪", fg="#475569", bg="#1e293b",
                                     font=(None, 14))
        self.ocli_status.pack(side="left", padx=2)

        frm = tk.Frame(bot, bg="#1e293b")
        frm.pack(side="right", padx=6)

        tk.Label(frm, text="🤖", fg="#64748b", bg="#1e293b").pack(side="left")
        self.model_v = tk.StringVar(value="deepseek")
        model_combo = ttk.Combobox(frm, textvariable=self.model_v,
            values=["deepseek", "hybrid", "claude", "flash"],
            width=8, state="readonly")
        model_combo.pack(side="left", padx=(2, 6))
        model_combo.bind("<<ComboboxSelected>>", lambda e: self._update_analysis_btn())

        self.analysis_btn = tk.Button(frm, text="开始 V4 Pro",
                                      command=self.run_analysis, bg="#334155", fg="#475569",
                                      relief="flat", padx=10, pady=2, state="disabled")
        self.analysis_btn.pack(side="left", padx=2)

        tk.Button(frm, text="📋 复制批次号", command=self.copy_bid,
                  bg="#334155", fg="#94a3b8", relief="flat", padx=10, pady=2).pack(side="left", padx=2)

        tk.Button(frm, text="🔄 刷新", command=self.refresh,
                  bg="#334155", fg="#94a3b8", relief="flat", padx=10, pady=2).pack(side="left", padx=2)

        # 数据
        self.batch_ids = []
        self.analysis_cache = set()
        self.win.bind("<Escape>", lambda e: self.win.quit())
        self.refresh()
        # 异步检查 OpenCLI 状态
        threading.Thread(target=self._check_opencli, daemon=True).start()

    # ───────── 方法 ─────────

    def log(self, msg):
        self.stat.config(text=msg)
        self.win.update_idletasks()

    def _check_opencli(self):
        """后台检测 OpenCLI 连接状态"""
        try:
            r = subprocess.run(["opencli", "doctor"], capture_output=True, text=True, timeout=15)
            if "Extension: connected" in r.stdout:
                self.win.after(0, lambda: self.ocli_status.config(
                    text="🟢", fg="#34d399"))
                self.win.after(0, lambda: self.log("🟢 OpenCLI 已连接"))
            else:
                self.win.after(0, lambda: self.ocli_status.config(
                    text="🔴", fg="#f87171"))
                self.win.after(0, lambda: self.log("🔴 OpenCLI 未连接"))
        except Exception:
            self.win.after(0, lambda: self.ocli_status.config(
                text="🔴", fg="#f87171"))

    def _selected_bid(self):
        sel = self.tree.selection()
        if not sel:
            return None
        idx = self.tree.index(sel[0])
        return self.batch_ids[idx] if idx < len(self.batch_ids) else None

    def search(self):
        kw = self.kw.get().strip()
        if not kw:
            return self.log("⚠️ 输入关键词")
        selected = [k for k, v in self.src_vars.items() if v.get()]
        if not selected:
            return self.log("⚠️ 至少勾选一个数据源")
        sources_str = ",".join(selected)

        self.btn.config(state="disabled", text="⏳ 搜索中...")
        self.log(f"🔍 搜索: {kw} ({len(selected)} 源)")

        def work():
            new_bid = None
            try:
                sort, limit = self.sort_v.get(), self.limit_v.get()
                self.win.after(0, lambda: self.log(f"🔍 {kw} — 正在抓取..."))

                out, err = bg([sys.executable, "main.py", "--keyword", kw,
                     "--sort", sort, "--limit", limit,
                     "--sources", sources_str])

                # 解析进度（提取各源结果）
                for line in out.split("\n"):
                    m = re.search(r"📡 抓取 (\w+)", line)
                    if m:
                        self.win.after(0, lambda s=m.group(1): self.log(f"📡 抓取 {s}..."))
                    m2 = re.search(r"✅ (\d+) 条", line)
                    if m2:
                        self.win.after(0, lambda n=m2.group(1): self.log(f"✅ {n} 条完成"))

                # 生成批次看板
                conn = sqlite3.connect(str(ROOT / "db" / "textiles.db"))
                row = conn.execute("""
                    SELECT batch_id FROM raw_posts
                    WHERE search_keyword=? AND batch_id!=''
                    ORDER BY id DESC LIMIT 1
                """, (kw,)).fetchone()
                conn.close()

                if row:
                    new_bid = row[0]
                    self.win.after(0, lambda: self.log(f"📄 生成看板: {new_bid}"))
                    bg([sys.executable, "scripts/generate_dashboard.py", "--batch", new_bid])

                    self.win.after(0, lambda: self.refresh(highlight_bid=new_bid))
                    self.win.after(0, lambda: self.log(f"✅ {kw} 完成（{new_bid}）双击记录打开看板"))
                else:
                    self.win.after(0, lambda: self.log("⚠️ 未找到批次数据"))
            except Exception as e:
                self.win.after(0, lambda: self.log(f"❌ {e}"))
            self.win.after(0, lambda: self.btn.config(state="normal", text="🔍 搜索"))

        threading.Thread(target=work, daemon=True).start()

    def refresh(self, highlight_bid=None):
        self.tree.delete(*self.tree.get_children())
        self.batch_ids.clear()
        self.analysis_cache.clear()

        try:
            conn = sqlite3.connect(str(ROOT / "db" / "textiles.db"))
            rows = conn.execute("""
                SELECT batch_id, search_keyword,
                       date(MIN(fetched_at), 'unixepoch'),
                       COUNT(*)
                FROM raw_posts
                WHERE batch_id!=''
                GROUP BY batch_id
                ORDER BY MAX(id) DESC
                LIMIT 50
            """).fetchall()

            bids = [r[0] for r in rows]
            if bids:
                placeholders = ",".join("?" for _ in bids)
                analyzed = set(
                    r[0] for r in conn.execute(
                        f"SELECT batch_id FROM llm_analyses WHERE batch_id IN ({placeholders})",
                        bids
                    ).fetchall()
                )
                self.analysis_cache = analyzed
            conn.close()

            highlight_row = None
            for i, r in enumerate(rows):
                bid, kw, dt, cnt = r[0], r[1] or "(空)", r[2] or "?", r[3]
                tag = bid.split("_")[-1] if "_" in bid else ""
                display_kw = kw if kw != "(空)" else tag.replace("_", " ")
                display_bid = short_bid(bid)
                item_id = self.tree.insert("", "end", values=(display_bid, display_kw, dt, cnt))
                self.batch_ids.append(bid)
                if highlight_bid and bid == highlight_bid:
                    highlight_row = item_id

            # 高亮刚生成的批次
            if highlight_row:
                self.tree.selection_set(highlight_row)
                self.tree.focus(highlight_row)
                self.tree.see(highlight_row)

            self.log(f"📋 {len(rows)} 条搜索记录")
        except Exception as e:
            self.log(f"❌ 读取记录失败: {e}")

        self._update_analysis_btn()

    def on_select(self, event=None):
        self._update_analysis_btn()
        bid = self._selected_bid()
        if bid:
            self.log(f"📋 {bid}")

    def _update_analysis_btn(self):
        bid = self._selected_bid()
        model_label = {"deepseek": "V4 Pro", "hybrid": "混合", "claude": "Sonnet", "flash": "V4 Flash"}.get(
            self.model_v.get(), "")
        if not bid:
            self.analysis_btn.config(state="disabled", fg="#475569",
                                     text=f"开始 {model_label}")
            return
        has_analysis = bid in self.analysis_cache
        self.analysis_btn.config(
            state="normal",
            fg="#60a5fa" if has_analysis else "#94a3b8",
            text=f"🕶️ {model_label}" if has_analysis else f"开始 {model_label}"
        )

    def open_batch(self, event=None):
        bid = self._selected_bid()
        if not bid:
            return

        html_path = ROOT / "reports" / f"batch_{bid}.html"
        if not html_path.exists():
            self.log(f"⏳ 生成批次看板...")
            try:
                bg([sys.executable, "scripts/generate_dashboard.py", "--batch", bid])
            except Exception as e:
                self.log(f"❌ 生成失败: {e}")
                return

        webbrowser.open(str(html_path))
        self.log(f"📂 已打开: {bid}")

    def copy_bid(self, event=None):
        bid = self._selected_bid()
        if not bid:
            return self.log("⚠️ 请先选中一个批次")
        self.win.clipboard_clear()
        self.win.clipboard_append(bid)
        self.log(f"📋 已复制: {bid}")

    def run_analysis(self):
        bid = self._selected_bid()
        if not bid:
            return self.log("请先选中一个批次")

        report_path = ROOT / "reports" / f"analysis_{bid}.html"
        if report_path.exists() and bid in self.analysis_cache:
            webbrowser.open(str(report_path))
            self.log(f"📂 打开分析报告: {bid}")
            return

        self.analysis_btn.config(state="disabled", text="⏳ 分析中...")
        self.log(f"🕶️ 市场分析: {bid}...")

        def work():
            try:
                node = shutil_which("node") or "/usr/bin/node"
                analysis_js = str(ROOT / "router" / "src" / "analysis.js")
                out, err = bg([node, analysis_js, "--batch", bid, "--model", self.model_v.get()],
                              timeout=300)

                if "分析完成" in out:
                    self.win.after(0, lambda: self.log(f"✅ 分析完成 ({bid})"))
                    self.win.after(0, lambda: self.refresh())
                    self.win.after(0, lambda: webbrowser.open(str(report_path)))
                elif err:
                    self.win.after(0, lambda: self.log(f"❌ 分析失败: {err[:80]}"))
                else:
                    self.win.after(0, lambda: self.log(f"❌ 分析异常，请查看输出"))
            except Exception as e:
                self.win.after(0, lambda: self.log(f"❌ 分析异常: {e}"))
            model_label = {"deepseek": "V4 Pro", "hybrid": "混合", "claude": "Sonnet", "flash": "V4 Flash"}.get(
                self.model_v.get(), "")
            self.win.after(0, lambda: self.analysis_btn.config(text="🕶️ " + model_label))

        threading.Thread(target=work, daemon=True).start()

    def run(self):
        self.win.mainloop()


def shutil_which(name):
    for p in os.environ.get("PATH", "").split(os.pathsep):
        fp = os.path.join(p, name)
        if os.path.isfile(fp) and os.access(fp, os.X_OK):
            return fp
    return None


if __name__ == "__main__":
    App().run()
