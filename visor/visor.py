"""
NBA Player Forecasting — Viewer
Desktop app to browse the daily forecasts published by the pipeline
(github.com/noevillaes/nba-player-forecasting) and compare them with
actual results.

Data source: if the exe sits inside the project folder it reads the local
CSVs (kept fresh by the daily task); anywhere else it downloads them from
the GitHub repo, so friends only need the exe and an internet connection.

Only uses the standard library (tkinter, urllib, csv), so the .exe stays small.
"""

import csv
import io
import os
import sys
import threading
import time
import urllib.request
import webbrowser
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

REPO = "noevillaes/nba-player-forecasting"
RAW = f"https://raw.githubusercontent.com/{REPO}/main/"
REPO_URL = f"https://github.com/{REPO}"

DATASETS = {
    "Live 2026-27": {
        "players": "predictions/historial.csv",
        "games": "predictions/historial_juegos.csv",
        "score": "results/marcador.csv",
    },
    "Backtest (Mar 2026)": {
        "players": "predictions/historial_backtest.csv",
        "games": "predictions/historial_juegos_backtest.csv",
        "score": "results/marcador_backtest.csv",
    },
}

STAT_NAMES = {
    "MIN": "Minutes", "PTS": "Points", "REB": "Rebounds", "OREB": "Off. rebounds",
    "DREB": "Def. rebounds", "AST": "Assists", "STL": "Steals", "BLK": "Blocks",
    "TO": "Turnovers", "PF": "Fouls", "FGM": "FG made", "FGA": "FG attempted",
    "3PM": "3P made", "3PA": "3P attempted", "FTM": "FT made", "FTA": "FT attempted",
}
BOX_COLS = ["MIN", "PTS", "REB", "AST", "STL", "BLK", "TO", "FGM", "FGA", "3PM", "FTM"]

# =====================================================================
# Data
# =====================================================================
def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def find_local_repo():
    """Folder containing predictions/historial.csv, searching upward from the exe/script."""
    starts = [os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)),
              os.getcwd()]
    for start in starts:
        d = start
        for _ in range(5):
            if os.path.isfile(os.path.join(d, "predictions", "historial.csv")):
                return d
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
    return None


