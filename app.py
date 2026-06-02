"""
家纺情报 · 桌面助手 v2
按批次管理搜索记录，点击批次打开 HTML 看板，LLM 分析独立操作
"""
import tkinter as tk
from tkinter import ttk
import subprocess, webbrowser, threading, sys, os, json, re, sqlite3
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent


def bg(cmd, timeout=180):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
    return r.stdout, r.stderr


class App:
    def __init__(self):
        self.win = tk.Tk()
        self.win.title("🏠 家纺情报助手")
        self.win.geometry("700x520")
        self.win.configure(bg="#0f172a")
        self.win.option_add("*Font", ("Segoe UI", 10))

        self.bg, self.fg = "#0f172a", "#e2e8f0"

        # ── 顶部：搜索输入 ──
        top = tk.Frame(self.win, bg=self.bg)
        top.pack(fill="x", padx=14, pady=(14, 4))

        tk.Label(top, text="关键词", fg="#64748b", bg=self.bg).pack(side="left")
        self.kw = tk.Entry(top, width=20, bg="#1e293b", fg=self.fg,
                           insertbackground=self.fg, relief="flat", bd=8)
        self.kw.pack(side="left", padx=(6, 10))
        self.kw.insert(0, "cooling sheets")

        tk.Label(top, text="排序", fg="#64748b", bg=self.bg).pack(side="left")
        self.sort_v = tk.StringVar(value="likes")
        ttk.Combobox(top, textvariable=self.sort_v, values=["likes", "comments"],
                     width=7, state="readonly").pack(side="left", padx=(6, 10))

        tk.Label(top, text="条数", fg="#64748b", bg=self.bg).pack(side="left")
        self.limit_v = tk.StringVar(value="10")
        tk.Spinbox(top, from_=3, to=50, textvariable=self.limit_v,
                   width=4, bg="#1e293b", fg=self.fg,
                   buttonbackground="#334155", relief="flat", bd=6).pack(side="left", padx=(6, 10))

        self.btn = tk.Button(top, text="🔍 搜索", command=self.search,
                             bg="#3b82f6", fg="white", font=(None, 10, "bold"),
                             relief="flat", padx=14, pady=3, cursor="hand2")
        self.btn.pack(side="left")

        # ── 搜索记录标题 ──
        hdr = tk.Frame(self.win, bg=self.bg)
        hdr.pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(hdr, text="📋 搜索记录", fg="#94a3b8",
                 font=(None, 11, "bold"), bg=self.bg).pack(side="left")

        # ── 记录列表 ──
        lst_frame = tk.Frame(self.win, bg=self.bg)
        lst_frame.pack(fill="both", expand=True, padx=14, pady=(0, 6))

        cols = ("批次", "关键词", "日期", "条数")
        self.tree = ttk.Treeview(lst_frame, columns=cols, show="headings",
                                  selectmode="browse", height=12)
        for c, w in zip(cols, [60, 150, 120, 60]):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="w")

        vsb = ttk.Scrollbar(lst_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self.open_batch)
        self.tree.bind("<Return>", self.open_batch)

        # ── 底部按钮 ──
        bot = tk.Frame(self.win, bg="#1e293b")
        bot.pack(fill="x")

        self.stat = tk.Label(bot, text="就绪", fg="#64748b", bg="#1e293b")
        self.stat.pack(side="left", padx=10, pady=5)

        frm = tk.Frame(bot, bg="#1e293b")
        frm.pack(side="right", padx=6)

        self.llm_btn = tk.Button(frm, text="🤖 LLM 分析选中批次",
                                  command=self.run_llm, bg="#334155", fg="#94a3b8",
                                  relief="flat", padx=10, pady=2, state="disabled")
        self.llm_btn.pack(side="left", padx=2)

        tk.Button(frm, text="🔄 刷新", command=self.refresh,
                  bg="#334155", fg="#94a3b8", relief="flat", padx=10, pady=2).pack(side="left", padx=2)

        # 数据
        self.batch_ids = []
        self.win.bind("<Escape>", lambda e: self.win.quit())
        self.refresh()

    # ───────── 方法 ─────────

    def log(self, msg):
        self.stat.config(text=msg)
        self.win.update_idletasks()

    def search(self):
        kw = self.kw.get().strip()
        if not kw:
            return self.log("⚠️ 输入关键词")
        self.btn.config(state="disabled", text="⏳ 搜索中...")
        self.log(f"🔍 搜索: {kw}")

        def work():
            try:
                sort, limit = self.sort_v.get(), self.limit_v.get()
                bg([sys.executable, "main.py", "--keyword", kw,
                     "--sort", sort, "--limit", limit,
                     "--sources", "reddit,twitter,tiktok,amazon,shein"])

                # 生成批次看板
                conn = sqlite3.connect(str(ROOT / "db" / "textiles.db"))
                row = conn.execute("""
                    SELECT batch_id FROM raw_posts
                    WHERE search_keyword=? AND batch_id!=''
                    ORDER BY id DESC LIMIT 1
                """, (kw,)).fetchone()
                conn.close()

                if row:
                    bid = row[0]
                    bg([sys.executable, "scripts/generate_dashboard.py", "--batch", bid])
                    self.win.after(0, self.refresh)
                    self.win.after(0, lambda: self.log(f"✅ {kw} 完成，双击记录打开看板"))
                else:
                    self.win.after(0, lambda: self.log("⚠️ 未找到批次数据"))
            except Exception as e:
                self.win.after(0, lambda: self.log(f"❌ {e}"))
            self.win.after(0, lambda: self.btn.config(state="normal", text="🔍 搜索"))

        threading.Thread(target=work, daemon=True).start()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self.batch_ids.clear()

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
            conn.close()

            for r in rows:
                bid, kw, dt, cnt = r[0], r[1] or "(空)", r[2] or "?", r[3]
                tag = bid.split("_")[-1] if "_" in bid else ""
                display_kw = kw if kw != "(空)" else tag.replace("_", " ")
                self.tree.insert("", "end", values=(bid[:20], display_kw, dt, cnt))
                self.batch_ids.append(bid)

            self.log(f"📋 {len(rows)} 条搜索记录")
        except Exception as e:
            self.log(f"❌ 读取记录失败: {e}")

    def open_batch(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        bid = self.batch_ids[idx]

        # 检查批次 HTML 是否存在，不存在则生成
        html_path = ROOT / "reports" / f"batch_{bid}.html"
        if not html_path.exists():
            self.log(f"⏳ 生成批次看板...")
            try:
                bg([sys.executable, "scripts/generate_dashboard.py", "--batch", bid])
            except Exception as e:
                self.log(f"❌ 生成失败: {e}")
                return

        webbrowser.open(str(html_path))
        self.log(f"📂 已打开: {bid[:25]}...")

    def run_llm(self):
        sel = self.tree.selection()
        if not sel:
            return self.log("请先选中一个批次")
        idx = self.tree.index(sel[0])
        bid = self.batch_ids[idx]

        self.llm_btn.config(state="disabled", text="⏳ LLM 分析中...")
        self.log(f"🤖 LLM 分析批次: {bid[:25]}...")

        def work():
            try:
                bg(["node", "router/src/router.js", "--batch", bid], timeout=120)
                self.win.after(0, lambda: self.log(f"✅ LLM 分析完成 (batch: {bid[:20]}...)"))
            except Exception as e:
                self.win.after(0, lambda: self.log(f"❌ LLM 失败: {e}"))
            self.win.after(0, lambda: self.llm_btn.config(state="normal", text="🤖 LLM 分析选中批次"))

        threading.Thread(target=work, daemon=True).start()

    def run(self):
        self.win.mainloop()


if __name__ == "__main__":
    App().run()