def fetch_text(path):
    """Returns (text, source).
    If the exe lives inside the repo (e.g. in dist/), the local copy is used: the daily
    task keeps it up to date and it is never stale. Otherwise, it downloads from GitHub."""
    local = find_local_repo()
    if local:
        p = os.path.join(local, *path.split("/"))
        if os.path.isfile(p):
            with open(p, encoding="utf-8-sig") as f:
                return f.read(), "local"
    url = RAW + path + f"?t={int(time.time())}"
    req = urllib.request.Request(url, headers={"User-Agent": "nba-forecast-viewer",
                                               "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8-sig"), "GitHub"


def read_csv(path):
    text, src = fetch_text(path)
    return list(csv.DictReader(io.StringIO(text))), src


def num(x):
    try:
        if x is None or x == "":
            return None
        return float(x)
    except ValueError:
        return None


def fmt(x, dec=1):
    if x is None:
        return "–"
    if abs(x - round(x)) < 1e-9 and dec <= 1:
        return str(int(round(x)))
    return f"{x:.{dec}f}"


class Dataset:
    def __init__(self, name):
        files = DATASETS[name]
        self.players, s1 = read_csv(files["players"])
        self.games, s2 = read_csv(files["games"])
        self.score, s3 = read_csv(files["score"])
        self.source = "GitHub" if {s1, s2, s3} == {"GitHub"} else "local repo folder"

        # games by date
        self.dates = sorted({g["fecha"] for g in self.games}, reverse=True)
        self.games_by_date = {}
        for g in self.games:
            self.games_by_date.setdefault(g["fecha"], []).append(g)

        # players: gameId -> personId -> {info, stats{code: row}}
        self.box = {}
        for r in self.players:
            game = self.box.setdefault(r["gameId"], {})
            p = game.setdefault(r["personId"], {
                "name": r["jugador"], "team": r["equipo"], "local": r["local"],
                "status": r["estado"], "stats": {},
            })
            p["stats"][r["estadistica"]] = r


# =====================================================================
# Look and feel
# =====================================================================
PAGE = "#E8EBEF"        # cool grey page
SURFACE = "#FFFFFF"
INK = "#17202B"
INK_2 = "#5A6472"
INK_3 = "#8A93A0"
RULE = "#D6DBE2"
HOVER = "#F3F5F8"
SELECT = "#DCE5F0"
HIT = "#2F7A4D"
MISS = "#B0322A"
BAR = "#2B4C74"

# Primary colour of each team (keyed by the nickname used in the CSVs)
TEAM_COLORS = {
    "Hawks": "#C8102E", "Celtics": "#007A33", "Nets": "#1A1A1A", "Hornets": "#1D1160",
    "Bulls": "#CE1141", "Cavaliers": "#860038", "Mavericks": "#00538C", "Nuggets": "#0E2240",
    "Pistons": "#C8102E", "Warriors": "#1D428A", "Rockets": "#CE1141", "Pacers": "#002D62",
    "Clippers": "#C8102E", "Lakers": "#552583", "Grizzlies": "#5D76A9", "Heat": "#98002E",
    "Bucks": "#00471B", "Timberwolves": "#0C2340", "Pelicans": "#0C2340", "Knicks": "#006BB6",
    "Thunder": "#007AC1", "Magic": "#0077C0", "76ers": "#006BB6", "Suns": "#1D1160",
    "Trail Blazers": "#E03A3E", "Kings": "#5A2D81", "Spurs": "#2B2B2B", "Raptors": "#CE1141",
    "Jazz": "#002B5C", "Wizards": "#002B5C",
}
TEAM_ALT = {  # secondary colour, used when both teams share almost the same primary
    "Hawks": "#26282A", "Celtics": "#963821", "Nets": "#707271", "Hornets": "#00788C",
    "Bulls": "#1A1A1A", "Cavaliers": "#041E42", "Mavericks": "#002B5E", "Nuggets": "#8B6F2E",
    "Pistons": "#1D42BA", "Warriors": "#B58B00", "Rockets": "#5A5F63", "Pacers": "#B88A00",
    "Clippers": "#1D428A", "Lakers": "#B07F00", "Grizzlies": "#12173F", "Heat": "#41454A",
    "Bucks": "#7A6A4F", "Timberwolves": "#236192", "Pelicans": "#85714D", "Knicks": "#E35A13",
    "Thunder": "#EF3B24", "Magic": "#5F6A72", "76ers": "#ED174C", "Suns": "#E56020",
    "Trail Blazers": "#1A1A1A", "Kings": "#63727A", "Spurs": "#8A9399", "Raptors": "#1A1A1A",
    "Jazz": "#6B5B00", "Wizards": "#E31837",
}

FONT_FILES = ["Barlow-Regular.ttf", "Barlow-Medium.ttf", "Barlow-SemiBold.ttf",
              "BarlowCondensed-Medium.ttf", "BarlowCondensed-SemiBold.ttf"]


K = 1.0  # screen scale: 1.0 at 100 %, 1.25 at 125 %, ... (set when the window opens)


def px(n):
    """Scales a pixel size so the layout keeps its proportions on high-DPI screens."""
    return int(round(n * K))


def register_fonts():
    """Makes the bundled Barlow fonts available to this process only."""
    folder = resource_path("fonts")
    paths = [os.path.join(folder, f) for f in FONT_FILES]
    try:
        import ctypes
        if sys.platform == "win32":
            for p in paths:
                ctypes.windll.gdi32.AddFontResourceExW(p, 0x10, 0)
        elif sys.platform == "darwin":
            import ctypes.util
            cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
            ct = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreText"))
            cf.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
            cf.CFURLCreateFromFileSystemRepresentation.argtypes = [
                ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool]
            ct.CTFontManagerRegisterFontsForURL.argtypes = [
                ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
            for p in paths:
                b = p.encode("utf-8")
                url = cf.CFURLCreateFromFileSystemRepresentation(None, b, len(b), False)
                ct.CTFontManagerRegisterFontsForURL(url, 1, None)  # 1 = this process only
    except Exception:
        pass


def team_color(team):
    return TEAM_COLORS.get(team, "#3A4A5C")


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def matchup_colors(away, home):
    a, h = team_color(away), team_color(home)
    if sum((x - y) ** 2 for x, y in zip(_rgb(a), _rgb(h))) < 60 ** 2:
        h = TEAM_ALT.get(home, "#3A4A5C")
    return a, h


def nice_date(d, year=False):
    try:
        import datetime
        dt = datetime.datetime.strptime(d, "%Y-%m-%d")
        s = f"{dt:%A}, {dt:%b} {dt.day}"
        return s + f", {dt.year}" if year else s
    except Exception:
        return d


def by_margin(team_home, team_away, margin):
    """'Raptors by 8.4' from a home-minus-away margin."""
    if margin is None:
        return ""
    if abs(margin) < 0.05:
        return "even"
    return f"{team_home if margin > 0 else team_away} by {abs(margin):.1f}".replace(".0 ", " ")


# =====================================================================
# Small widgets
# =====================================================================
class Segmented(tk.Frame):
    """Row of text options; the active one gets an underline (optionally in a team colour)."""

    def __init__(self, parent, options, command, bg=SURFACE, font=None):
        super().__init__(parent, bg=bg)
        self.command = command
        self.items = {}
        self.value = None
        self.colors = {}
        for key, text in options:
            self.add(key, text, font)

    def add(self, key, text, font=None):
        f = tk.Frame(self, bg=self["bg"], cursor="hand2")
        f.pack(side="left", padx=(px(0), px(18)))
        lbl = tk.Label(f, text=text, bg=self["bg"], fg=INK_2, font=font)
        lbl.pack()
        bar = tk.Frame(f, height=px(3), bg=self["bg"])
        bar.pack(fill="x", pady=(px(3), px(0)))
        for w in (f, lbl):
            w.bind("<Button-1>", lambda e, k=key: self.select(k, fire=True))
        self.items[key] = (lbl, bar)

    def set_text(self, key, text, color=None):
        self.items[key][0].config(text=text)
        if color:
            self.colors[key] = color
        self._paint()

    def select(self, key, fire=False):
        self.value = key
        self._paint()
        if fire:
            self.command(key)

    def _paint(self):
        for k, (lbl, bar) in self.items.items():
            on = k == self.value
            lbl.config(fg=INK if on else INK_2)
            bar.config(bg=self.colors.get(k, INK) if on else self["bg"])


class GameList(tk.Frame):
    """Scrollable list of games, scoreboard style."""

    def __init__(self, parent, on_select, fonts):
        super().__init__(parent, bg=SURFACE)
        self.on_select = on_select
        self.F = fonts
        self.canvas = tk.Canvas(self, bg=SURFACE, highlightthickness=0, bd=0)
        self.sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=SURFACE)
        self.win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        for w in (self.canvas, self.inner):
            w.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
            w.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))
        self.rows = {}
        self.selected = None

    def _wheel(self, e):
        step = -e.delta if sys.platform == "darwin" else -e.delta / 120
        self.canvas.yview_scroll(int(step) or (1 if step > 0 else -1), "units")

    def fill(self, games):
        for w in self.inner.winfo_children():
            w.destroy()
        self.rows = {}
        self.selected = None
        if not games:
            tk.Label(self.inner, text="No games on this day.", bg=SURFACE, fg=INK_2,
                     font=self.F["body"]).pack(anchor="w", padx=px(16), pady=px(16))
        for g in games:
            self._row(g)
        self.canvas.yview_moveto(0)

    def _row(self, g):
        played = g["estado"] == "Jugado"
        row = tk.Frame(self.inner, bg=SURFACE, cursor="hand2")
        row.pack(fill="x")
        if played:
            stripe_c = HIT if num(g["acierto_ganador"]) == 1 else MISS
        else:
            stripe_c = RULE
        stripe = tk.Frame(row, width=px(4), bg=stripe_c)
        stripe.pack(side="left", fill="y")
        body = tk.Frame(row, bg=SURFACE, padx=px(12), pady=px(8))
        body.pack(side="left", fill="x", expand=True)
        body.columnconfigure(0, weight=1)

        ra, rh = num(g["real_visita"]), num(g["real_local"])
        winner = None
        if played and ra is not None and rh is not None:
            winner = "away" if ra > rh else "home"
        widgets = [row, stripe, body]
        for i, (side, team, proj, real) in enumerate((
                ("away", g["visitante"], g["pts_visita"], ra),
                ("home", g["local"], g["pts_local"], rh))):
            strong = winner is None or winner == side
            name = tk.Label(body, text=team, bg=SURFACE, anchor="w",
                            fg=INK if strong else INK_3, font=self.F["team"])
            name.grid(row=i, column=0, sticky="w")
            pj = tk.Label(body, text=fmt(num(proj)), bg=SURFACE, fg=INK_3, width=5, anchor="e",
                          font=self.F["small"])
            pj.grid(row=i, column=1, sticky="e")
            sc = tk.Label(body, text=fmt(real) if played else "", bg=SURFACE, width=4, anchor="e",
                          fg=INK if strong else INK_3, font=self.F["score_s"])
            sc.grid(row=i, column=2, sticky="e")
            widgets += [name, pj, sc]
        tk.Frame(self.inner, height=px(1), bg=RULE).pack(fill="x")

        def paint(bgc):
            for w in widgets[2:]:
                w.config(bg=bgc)
            row.config(bg=bgc)

        def enter(_):
            if self.selected != g["gameId"]:
                paint(HOVER)

        def leave(_):
            if self.selected != g["gameId"]:
                paint(SURFACE)

        for w in widgets:
            w.bind("<Button-1>", lambda e, gid=g["gameId"]: self.select(gid, fire=True))
            w.bind("<Enter>", enter)
            w.bind("<Leave>", leave)
        self.rows[g["gameId"]] = paint

    def select(self, gid, fire=False):
        if self.selected in self.rows:
            self.rows[self.selected](SURFACE)
        self.selected = gid
        if gid in self.rows:
            self.rows[gid](SELECT)
        if fire:
            self.on_select(gid)


# =====================================================================
# App
# =====================================================================
class App(tk.Tk):
    def __init__(self):
        register_fonts()
        super().__init__()
        self.title("NBA Forecasts")
        global K
        if sys.platform == "darwin":
            # Tk on macOS maps 1 pt to 1 px; match the Windows 96-dpi baseline
            self.tk.call("tk", "scaling", 96 / 72)
        else:
            K = max(1.0, float(self.tk.call("tk", "scaling")) / (96 / 72))
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(px(1320), int(sw * 0.95)), min(px(860), int(sh * 0.88))
        self.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")
        self.minsize(min(px(1100), w), min(px(660), h))
        if h < px(860) and sys.platform == "win32":
            self.state("zoomed")  # small or scaled screen: use all of it
        self.configure(bg=PAGE)
        try:
            self.iconbitmap(resource_path("nba.ico"))
        except Exception:
            pass

        self._fonts()
        self.cache = {}
        self.data = None
        self.current_game = None
        self.date_idx = 0
        self.mode = "both"
        self.side = 0
        self.dataset_name = tk.StringVar(value=list(DATASETS)[0])

        self._style()
        self._build()
        self.load()

    # ---------- fonts & ttk styles ----------
    def _fonts(self):
        fams = set(tkfont.families(self))

        def pick(exact, base, fallback, bold):
            """Windows exposes each weight as its own family ('Barlow SemiBold'); other
            systems expose one family plus a weight. Fall back to a system font."""
            if exact in fams:
                return lambda size: (exact, size)
            if base in fams:
                return lambda size: (base, size, "bold") if bold else (base, size)
            fb = next((f for f in fallback if f in fams), "TkDefaultFont")
            return lambda size: (fb, size)

        body = pick("Barlow", "Barlow", ["Segoe UI"], False)
        med = pick("Barlow Medium", "Barlow", ["Segoe UI Semibold", "Segoe UI"], False)
        semi = pick("Barlow SemiBold", "Barlow", ["Segoe UI Semibold", "Segoe UI"], True)
        cond = pick("Barlow Condensed SemiBold", "Barlow Condensed",
                    ["Bahnschrift SemiBold SemiConden", "Bahnschrift", "Segoe UI Semibold"], True)
        cond_m = pick("Barlow Condensed Medium", "Barlow Condensed",
                      ["Bahnschrift SemiCondensed", "Bahnschrift", "Segoe UI"], False)
        self.F = {
            "body": body(11), "small": body(10), "tiny": body(9),
            "med": med(11), "semi": semi(11), "team": med(12),
            "brand": cond(22), "nav": cond_m(15), "h": cond(17),
            "score_s": cond(16), "score": cond(42), "team_big": cond(24),
            "figure": cond(34), "head": semi(10), "arrow": cond(20),
        }

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        F = self.F
        s.configure(".", background=SURFACE, foreground=INK, font=F["body"], bordercolor=RULE,
                    lightcolor=RULE, darkcolor=RULE, troughcolor=SURFACE,
                    selectbackground=SELECT, selectforeground=INK)
        s.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=INK,
                    rowheight=px(27), borderwidth=0, font=F["body"])
        s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        s.map("Treeview", background=[("selected", SELECT)], foreground=[("selected", INK)])
        s.configure("Treeview.Heading", background=SURFACE, foreground=INK_2, relief="flat",
                    font=F["head"], padding=(px(4), px(6)), borderwidth=0)
        s.map("Treeview.Heading", background=[("active", SURFACE)])
        s.configure("Vertical.TScrollbar", background="#C9CFD7", troughcolor=SURFACE, borderwidth=0,
                    arrowsize=0, gripcount=0, width=px(8), bordercolor=SURFACE, lightcolor="#C9CFD7",
                    darkcolor="#C9CFD7")
        s.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
            ("Vertical.Scrollbar.thumb", {"expand": 1, "sticky": "nswe"})]})])
        s.map("Vertical.TScrollbar", background=[("active", INK_3)])
        s.configure("TCombobox", foreground=INK, background=SURFACE, fieldbackground=SURFACE,
                    arrowcolor=INK_2, padding=(px(6), px(3)), bordercolor=RULE)
        s.map("TCombobox", fieldbackground=[("readonly", SURFACE)], foreground=[("readonly", INK)],
              background=[("readonly", SURFACE)], bordercolor=[("focus", INK_3)],
              selectbackground=[("readonly", SURFACE)], selectforeground=[("readonly", INK)])
        self.option_add("*TCombobox*Listbox.font", F["body"])
        self.option_add("*TCombobox*Listbox.selectBackground", SELECT)
        self.option_add("*TCombobox*Listbox.selectForeground", INK)

    def _link(self, parent, text, cmd, bg=SURFACE, font=None, fg=INK_2):
        l = tk.Label(parent, text=text, bg=bg, fg=fg, cursor="hand2", font=font or self.F["med"])
        l.bind("<Button-1>", lambda e: cmd())
        l.bind("<Enter>", lambda e: l.config(fg=INK))
        l.bind("<Leave>", lambda e: l.config(fg=fg))
        return l

    def _tree(self, parent, cols, widths, height):
        wrap = tk.Frame(parent, bg=SURFACE)
        t = ttk.Treeview(wrap, columns=cols, show="headings", height=height, selectmode="browse")
        for i, (c, w) in enumerate(zip(cols, widths)):
            a = "w" if i == 0 else "center"
            t.heading(c, text=c, anchor=a)
            t.column(c, width=px(w), anchor=a, stretch=True)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=sb.set)
        t.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y", padx=(px(4), px(0)))
        t.tag_configure("dnp", foreground=INK_3)
        t.tag_configure("miss", foreground=MISS)
        t.tag_configure("odd", background="#F7F8FA")
        return wrap, t

    # ---------- layout ----------
    def _build(self):
        F = self.F
        top = tk.Frame(self, bg=SURFACE, padx=px(24))
        top.pack(fill="x")
        tk.Frame(self, height=px(1), bg=RULE).pack(fill="x")

        tk.Label(top, text="NBA Forecasts", bg=SURFACE, fg=INK, font=F["brand"]).pack(
            side="left", pady=(px(10), px(8)))
        self.nav = Segmented(top, [("games", "Games"), ("perf", "Model performance")],
                             self.show_page, font=F["nav"])
        self.nav.pack(side="left", padx=(px(36), px(0)), pady=(px(16), px(0)), anchor="s")

        self._link(top, "GitHub", lambda: webbrowser.open(REPO_URL)).pack(side="right")
        self._link(top, "Refresh", lambda: self.load(force=True)).pack(side="right", padx=(px(0), px(22)))
        cb = ttk.Combobox(top, textvariable=self.dataset_name, values=list(DATASETS),
                          state="readonly", width=19, font=F["body"])
        cb.pack(side="right", padx=(px(0), px(26)))
        cb.bind("<<ComboboxSelected>>", lambda e: self.load())

        self.footer = tk.Label(self, text="", bg=PAGE, fg=INK_2, font=F["tiny"], anchor="w", padx=px(24))
        self.footer.pack(side="bottom", fill="x", pady=(px(0), px(6)))

        self.pages = tk.Frame(self, bg=PAGE)
        self.pages.pack(fill="both", expand=True, padx=px(24), pady=(px(18), px(8)))
        self.page_games = tk.Frame(self.pages, bg=PAGE)
        self.page_perf = tk.Frame(self.pages, bg=PAGE)
        self._build_games()
        self._build_perf()
        self.nav.select("games")
        self.show_page("games")

    def show_page(self, key):
        for p in (self.page_games, self.page_perf):
            p.pack_forget()
        (self.page_games if key == "games" else self.page_perf).pack(fill="both", expand=True)

    # ---------- Games page ----------
    def _build_games(self):
        F = self.F
        root = self.page_games

        left = tk.Frame(root, bg=SURFACE, width=px(300))
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        dn = tk.Frame(left, bg=SURFACE, padx=px(12), pady=px(12))
        dn.pack(fill="x")
        self.prev_btn = self._link(dn, "‹", lambda: self.step_date(+1), font=F["arrow"])
        self.prev_btn.pack(side="left")
        self.next_btn = self._link(dn, "›", lambda: self.step_date(-1), font=F["arrow"])
        self.next_btn.pack(side="right")
        self.date_lbl = tk.Label(dn, text="", bg=SURFACE, fg=INK, font=F["h"])
        self.date_lbl.pack()
        hdr = tk.Frame(left, bg=SURFACE, padx=px(16))
        hdr.pack(fill="x")
        tk.Label(hdr, text="Final", bg=SURFACE, fg=INK_3, font=F["tiny"], width=5, anchor="e").pack(side="right")
        tk.Label(hdr, text="Proj.", bg=SURFACE, fg=INK_3, font=F["tiny"], width=6, anchor="e").pack(side="right")
        tk.Frame(left, height=px(1), bg=RULE).pack(fill="x", pady=(px(4), px(0)))
        self.game_list = GameList(left, self.show_game, F)
        self.game_list.pack(fill="both", expand=True)
        legend = tk.Frame(left, bg=SURFACE, padx=px(16), pady=px(10))
        legend.pack(fill="x", side="bottom")
        for c, t in ((HIT, "picked the winner"), (MISS, "missed the winner")):
            r = tk.Frame(legend, bg=SURFACE)
            r.pack(anchor="w")
            tk.Frame(r, width=px(4), height=px(12), bg=c).pack(side="left", padx=(px(0), px(8)))
            tk.Label(r, text=t, bg=SURFACE, fg=INK_2, font=F["tiny"]).pack(side="left")

        right = tk.Frame(root, bg=PAGE)
        right.pack(side="left", fill="both", expand=True, padx=(px(18), px(0)))

        # matchup band: the split point is the win probability
        self.band = tk.Canvas(right, height=px(100), bg=PAGE, highlightthickness=0)
        self.band.pack(fill="x")
        self.band.bind("<Configure>", lambda e: self.draw_band())
        info = tk.Frame(right, bg=PAGE)
        info.pack(fill="x", pady=(px(8), px(0)))
        self.info_away = tk.Label(info, text="", bg=PAGE, fg=INK_2, font=F["small"], justify="left")
        self.info_away.pack(side="left")
        self.info_home = tk.Label(info, text="", bg=PAGE, fg=INK_2, font=F["small"], justify="right")
        self.info_home.pack(side="right")
        self.summary = tk.Label(right, text="", bg=PAGE, fg=INK, font=F["body"], justify="left",
                                anchor="w")
        self.summary.pack(fill="x", pady=(px(8), px(14)))
        self.summary.bind("<Configure>", lambda e: self.summary.config(wraplength=e.width))

        # player detail pinned to the bottom
        det = tk.Frame(right, bg=SURFACE, padx=px(18), pady=px(12))
        det.pack(side="bottom", fill="x", pady=(px(14), px(0)))
        self.player_lbl = tk.Label(det, text="", bg=SURFACE, fg=INK, font=F["semi"], anchor="w")
        self.player_lbl.pack(fill="x", pady=(px(0), px(4)))
        dcols = ("Stat", "Forecast", "80% range", "Last 10 avg.", "Actual", "Off by", "In range")
        wrap, self.detail = self._tree(det, dcols, (150, 80, 110, 110, 80, 80, 80), height=4)
        wrap.pack(fill="x")

        # box score
        box = tk.Frame(right, bg=SURFACE, padx=px(18), pady=px(12))
        box.pack(fill="both", expand=True)
        ctl = tk.Frame(box, bg=SURFACE)
        ctl.pack(fill="x")
        self.team_tabs = Segmented(ctl, [(0, ""), (1, "")], self.set_side, font=F["nav"])
        self.team_tabs.pack(side="left")
        self.view_tabs = Segmented(ctl, [("proj", "Projected"), ("real", "Actual"),
                                         ("both", "Projected / actual")], self.set_mode, font=F["med"])
        self.view_tabs.pack(side="right")
        self.view_tabs.select("both")
        self.team_note = tk.Label(box, text="", bg=SURFACE, fg=INK_2, font=F["small"], anchor="w")
        self.team_note.pack(fill="x", pady=(px(8), px(6)))
        cols = ("Player",) + tuple(BOX_COLS)
        wrap, self.box_tree = self._tree(box, cols, (170,) + (64,) * len(BOX_COLS), height=8)
        wrap.pack(fill="both", expand=True)
        self.box_tree.column("MIN", width=px(80))
        self.box_tree.bind("<<TreeviewSelect>>", lambda e: self.show_player())

    # ---------- Performance page ----------
    def _build_perf(self):
        F = self.F
        root = self.page_perf
        self.figures = tk.Frame(root, bg=SURFACE, padx=px(8), pady=px(14))
        self.figures.pack(fill="x")

        body = tk.Frame(root, bg=PAGE)
        body.pack(fill="both", expand=True, pady=(px(18), px(0)))
        lp = tk.Frame(body, bg=SURFACE, padx=px(18), pady=px(14))
        lp.pack(side="left", fill="both", expand=True)
        tk.Label(lp, text="Player stats against a last-10-games average", bg=SURFACE, fg=INK,
                 font=F["h"], anchor="w").pack(fill="x")
        tk.Label(lp, text="Mean absolute error over every scored day. Lower is better; the improvement "
                          "column is how much smaller the model's error is.",
                 bg=SURFACE, fg=INK_2, font=F["small"], anchor="w", justify="left", wraplength=px(560)
                 ).pack(fill="x", pady=(px(2), px(10)))
        cols = ("Stat", "Players", "Model error", "Average error", "Improvement", "In 80% range")
        wrap, self.perf_tree = self._tree(lp, cols, (150, 70, 95, 105, 100, 105), height=16)
        wrap.pack(fill="both", expand=True)

        rp = tk.Frame(body, bg=SURFACE, padx=px(18), pady=px(14))
        rp.pack(side="left", fill="both", expand=True, padx=(px(18), px(0)))
        tk.Label(rp, text="Improvement by stat", bg=SURFACE, fg=INK, font=F["h"], anchor="w").pack(fill="x")
        tk.Label(rp, text="Percent less error than the last-10-games average.", bg=SURFACE, fg=INK_2,
                 font=F["small"], anchor="w").pack(fill="x", pady=(px(2), px(6)))
        self.chart = tk.Canvas(rp, bg=SURFACE, highlightthickness=0)
        self.chart.pack(fill="both", expand=True)
        self.chart.bind("<Configure>", lambda e: self.draw_chart())
        self.chart_data = []

    # =================================================================
    # Loading
    # =================================================================
    def load(self, force=False):
        name = self.dataset_name.get()
        if force:
            self.cache.pop(name, None)
        if name in self.cache:
            self.set_data(self.cache[name])
            return
        self.footer.config(text=f"Loading {name}…")

        def work():
            try:
                ds = Dataset(name)
                self.after(0, lambda: self._loaded(name, ds))
            except Exception as e:
                msg = str(e)
                self.after(0, lambda: self.footer.config(
                    text=f"Couldn't load the forecasts ({msg}). Check your internet connection and "
                         "click Refresh.", fg=MISS))
        threading.Thread(target=work, daemon=True).start()

    def _loaded(self, name, ds):
        self.cache[name] = ds
        if name == self.dataset_name.get():
            self.set_data(ds)

    def set_data(self, ds):
        self.data = ds
        scored = sum(1 for g in ds.games if g["estado"] == "Jugado")
        src = "your local project folder" if ds.source != "GitHub" else "GitHub"
        self.footer.config(fg=INK_2, text=(
            f"Reading from {src}. {len(ds.dates)} days, {len(ds.games)} games forecast, "
            f"{scored} already scored."))
        self.date_idx = 0
        self.show_date()
        self.fill_perf()

    # =================================================================
    # Games
    # =================================================================
    def step_date(self, d):
        if not self.data:
            return
        i = self.date_idx + d
        if 0 <= i < len(self.data.dates):
            self.date_idx = i
            self.show_date()

    def show_date(self):
        ds = self.data
        if not ds or not ds.dates:
            return
        d = ds.dates[self.date_idx]
        self.date_lbl.config(text=nice_date(d, year=self.dataset_name.get() != list(DATASETS)[0]))
        self.prev_btn.config(fg=INK_2 if self.date_idx < len(ds.dates) - 1 else RULE)
        self.next_btn.config(fg=INK_2 if self.date_idx > 0 else RULE)
        games = ds.games_by_date.get(d, [])
        self.game_list.fill(games)
        if games:
            self.game_list.select(games[0]["gameId"], fire=True)
        else:
            self.current_game = None
            self.draw_band()
            self.fill_box()

    def show_game(self, gid):
        g = next(x for x in self.data.games if x["gameId"] == gid)
        if g is not self.current_game:
            self.side = 0
            self.team_tabs.select(0)
        self.current_game = g
        self.draw_band()

        home, away = g["local"], g["visitante"]
        proj_margin = num(g["spread"])
        s = (f"Projected total {g['total']}, {by_margin(home, away, proj_margin)}. ")
        if g["estado"] == "Jugado":
            real_margin = num(g["margen_real"])
            won = home if real_margin > 0 else away
            s += (f"Final total {fmt(num(g['real_total']))} (off by {g['error_total']}); "
                  f"{won} won by {abs(real_margin):.0f} (margin off by {g['error_spread']}). ")
            s += ("The model picked the winner." if num(g["acierto_ganador"]) == 1
                  else "The model picked the wrong winner.")
        else:
            gen = g.get("generado", "")
            s += f"Not played yet. Forecast made {gen}." if gen else "Not played yet."
        self.summary.config(text=s)
        self.fill_box()

    def draw_band(self):
        c = self.band
        c.delete("all")
        g = self.current_game
        W, H = c.winfo_width(), c.winfo_height()
        if not g or W < 50:
            for l in (getattr(self, "info_away", None), getattr(self, "info_home", None)):
                if l:
                    l.config(text="")
            return
        F = self.F
        away, home = g["visitante"], g["local"]
        ca, ch = matchup_colors(away, home)
        p = num(g["prob_local"]) or 0.5
        x = int(W * (1 - p))
        x = max(px(190), min(W - px(190), x))
        c.create_rectangle(0, 0, x, H, fill=ca, outline="")
        c.create_rectangle(x, 0, W, H, fill=ch, outline="")
        played = g["estado"] == "Jugado"
        for team, xx, anchor, pts, real in (
                (away, px(22), "w", num(g["pts_visita"]), num(g["real_visita"])),
                (home, W - px(22), "e", num(g["pts_local"]), num(g["real_local"]))):
            c.create_text(xx, px(24), text=team, anchor=anchor, fill="white", font=F["team_big"])
            if played and real is not None:
                c.create_text(xx, px(66), text=fmt(real), anchor=anchor, fill="white", font=F["score"])
            else:  # not played: the projection, dimmed and labelled
                t = c.create_text(xx, px(66), text=fmt(pts), anchor=anchor, fill="#C9D1DB", font=F["score"])
                x1, _, x2, _ = c.bbox(t)
                lx, la = (x2 + px(8), "w") if anchor == "w" else (x1 - px(8), "e")
                c.create_text(lx, px(80), text="projected", anchor=la, fill="#C9D1DB", font=F["small"])
        c.create_line(x, 0, x, H, fill="white", width=2)

        def info(where, prob, pts, q10, q90):
            return f"{where}, {prob:.0%} to win\nProjected {pts} (80% range {q10} to {q90})"
        self.info_away.config(text=info("Away", 1 - p, g["pts_visita"], g["pts_visita_q10"],
                                        g["pts_visita_q90"]))
        self.info_home.config(text=info("Home", p, g["pts_local"], g["pts_local_q10"],
                                        g["pts_local_q90"]))

    def _cell(self, p, col, mode):
        r = p["stats"].get(col)
        proj = fmt(num(r["pronostico"])) if r else "–"
        val = num(r["real"]) if r else None
        if p["status"] == "No jugó":
            real = "DNP"
        elif p["status"] == "Pendiente" or val is None:
            real = ""
        else:
            real = fmt(round(val))
        if mode == "proj":
            return proj
        if mode == "real":
            return real or "–"
        if real == "DNP":
            return "DNP" if col == "MIN" else ""
        return f"{proj} / {real}" if real else proj

    def set_side(self, side):
        self.side = side
        self.fill_box()

    def set_mode(self, mode):
        self.mode = mode
        self.fill_box()

    def fill_box(self):
        t = self.box_tree
        t.delete(*t.get_children())
        self.detail.delete(*self.detail.get_children())
        self.player_lbl.config(text="Select a player to see all 16 stats with their 80% ranges.")
        g = self.current_game
        if not g or not self.data:
            self.team_note.config(text="")
            return
        teams = (g["visitante"], g["local"])
        cols = matchup_colors(*teams)
        for side in (0, 1):
            self.team_tabs.set_text(side, teams[side], cols[side])
        team = teams[self.side]
        players = self.data.box.get(g["gameId"], {})
        roster = [(pid, p) for pid, p in players.items() if p["team"] == team]
        roster.sort(key=lambda x: (x[1]["status"] == "No jugó",
                                   -(num(x[1]["stats"].get("MIN", {}).get("pronostico")) or 0)))
        pts = sum(num(p["stats"].get("PTS", {}).get("pronostico")) or 0 for _, p in roster)
        adj = roster[0][1]["stats"].get("MIN", {}).get("ajuste_equipo", "") if roster else ""
        note = f"{len(roster)} players, {pts:.0f} projected points between them"
        if adj:
            note += f", scaled ×{adj} so the total matches the team-score forecast"
        self.team_note.config(text=note + ".")
        for i, (pid, p) in enumerate(roster):
            vals = (p["name"],) + tuple(self._cell(p, c, self.mode) for c in BOX_COLS)
            tags = ["odd"] if i % 2 else []
            if p["status"] == "No jugó":
                tags.append("dnp")
            t.insert("", "end", iid=pid, values=vals, tags=tags)

    def show_player(self):
        sel = self.box_tree.selection()
        if not sel or not self.current_game:
            return
        p = self.data.box[self.current_game["gameId"]][sel[0]]
        status = {"Jugó": "played", "No jugó": "did not play", "Pendiente": "game not played yet"}.get(
            p["status"], p["status"])
        self.player_lbl.config(text=f"{p['name']}, {p['team']} ({status})")
        d = self.detail
        d.delete(*d.get_children())
        rows = sorted(p["stats"].values(), key=lambda r: int(r["orden"]))
        rows.sort(key=lambda r: (r["estadistica"] != "PTS", r["estadistica"] != "MIN"))
        for i, r in enumerate(rows):
            inside = num(r["dentro_80"])
            tags = ["odd"] if i % 2 else []
            if inside == 0:
                tags.append("miss")
            d.insert("", "end", values=(
                STAT_NAMES.get(r["estadistica"], r["estadistica"]),
                r["pronostico"], f"{r['q10']} to {r['q90']}", r["baseline"],
                fmt(num(r["real"])) if r["real"] else "–",
                fmt(num(r["error_abs"]), 2) if r["error_abs"] else "–",
                "–" if inside is None else ("yes" if inside == 1 else "no"),
            ), tags=tags)

    # =================================================================
    # Performance
    # =================================================================
    def _figure(self, value, label, note="", first=False):
        F = self.F
        if not first:
            tk.Frame(self.figures, width=px(1), bg=RULE).pack(side="left", fill="y", pady=px(4))
        f = tk.Frame(self.figures, bg=SURFACE, padx=px(18))
        f.pack(side="left", fill="both", expand=True)
        tk.Label(f, text=value, bg=SURFACE, fg=INK, font=F["figure"], anchor="w").pack(fill="x")
        tk.Label(f, text=label, bg=SURFACE, fg=INK, font=F["med"], anchor="w").pack(fill="x")
        tk.Label(f, text=note, bg=SURFACE, fg=INK_3, font=F["tiny"], anchor="w").pack(fill="x")

    def fill_perf(self):
        for w in self.figures.winfo_children():
            w.destroy()
        ds = self.data
        played = [g for g in ds.games if g["estado"] == "Jugado"]
        n = len(played)

        def mean(key):
            vals = [num(g[key]) for g in played if num(g[key]) is not None]
            return sum(vals) / len(vals) if vals else None

        acc, brier = mean("acierto_ganador"), mean("brier")
        e_tot, e_spr = mean("error_total"), mean("error_spread")
        cov = None
        if n:
            cov = sum((num(g["dentro_80_local"]) or 0) + (num(g["dentro_80_visita"]) or 0)
                      for g in played) / (2 * n)
        dash = "–"
        self._figure(str(n), "Games scored", "played games with a forecast", first=True)
        self._figure(dash if acc is None else f"{acc:.0%}", "Winners picked",
                     dash if acc is None else f"{round(acc * n)} of {n}")
        self._figure(dash if brier is None else f"{brier:.3f}", "Brier score", "0.250 is a coin flip")
        self._figure(dash if e_tot is None else f"{e_tot:.1f}", "Total points error", "average, in points")
        self._figure(dash if e_spr is None else f"{e_spr:.1f}", "Margin error", "average, in points")
        self._figure(dash if cov is None else f"{cov:.0%}", "Team scores in 80% range",
                     "should land near 80%")

        agg = {}
        for r in ds.score:
            w = num(r["jugadores"]) or 0
            a = agg.setdefault(r["estadistica"], [0, 0.0, 0.0, 0.0])
            a[0] += w
            a[1] += w * (num(r["MAE"]) or 0)
            a[2] += w * (num(r["MAE_baseline"]) or 0)
            a[3] += w * (num(r["cobertura_80"]) or 0)
        t = self.perf_tree
        t.delete(*t.get_children())
        self.chart_data = []
        order = ["PTS", "REB", "AST", "MIN", "STL", "BLK", "TO", "3PM", "3PA",
                 "FGM", "FGA", "FTM", "FTA", "OREB", "DREB", "PF"]
        i = 0
        for code in order:
            if code not in agg or agg[code][0] == 0:
                continue
            w, m, mb, c = agg[code]
            mae, maeb, cv = m / w, mb / w, c / w
            imp = (1 - mae / maeb) * 100 if maeb else 0
            tags = ["odd"] if i % 2 else []
            if imp < 0:
                tags.append("miss")
            t.insert("", "end", values=(STAT_NAMES.get(code, code), int(w), f"{mae:.2f}", f"{maeb:.2f}",
                                        f"{imp:+.1f}%", f"{cv:.0%}"), tags=tags)
            self.chart_data.append((STAT_NAMES.get(code, code), imp))
            i += 1
        self.draw_chart()

    def draw_chart(self):
        c = self.chart
        c.delete("all")
        data = self.chart_data
        W, H = c.winfo_width(), c.winfo_height()
        if not data or W < px(80) or H < px(80):
            return
        F = self.F
        lo = min(0.0, min(v for _, v in data))
        hi = max(5.0, max(v for _, v in data))
        left, right, top, bottom = px(118), px(52), px(4), px(26)
        span = hi - lo
        plot_w = W - left - right
        row_h = min(px(30), (H - top - bottom) / len(data))
        X = lambda v: left + (v - lo) / span * plot_w
        x0 = X(0)
        # light gridlines every 5%
        step = 5 if span <= 40 else 10
        g = (int(lo // step)) * step
        while g <= hi:
            xg = X(g)
            c.create_line(xg, top, xg, top + row_h * len(data), fill="#EEF1F4")
            c.create_text(xg, top + row_h * len(data) + px(12), text=f"{g:g}%", fill=INK_3, font=F["tiny"])
            g += step
        for i, (name, v) in enumerate(data):
            y = top + i * row_h
            xv = X(v)
            c.create_rectangle(min(x0, xv), y + row_h * 0.22, max(x0, xv), y + row_h * 0.78,
                               fill=BAR if v >= 0 else MISS, outline="")
            c.create_text(left - px(10), y + row_h / 2, text=name, anchor="e", fill=INK_2, font=F["small"])
            c.create_text(xv + (6 if v >= 0 else -6), y + row_h / 2, text=f"{v:.1f}",
                          anchor="w" if v >= 0 else "e", fill=INK, font=F["small"])
        c.create_line(x0, top, x0, top + row_h * len(data), fill=INK_3)


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    App().mainloop()


if __name__ == "__main__":
    main()
