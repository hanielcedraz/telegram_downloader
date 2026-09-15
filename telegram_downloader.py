#!/usr/bin/env python3
"""
Telegram Group Downloader
-------------------------
App desktop (Tkinter) para:
  1. logar no Telegram via Telethon
  2. listar grupos/canais
  3. analisar quantos arquivos e quantos GB existem, por tipo
  4. selecionar os tipos desejados e baixar

Requisitos: nenhum passo manual — o script instala o que faltar na primeira execução.

Rodar:
    python3 telegram_downloader.py

Config e sessão ficam em ~/.tg_downloader/
"""

import importlib
import importlib.util
import os
import platform
import subprocess
import sys


# --------------------------------------------------------------------------
# Bootstrap: garante as dependências antes de qualquer import pesado
# --------------------------------------------------------------------------
def _instalar(pacote: str) -> bool:
    """Tenta instalar um pacote via pip. Devolve True se deu certo."""
    base = [sys.executable, "-m", "pip", "install", pacote]
    # em ambiente gerenciado (Homebrew/Debian) o pip recusa sem --user
    tentativas = [base, base + ["--user"]]
    for cmd in tentativas:
        print(f"→ {' '.join(cmd)}")
        if subprocess.call(cmd) == 0:
            importlib.invalidate_caches()
            return True
    return False


def _garantir(modulo: str, pacote: str = None, opcional: bool = False) -> bool:
    """Importa o módulo; se faltar, instala o pacote correspondente."""
    pacote = pacote or modulo
    if importlib.util.find_spec(modulo) is not None:
        return True

    rotulo = "opcional" if opcional else "obrigatória"
    print(f"Dependência {rotulo} ausente: {pacote}. Instalando...")
    if _instalar(pacote):
        if importlib.util.find_spec(modulo) is not None:
            print(f"✓ {pacote} instalado.\n")
            return True

    if opcional:
        print(f"! Não consegui instalar {pacote} (opcional). Seguindo sem ele.\n")
        return False

    print(
        f"\nFalha ao instalar {pacote}.\n"
        f"Instale manualmente e rode de novo:\n"
        f"    {sys.executable} -m pip install {pacote}\n"
        f"Se aparecer 'externally-managed-environment', use um ambiente virtual:\n"
        f"    python3 -m venv ~/.venvs/telegram\n"
        f"    source ~/.venvs/telegram/bin/activate   # Windows: "
        f"~\\.venvs\\telegram\\Scripts\\activate\n"
        f"    pip install {pacote}\n"
    )
    sys.exit(1)
    return False


def _checar_tkinter():
    """tkinter não se instala por pip — orienta conforme o sistema."""
    if importlib.util.find_spec("tkinter") is not None:
        # presente, mas o Tk 8.5 da Apple aborta em macOS recente
        try:
            import tkinter as _tk
            if float(_tk.TkVersion) < 8.6:
                print(
                    f"\nEste Python usa Tcl/Tk {_tk.TkVersion}, que trava no "
                    f"macOS atual.\n"
                    f"Interpretador em uso: {sys.executable}\n\n"
                    "Provavelmente voce rodou com o Python do sistema em vez do "
                    "ambiente virtual.\n"
                    "Ative o venv e rode de novo:\n\n"
                    "    source ~/.venvs/telegram/bin/activate\n"
                    "    python --version        # deve mostrar 3.12.x\n"
                    f"    python {os.path.basename(sys.argv[0])}\n\n"
                    "Se o venv ainda nao existe:\n\n"
                    "    brew install python@3.12 python-tk@3.12\n"
                    "    python3.12 -m venv ~/.venvs/telegram\n"
                    "    source ~/.venvs/telegram/bin/activate\n"
                )
                sys.exit(1)
        except ImportError:
            pass
        return
    so = platform.system()
    dicas = {
        "Darwin": "brew install python@3.12 python-tk@3.12\n"
                  "  (ou instale o Python de python.org, que já inclui Tk 8.6)",
        "Linux": "sudo apt install python3-tk      # Debian/Ubuntu\n"
                 "  sudo dnf install python3-tkinter  # Fedora",
        "Windows": "reinstale o Python do python.org marcando 'tcl/tk and IDLE'",
    }
    print(
        "\nO módulo tkinter não está disponível neste Python.\n"
        "Ele faz parte da biblioteca padrão, mas nem sempre vem incluído.\n\n"
        f"{dicas.get(so, dicas['Linux'])}\n"
    )
    sys.exit(1)


def _bootstrap():
    """Verifica dependências uma vez. Nada é instalado se já estiver presente."""
    _checar_tkinter()

    # obrigatória
    _garantir("telethon", "telethon")

    # opcional: acelera a criptografia. Se já houver qualquer uma das duas
    # aceleradoras, ou se uma tentativa anterior falhou, não tenta de novo.
    if any(importlib.util.find_spec(m) for m in ("cryptg", "Crypto")):
        return
    marcador = os.path.join(os.path.expanduser("~"), ".tg_downloader",
                            ".sem_acelerador")
    if os.path.exists(marcador):
        return
    # Pillow: necessaria para exibir miniaturas JPEG na pre-visualizacao
    _garantir("PIL", "pillow", opcional=True)

    if not _garantir("Crypto", "pycryptodome", opcional=True):
        os.makedirs(os.path.dirname(marcador), exist_ok=True)
        with open(marcador, "w") as f:
            f.write(
                "Tentativa de instalar pycryptodome falhou neste ambiente.\n"
                "O app funciona sem ele (mais lento em download em massa).\n"
                "Apague este arquivo para tentar de novo.\n"
            )
        print("  (registrado; não tentarei de novo nas próximas aberturas)\n")


_bootstrap()


import asyncio
import json
import queue
import shutil
import threading
import tkinter as tk
import webbrowser
from collections import defaultdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageTk
    TEM_PIL = True
except ImportError:
    TEM_PIL = False

from telethon import TelegramClient
from telethon.errors import (
    ChatForwardsRestrictedError,
    FloodWaitError,
    SessionPasswordNeededError,
)

APP_DIR = Path.home() / ".tg_downloader"
APP_DIR.mkdir(exist_ok=True)
CONFIG_FILE = APP_DIR / "config.json"
SESSION = str(APP_DIR / "sessao")
THUMB_DIR = APP_DIR / "thumbs"
THUMB_DIR.mkdir(exist_ok=True)


# --------------------------------------------------------------------------
# Categorias de arquivo (extensão -> pasta)
# --------------------------------------------------------------------------
CATEGORIAS = {
    "modelos-3d": (".stl", ".3mf", ".obj", ".step", ".stp", ".iges", ".igs",
                   ".ply", ".amf", ".scad", ".f3d", ".fbx", ".dae", ".blend",
                   ".gcode", ".bgcode", ".gco"),
    "imagens": (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff",
                ".tif", ".heic", ".svg"),
    "videos": (".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv", ".flv"),
    "audio": (".mp3", ".wav", ".ogg", ".oga", ".flac", ".m4a", ".aac", ".opus"),
    "documentos": (".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md",
                   ".epub", ".mobi", ".djvu"),
    "planilhas": (".xls", ".xlsx", ".ods", ".csv", ".tsv"),
    "apresentacoes": (".ppt", ".pptx", ".odp"),
    "compactados": (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".zst"),
    "codigo": (".py", ".js", ".ts", ".c", ".cpp", ".h", ".java", ".rb", ".go",
               ".rs", ".sh", ".json", ".xml", ".yaml", ".yml", ".ini", ".cfg"),
    "fontes": (".ttf", ".otf", ".woff", ".woff2"),
    "instaladores": (".dmg", ".pkg", ".exe", ".msi", ".deb", ".rpm", ".appimage"),
}

# indice invertido: extensao -> categoria
_EXT2CAT = {ext: cat for cat, exts in CATEGORIAS.items() for ext in exts}

MODOS_ORG = (
    "Pasta única",
    "Categoria",
    "Categoria / extensão",
    "Extensão",
    "Ano-mês",
    "Ano-mês / categoria",
)


def categoria_de(ext: str) -> str:
    """Devolve a categoria de uma extensão (.stl -> modelos-3d)."""
    return _EXT2CAT.get((ext or "").lower(), "outros")


def subpasta(modo: str, ext: str, data=None) -> str:
    """Caminho relativo onde o arquivo deve ser salvo, conforme o modo."""
    ext = (ext or "").lower()
    limpa = ext.lstrip(".") or "sem-extensao"
    cat = categoria_de(ext)
    ym = data.strftime("%Y-%m") if data else "sem-data"

    if modo == "Categoria":
        return cat
    if modo == "Categoria / extensão":
        return os.path.join(cat, limpa)
    if modo == "Extensão":
        return limpa
    if modo == "Ano-mês":
        return ym
    if modo == "Ano-mês / categoria":
        return os.path.join(ym, cat)
    return ""  # Pasta única


# --------------------------------------------------------------------------
# Infra: loop asyncio em thread separada
# --------------------------------------------------------------------------
class AsyncRunner:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro, callback=None, tk_root=None):
        """Agenda a corrotina. callback(resultado, erro) roda na thread do Tk."""
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)

        if callback:
            def _done(f):
                try:
                    res, err = f.result(), None
                except Exception as e:  # noqa: BLE001
                    res, err = None, e
                if tk_root:
                    tk_root.after(0, callback, res, err)
                else:
                    callback(res, err)

            fut.add_done_callback(_done)
        return fut


def human(n_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n_bytes) < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} PB"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:  # noqa: BLE001
            return {}
    return {}


def save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    os.chmod(CONFIG_FILE, 0o600)


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Telegram Group Downloader")
        self.geometry("1000x720")
        self.minsize(880, 620)

        self.runner = AsyncRunner()
        self.client = None
        self.cfg = load_config()

        self.dialogs = []          # lista de (nome, entity)
        self.scan_index = {}       # ext -> lista de dicts {id, size, name}
        self._por_cat = {}         # categoria -> lista de extensoes
        self._por_id = {}          # msg id -> item
        self._por_grupo = {}       # grouped_id -> itens do mesmo post
        self._thumb_atual = None   # referencia viva da imagem no Tk
        self._item_prev = None
        self._fotos_prev = []
        self._idx_prev = 0
        self.current_entity = None
        self.cancel_flag = threading.Event()
        self.log_queue = queue.Queue()

        self.dest_var = tk.StringVar(value=str(Path.home() / "Downloads" / "telegram"))
        self.status_var = tk.StringVar(value="Desconectado")
        self.dedup_var = tk.BooleanVar(value=True)
        self.resume_var = tk.BooleanVar(value=True)
        self.limit_var = tk.StringVar(value="0")
        self.org_var = tk.StringVar(value="Categoria")
        self.filter_var = tk.StringVar()

        self._build_ui()
        self._preview_org()
        self._drain_log()
        self.after(300, self._auto_connect)

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("aqua")  # macOS
        except tk.TclError:
            pass

        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        # --- barra de status / conexão
        top = ttk.Frame(outer)
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="Status:").pack(side="left")
        ttk.Label(top, textvariable=self.status_var, foreground="#555").pack(
            side="left", padx=(6, 16)
        )
        self.btn_login = ttk.Button(top, text="Conectar", command=self._open_login)
        self.btn_login.pack(side="right")

        # divisor arrastável entre as abas e o log
        paned = ttk.PanedWindow(outer, orient="vertical")
        paned.pack(fill="both", expand=True)

        nb_frame = ttk.Frame(paned)
        nb_frame.configure(height=380)
        self.nb = ttk.Notebook(nb_frame)
        self.nb.pack(fill="both", expand=True)
        paned.add(nb_frame, weight=4)
        # impede que a divisória seja arrastada a ponto de sumir com as abas
        paned.bind("<B1-Motion>", self._limitar_divisoria, add="+")
        paned.bind("<ButtonRelease-1>", self._limitar_divisoria, add="+")
        self._paned = paned

        self._build_tab_grupos()
        self._build_tab_analise()

        # --- log (arraste a divisória acima para aumentar)
        log_frame = ttk.Frame(paned)
        cab = ttk.Frame(log_frame)
        cab.pack(fill="x", pady=(8, 2))
        ttk.Label(cab, text="Log").pack(side="left")
        ttk.Label(cab, text="(arraste a divisória acima para ampliar)",
                  foreground="#888").pack(side="left", padx=8)
        ttk.Button(cab, text="Limpar", command=self._clear_log).pack(side="right")

        caixa = ttk.Frame(log_frame)
        caixa.pack(fill="both", expand=True)
        self.log = tk.Text(caixa, height=8, wrap="word", font=("Menlo", 11))
        barra = ttk.Scrollbar(caixa, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=barra.set)
        barra.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)
        self.log.configure(state="disabled")
        paned.add(log_frame, weight=1)

    def _limitar_divisoria(self, _evt=None):
        """Garante uma altura minima para as abas."""
        try:
            pos = self._paned.sashpos(0)
        except Exception:  # noqa: BLE001
            return
        if pos < 320:
            self._paned.sashpos(0, 320)

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _build_tab_grupos(self):
        tab = ttk.Frame(self.nb, padding=10)
        self.nb.add(tab, text="1. Grupos")

        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Button(bar, text="Carregar grupos", command=self.load_dialogs).pack(side="left")
        ttk.Label(bar, text="Filtrar:").pack(side="left", padx=(16, 4))
        ent = ttk.Entry(bar, textvariable=self.filter_var, width=30)
        ent.pack(side="left")
        ent.bind("<KeyRelease>", lambda _e: self._render_dialogs())

        ttk.Label(bar, text="ou @username / link:").pack(side="left", padx=(16, 4))
        self.manual_var = tk.StringVar()
        ttk.Entry(bar, textvariable=self.manual_var, width=24).pack(side="left")
        ttk.Button(bar, text="Usar", command=self.use_manual).pack(side="left", padx=4)

        # empacotado ANTES da tabela para nunca ser espremido para fora
        rodape = ttk.Frame(tab)
        rodape.pack(side="bottom", fill="x", pady=(8, 0))
        ttk.Button(rodape, text="Analisar grupo selecionado →",
                   command=self.analyze_selected).pack(side="right")

        corpo = ttk.Frame(tab)
        corpo.pack(side="top", fill="both", expand=True)
        cols = ("nome", "tipo", "id")
        self.tree_dialogs = ttk.Treeview(corpo, columns=cols, show="headings", height=8)
        rol_d = ttk.Scrollbar(corpo, orient="vertical",
                              command=self.tree_dialogs.yview)
        self.tree_dialogs.configure(yscrollcommand=rol_d.set)
        for c, w in zip(cols, (520, 120, 160)):
            self.tree_dialogs.heading(c, text=c.capitalize())
            self.tree_dialogs.column(c, width=w, anchor="w")
        rol_d.pack(side="right", fill="y")
        self.tree_dialogs.pack(side="left", fill="both", expand=True)
        self.tree_dialogs.bind("<Double-1>", lambda _e: self.analyze_selected())


    def _build_tab_analise(self):
        tab = ttk.Frame(self.nb, padding=10)
        self.nb.add(tab, text="2. Análise e download")

        head = ttk.Frame(tab)
        head.pack(side="top", fill="x", pady=(0, 8))
        self.grupo_label = ttk.Label(head, text="Nenhum grupo selecionado",
                                     font=("Helvetica", 13, "bold"))
        self.grupo_label.pack(side="left")
        ttk.Label(head, text="Limite de msgs (0 = tudo):").pack(side="left", padx=(20, 4))
        ttk.Entry(head, textvariable=self.limit_var, width=8).pack(side="left")
        self.btn_scan = ttk.Button(head, text="Analisar", command=self.start_scan)
        self.btn_scan.pack(side="left", padx=8)

        # ---- controles fixos: empacotados de baixo para cima, ANTES da tabela,
        #      para que encolher a aba nunca os esconda
        act = ttk.Frame(tab)
        act.pack(side="bottom", fill="x", pady=(12, 0))
        self.btn_download = ttk.Button(act, text="Baixar selecionados",
                                       command=self.start_download)
        self.btn_download.pack(side="left")
        self.btn_cancel = ttk.Button(act, text="Cancelar", state="disabled",
                                     command=lambda: self.cancel_flag.set())
        self.btn_cancel.pack(side="left", padx=8)
        self.progress = ttk.Progressbar(act, mode="determinate", length=380)
        self.progress.pack(side="left", padx=12, fill="x", expand=True)
        self.prog_label = ttk.Label(act, text="")
        self.prog_label.pack(side="left")

        dest = ttk.Frame(tab)
        dest.pack(side="bottom", fill="x", pady=(10, 0))
        ttk.Label(dest, text="Destino:").pack(side="left")
        ttk.Entry(dest, textvariable=self.dest_var).pack(
            side="left", fill="x", expand=True, padx=6)
        ttk.Button(dest, text="Escolher...", command=self.choose_dest).pack(side="left")
        self.disk_label = ttk.Label(dest, text="")
        self.disk_label.pack(side="left", padx=10)

        org = ttk.Frame(tab)
        org.pack(side="bottom", fill="x", pady=(10, 0))
        ttk.Label(org, text="Organizar em:").pack(side="left")
        combo = ttk.Combobox(org, textvariable=self.org_var, values=MODOS_ORG,
                             state="readonly", width=22)
        combo.pack(side="left", padx=6)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._preview_org())
        self.org_label = ttk.Label(org, text="", foreground="#666")
        self.org_label.pack(side="left", padx=10)
        ttk.Button(org, text="Reorganizar pasta destino",
                   command=self.reorganizar).pack(side="right")

        opts = ttk.Frame(tab)
        opts.pack(side="bottom", fill="x", pady=(10, 0))
        ttk.Checkbutton(opts, text="Ignorar duplicatas (mesmo nome + tamanho)",
                        variable=self.dedup_var,
                        command=self._update_selection_label).pack(side="left")
        ttk.Checkbutton(opts, text="Retomar (pular já baixados)",
                        variable=self.resume_var).pack(side="left", padx=16)

        sel = ttk.Frame(tab)
        sel.pack(side="bottom", fill="x", pady=(6, 0))
        ttk.Button(sel, text="Selecionar tudo",
                   command=lambda: self.tree_ext.selection_set(
                       self.tree_ext.get_children())).pack(side="left")
        ttk.Button(sel, text="Expandir tudo",
                   command=self._expandir_categorias).pack(side="left", padx=6)
        ttk.Button(sel, text="Limpar seleção",
                   command=lambda: self.tree_ext.selection_remove(
                       self.tree_ext.get_children())).pack(side="left", padx=6)
        self.sel_label = ttk.Label(sel, text="Nada selecionado", foreground="#333")
        self.sel_label.pack(side="left", padx=16)

        # ---- corpo: arvore a esquerda, pre-visualizacao a direita
        split = ttk.PanedWindow(tab, orient="horizontal")
        split.pack(side="top", fill="both", expand=True)

        corpo = ttk.Frame(split)
        split.add(corpo, weight=3)
        cols = ("tipo", "arquivos", "tamanho", "bytes")
        self.tree_ext = ttk.Treeview(corpo, columns=cols, show="tree headings",
                                     selectmode="extended", height=6)
        self.tree_ext.column("#0", width=28, stretch=False)
        rol_e = ttk.Scrollbar(corpo, orient="vertical", command=self.tree_ext.yview)
        self.tree_ext.configure(yscrollcommand=rol_e.set)
        for c, w, anchor in (
            ("tipo", 160, "w"),
            ("arquivos", 120, "e"),
            ("tamanho", 140, "e"),
            ("bytes", 0, "e"),
        ):
            titulo = {"tipo": "Categoria / tipo / arquivo",
                      "arquivos": "Arquivos"}.get(c, c.capitalize())
            self.tree_ext.heading(c, text=titulo)
            largura = 420 if c == "tipo" else w
            self.tree_ext.column(c, width=largura, anchor=anchor,
                                 stretch=(c == "tipo"))
        self.tree_ext.column("bytes", width=0, stretch=False)  # coluna oculta
        rol_e.pack(side="right", fill="y")
        self.tree_ext.pack(side="left", fill="both", expand=True)
        self.tree_ext.bind("<<TreeviewSelect>>", lambda _e: (
            self._update_selection_label(), self._on_select_preview()))
        self.tree_ext.bind("<<TreeviewOpen>>", self._expandir_no)

        # ---- painel de pre-visualizacao
        prev = ttk.Frame(split, padding=(10, 0, 0, 0))
        split.add(prev, weight=2)
        ttk.Label(prev, text="Pré-visualização",
                  font=("Helvetica", 12, "bold")).pack(anchor="w")

        self.canvas_prev = tk.Canvas(prev, width=300, height=300,
                                     highlightthickness=1,
                                     highlightbackground="#ccc")
        self.canvas_prev.pack(pady=(6, 6))
        self._msg_prev = self.canvas_prev.create_text(
            150, 150, text="selecione um arquivo", fill="#999", width=260)

        self.prev_info = ttk.Label(prev, text="", wraplength=300,
                                   justify="left", foreground="#444")
        self.prev_info.pack(anchor="w")

        nav = ttk.Frame(prev)
        nav.pack(anchor="w", pady=(8, 0))
        self.btn_prev_ant = ttk.Button(nav, text="‹", width=3,
                                       command=lambda: self._navegar_thumb(-1))
        self.btn_prev_ant.pack(side="left")
        self.lbl_prev_pos = ttk.Label(nav, text="")
        self.lbl_prev_pos.pack(side="left", padx=6)
        self.btn_prev_prox = ttk.Button(nav, text="›", width=3,
                                        command=lambda: self._navegar_thumb(1))
        self.btn_prev_prox.pack(side="left")

        ttk.Button(prev, text="Selecionar todo o post",
                   command=self._selecionar_post).pack(anchor="w", pady=(10, 0))
        ttk.Button(prev, text="Marcar este arquivo",
                   command=self._marcar_atual).pack(anchor="w", pady=(4, 0))


    # ------------------------------------------------------------- log
    def logmsg(self, txt):
        self.log_queue.put(txt)

    def _drain_log(self):
        while not self.log_queue.empty():
            txt = self.log_queue.get()
            self.log.configure(state="normal")
            self.log.insert("end", txt + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.after(150, self._drain_log)

    # ----------------------------------------------------------- login
    def _auto_connect(self):
        if self.cfg.get("api_id") and self.cfg.get("api_hash"):
            self.status_var.set("conectando...")
            self.runner.submit(self._connect(), self._after_connect, self)
        else:
            self._boas_vindas()

    def _boas_vindas(self):
        """Primeira execucao: explica em uma tela o que vai acontecer."""
        win = tk.Toplevel(self)
        win.title("Bem-vindo")
        win.geometry("540x380")
        win.transient(self)
        frm = ttk.Frame(win, padding=24)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Telegram Downloader",
                  font=("Helvetica", 20, "bold")).pack(anchor="w")
        ttk.Label(frm, text="Baixe arquivos de grupos e canais de forma organizada",
                  foreground="#666").pack(anchor="w", pady=(2, 18))

        passos = (
            "Como funciona:\n\n"
            "1.  Você conecta sua conta do Telegram (uma única vez)\n"
            "2.  Escolhe um grupo ou canal da sua lista\n"
            "3.  O app analisa e mostra quantos arquivos e quantos GB existem,\n"
            "     separados por categoria\n"
            "4.  Você seleciona o que quer — categorias inteiras ou arquivos\n"
            "     avulsos, vendo a foto de cada modelo antes de decidir\n"
            "5.  Baixa, com as pastas já organizadas\n\n"
            "Para conectar, você precisa de duas credenciais gratuitas do\n"
            "Telegram. A próxima tela explica como obtê-las em 2 minutos."
        )
        ttk.Label(frm, text=passos, justify="left", foreground="#333").pack(anchor="w")

        def seguir():
            win.destroy()
            self._open_login()

        ttk.Button(frm, text="Começar", command=seguir).pack(anchor="w", pady=(20, 0))
        win.protocol("WM_DELETE_WINDOW", seguir)

    async def _connect(self):
        self.client = TelegramClient(SESSION, int(self.cfg["api_id"]),
                                     self.cfg["api_hash"])
        await self.client.connect()
        return await self.client.is_user_authorized()

    def _after_connect(self, authorized, err):
        if err:
            self.status_var.set("erro de conexão")
            self.logmsg(f"Erro ao conectar: {err}")
            return
        if authorized:
            self.status_var.set("conectado")
            self.btn_login.configure(text="Reconectar")
            self.logmsg("Conectado. Vá para a aba '1. Grupos' e clique em "
                        "'Carregar grupos'.")
        else:
            self.status_var.set("não autenticado")
            self._open_phone_dialog()

    def _open_login(self):
        win = tk.Toplevel(self)
        win.title("Credenciais da API")
        win.geometry("540x470")
        frm = ttk.Frame(win, padding=16)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Credenciais do Telegram",
                  font=("Helvetica", 14, "bold")).pack(anchor="w")

        api_id = tk.StringVar(value=str(self.cfg.get("api_id", "")))
        api_hash = tk.StringVar(value=self.cfg.get("api_hash", ""))

        campos = ttk.Frame(frm)
        campos.pack(fill="x", pady=(12, 6))
        for label, var in (("api_id", api_id), ("api_hash", api_hash)):
            row = ttk.Frame(campos)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=label, width=10).pack(side="left")
            ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)

        # --- ajuda para quem ainda não tem credenciais
        ajuda = ttk.LabelFrame(frm, text="Ainda não tenho essas credenciais",
                               padding=12)
        ajuda.pack(fill="both", expand=True, pady=(14, 0))

        passos = (
            "São gratuitas, levam 2 minutos e ficam vinculadas à sua conta.\n\n"
            "1. Clique no botão abaixo para abrir my.telegram.org\n"
            "2. Informe seu telefone (+55...); o código chega no app do Telegram\n"
            "3. Entre em 'API development tools'\n"
            "4. Preencha App title e Short name (qualquer nome serve) e\n"
            "     escolha a plataforma Desktop; URL e descrição podem ficar vazias\n"
            "5. Clique em 'Create application'\n"
            "6. Copie App api_id e App api_hash para os campos acima"
        )
        ttk.Label(ajuda, text=passos, justify="left", wraplength=460,
                  foreground="#444").pack(anchor="w")

        linha_botoes = ttk.Frame(ajuda)
        linha_botoes.pack(anchor="w", pady=(10, 0))
        ttk.Button(linha_botoes, text="Abrir my.telegram.org",
                   command=lambda: webbrowser.open(
                       "https://my.telegram.org/auth?to=apps")).pack(side="left")
        ttk.Label(linha_botoes, text="não compartilhe essas credenciais",
                  foreground="#a33").pack(side="left", padx=10)

        def salvar():
            bruto = api_id.get().strip()
            h = api_hash.get().strip()
            if not bruto or not h:
                messagebox.showerror(
                    "Erro",
                    "Preencha api_id e api_hash. Use o botão acima se ainda "
                    "não os tiver.", parent=win)
                return
            try:
                self.cfg["api_id"] = int(bruto)
            except ValueError:
                messagebox.showerror("Erro", "api_id deve ser numérico "
                                             "(apenas dígitos).", parent=win)
                return
            if len(h) != 32 and not messagebox.askyesno(
                "Confirmar",
                f"O api_hash costuma ter 32 caracteres; o informado tem "
                f"{len(h)}. Continuar mesmo assim?", parent=win):
                return
            self.cfg["api_hash"] = h
            save_config(self.cfg)
            win.destroy()
            self.status_var.set("conectando...")
            self.runner.submit(self._connect(), self._after_connect, self)

        ttk.Button(frm, text="Salvar e conectar", command=salvar).pack(pady=12)

    def _open_phone_dialog(self):
        win = tk.Toplevel(self)
        win.title("Login")
        win.geometry("400x260")
        frm = ttk.Frame(win, padding=16)
        frm.pack(fill="both", expand=True)

        phone = tk.StringVar(value=self.cfg.get("phone", ""))
        code = tk.StringVar()
        pwd = tk.StringVar()

        ttk.Label(frm, text="Telefone (ex: +5571999999999)").pack(anchor="w")
        ttk.Entry(frm, textvariable=phone).pack(fill="x", pady=(0, 8))

        self._code_hash = None
        btn_entrar_ref = {}

        def enviar_codigo():
            tel = phone.get().strip()
            if not tel.startswith("+"):
                messagebox.showerror("Erro", "Use o formato internacional: +55...",
                                     parent=win)
                return
            self.cfg["phone"] = tel
            save_config(self.cfg)

            def done(sent, e):
                if e:
                    self._code_hash = None
                    self.logmsg(f"Erro ao enviar código: {e}")
                    messagebox.showerror("Erro", str(e), parent=win)
                    return
                self._code_hash = sent.phone_code_hash
                self.logmsg(f"Código enviado (hash {self._code_hash[:8]}...).")
                if btn_entrar_ref:
                    btn_entrar_ref["b"].configure(state="normal")

            self.runner.submit(self.client.send_code_request(tel), done, self)

        ttk.Button(frm, text="Enviar código", command=enviar_codigo).pack(anchor="w")

        ttk.Label(frm, text="Código recebido").pack(anchor="w", pady=(12, 0))
        ttk.Entry(frm, textvariable=code).pack(fill="x")
        ttk.Label(frm, text="Senha 2FA (se houver)").pack(anchor="w", pady=(8, 0))
        ttk.Entry(frm, textvariable=pwd, show="•").pack(fill="x")

        async def _signin():
            try:
                await self.client.sign_in(
                    phone=self.cfg["phone"],
                    code=code.get().strip(),
                    phone_code_hash=self._code_hash,
                )
            except SessionPasswordNeededError:
                await self.client.sign_in(password=pwd.get())
            return True

        def entrar():
            if not self._code_hash:
                messagebox.showwarning(
                    "Atenção",
                    "Clique em 'Enviar código' antes de entrar.", parent=win)
                return

            def done(_r, e):
                if e:
                    self.logmsg(f"Falha no login: {type(e).__name__}: {e}")
                    messagebox.showerror("Erro", str(e), parent=win)
                else:
                    self.status_var.set("conectado")
                    self.logmsg("Login concluído.")
                    win.destroy()

            self.runner.submit(_signin(), done, self)

        b = ttk.Button(frm, text="Entrar", command=entrar, state="disabled")
        b.pack(pady=14)
        btn_entrar_ref["b"] = b

    # --------------------------------------------------------- diálogos
    def load_dialogs(self):
        if not self.client:
            messagebox.showwarning("Atenção", "Conecte-se primeiro.")
            return
        self.logmsg("Carregando lista de grupos...")

        async def _load():
            out = []
            async for d in self.client.iter_dialogs():
                if d.is_group or d.is_channel:
                    kind = "grupo" if d.is_group else "canal"
                    out.append((d.name or "(sem nome)", kind, d.id, d.entity))
            return out

        def done(res, err):
            if err:
                self.logmsg(f"Erro: {err}")
                return
            self.dialogs = res
            self._render_dialogs()
            self.logmsg(f"{len(res)} grupos/canais carregados.")

        self.runner.submit(_load(), done, self)

    def _render_dialogs(self):
        termo = self.filter_var.get().lower().strip()
        self.tree_dialogs.delete(*self.tree_dialogs.get_children())
        for i, (nome, kind, did, _ent) in enumerate(self.dialogs):
            if termo and termo not in nome.lower():
                continue
            self.tree_dialogs.insert("", "end", iid=str(i), values=(nome, kind, did))

    def use_manual(self):
        alvo = self.manual_var.get().strip()
        if not alvo:
            return
        alvo = alvo.rstrip("/").split("/")[-1].lstrip("@")

        def done(ent, err):
            if err:
                self.logmsg(f"Não consegui resolver '{alvo}': {err}")
                return
            self.current_entity = ent
            nome = getattr(ent, "title", None) or getattr(ent, "username", alvo)
            self.grupo_label.configure(text=nome)
            self.nb.select(1)
            self.logmsg(f"Grupo definido: {nome}")

        self.runner.submit(self.client.get_entity(alvo), done, self)

    def analyze_selected(self):
        sel = self.tree_dialogs.selection()
        if not sel:
            messagebox.showinfo("Selecione", "Escolha um grupo na lista.")
            return
        nome, _kind, _did, ent = self.dialogs[int(sel[0])]
        self.current_entity = ent
        self.grupo_label.configure(text=nome)
        self.nb.select(1)
        self.start_scan()

    # ----------------------------------------------------------- scan
    def start_scan(self):
        if self.current_entity is None:
            messagebox.showinfo("Selecione", "Escolha um grupo primeiro.")
            return
        try:
            limite = int(self.limit_var.get() or 0)
        except ValueError:
            limite = 0

        self.btn_scan.configure(state="disabled")
        self.tree_ext.delete(*self.tree_ext.get_children())
        self.scan_index = {}
        self.logmsg("Analisando (só metadados, nada é baixado)...")

        async def _scan():
            index = defaultdict(list)
            vistos = set()
            n = 0
            async for msg in self.client.iter_messages(
                self.current_entity, limit=limite or None
            ):
                if not msg.file:
                    continue
                nome = msg.file.name or ""
                ext = (msg.file.ext or "").lower() or "(sem extensão)"
                tam = msg.file.size or 0
                chave = (nome, tam)
                dup = chave in vistos
                vistos.add(chave)
                index[ext].append({
                    "id": msg.id,
                    "size": tam,
                    "name": nome,
                    "dup": dup,
                    "grupo": msg.grouped_id,          # amarra o album/post
                    "foto": bool(msg.photo),
                    "legenda": (msg.message or "").strip()[:120],
                    "data": msg.date,
                })
                n += 1
                if n % 250 == 0:
                    self.logmsg(f"  ...{n} arquivos indexados")
            return dict(index)

        def done(res, err):
            self.btn_scan.configure(state="normal")
            if err:
                self.logmsg(f"Erro na análise: {err}")
                return
            self.scan_index = res
            self._render_scan()

        self.runner.submit(_scan(), done, self)

    def _render_scan(self):
        """Monta a arvore: categoria -> extensao -> arquivos (sob demanda)."""
        self.tree_ext.delete(*self.tree_ext.get_children())
        self._por_id = {}
        self._por_cat = defaultdict(list)

        self._por_grupo = defaultdict(list)
        for ext, itens in self.scan_index.items():
            self._por_cat[categoria_de(ext)].append(ext)
            for it in itens:
                self._por_id[it["id"]] = it
                if it.get("grupo"):
                    self._por_grupo[it["grupo"]].append(it)

        # ordena categorias por tamanho total decrescente
        def tam_cat(cat):
            return sum(i["size"] for e in self._por_cat[cat]
                       for i in self.scan_index[e])

        for cat in sorted(self._por_cat, key=tam_cat, reverse=True):
            exts = sorted(self._por_cat[cat],
                          key=lambda e: -sum(i["size"] for i in self.scan_index[e]))
            qtd_cat = sum(len(self.scan_index[e]) for e in exts)
            tot_cat = sum(i["size"] for e in exts for i in self.scan_index[e])
            no_cat = self.tree_ext.insert(
                "", "end", iid=f"cat::{cat}",
                values=(cat, qtd_cat, human(tot_cat), tot_cat), open=False)

            for ext in exts:
                itens = self.scan_index[ext]
                tot = sum(i["size"] for i in itens)
                no_ext = self.tree_ext.insert(
                    no_cat, "end", iid=f"ext::{ext}",
                    values=(f"    {ext}", len(itens), human(tot), tot))
                # placeholder: faz aparecer a setinha; conteudo carrega ao abrir
                self.tree_ext.insert(no_ext, "end",
                                     iid=f"ph::{ext}", values=("carregando...",))

        g_qtd = sum(len(v) for v in self.scan_index.values())
        g_tot = sum(i["size"] for v in self.scan_index.values() for i in v)
        dups = [i for v in self.scan_index.values() for i in v if i["dup"]]
        self.logmsg(
            f"Análise concluída: {g_qtd} arquivos | {human(g_tot)} | "
            f"{len(dups)} prováveis duplicatas ({human(sum(i['size'] for i in dups))})"
        )
        self._update_disk()
        self._update_selection_label()

    def _expandir_no(self, _evt=None):
        """Carrega os arquivos de uma extensao na primeira vez que ela abre."""
        iid = self.tree_ext.focus()
        if not iid.startswith("ext::"):
            return
        filhos = self.tree_ext.get_children(iid)
        if not (len(filhos) == 1 and filhos[0].startswith("ph::")):
            return  # ja carregado

        ext = iid[5:]
        self.tree_ext.delete(filhos[0])
        itens = sorted(self.scan_index.get(ext, []),
                       key=lambda i: i["name"].lower())
        limite = 1500
        com_foto = {g for g, v in self._por_grupo.items()
                    if any(i.get("foto") for i in v)}
        for it in itens[:limite]:
            marca = "  (dup)" if it["dup"] else ""
            if it.get("grupo") in com_foto and not it.get("foto"):
                marca += "  🖼"
            nome = it["name"] or f"(sem nome) msg {it['id']}"
            self.tree_ext.insert(
                iid, "end", iid=f"file::{it['id']}",
                values=(f"        {nome}{marca}", "", human(it["size"]), it["size"]))
        if len(itens) > limite:
            self.tree_ext.insert(
                iid, "end", iid=f"mais::{ext}",
                values=(f"        (+{len(itens) - limite} arquivos não listados "
                        f"— selecione a extensão inteira)", "", "", 0))

    # ------------------------------------------------- pre-visualizacao
    def _fotos_do_post(self, item):
        """Fotos publicadas no mesmo post que este arquivo."""
        g = item.get("grupo")
        if not g:
            return [item] if item.get("foto") else []
        return [i for i in self._por_grupo.get(g, []) if i.get("foto")]

    def _on_select_preview(self):
        """Atualiza o painel conforme o no selecionado."""
        sel = self.tree_ext.selection()
        alvos = [i for i in sel if i.startswith("file::")]
        if not alvos:
            self._limpar_preview("selecione um arquivo")
            return

        item = self._por_id.get(int(alvos[-1][6:]))
        if not item:
            self._limpar_preview("arquivo não encontrado")
            return

        self._item_prev = item
        self._fotos_prev = self._fotos_do_post(item)
        self._idx_prev = 0

        legenda = item.get("legenda") or ""
        data = item["data"].strftime("%d/%m/%Y") if item.get("data") else ""
        info = f"{item['name'] or '(sem nome)'}\n{human(item['size'])}  ·  {data}"
        if legenda:
            info += f"\n\n{legenda}"
        if not item.get("grupo"):
            info += "\n\n(arquivo avulso, sem post associado)"
        self.prev_info.configure(text=info)

        if not self._fotos_prev:
            self._limpar_preview("sem imagem neste post", manter_info=True)
            return
        self._mostrar_thumb()

    def _limpar_preview(self, texto, manter_info=False):
        self.canvas_prev.delete("all")
        self._msg_prev = self.canvas_prev.create_text(
            150, 150, text=texto, fill="#999", width=260)
        self._thumb_atual = None
        self.lbl_prev_pos.configure(text="")
        if not manter_info:
            self.prev_info.configure(text="")
            self._item_prev = None
            self._fotos_prev = []

    def _navegar_thumb(self, passo):
        if not getattr(self, "_fotos_prev", None):
            return
        self._idx_prev = (self._idx_prev + passo) % len(self._fotos_prev)
        self._mostrar_thumb()

    def _mostrar_thumb(self):
        foto = self._fotos_prev[self._idx_prev]
        self.lbl_prev_pos.configure(
            text=f"{self._idx_prev + 1}/{len(self._fotos_prev)}")

        if not TEM_PIL:
            self._desenhar_aviso("Pillow não instalado —\ninstale para ver imagens:\n"
                                 "pip install pillow")
            return

        cache = THUMB_DIR / f"{foto['id']}.jpg"
        if cache.exists():
            self._pintar(cache)
            return

        self.canvas_prev.delete("all")
        self.canvas_prev.create_text(150, 150, text="carregando imagem...",
                                     fill="#999")

        alvo_id = foto["id"]

        async def _baixar():
            msg = await self.client.get_messages(self.current_entity, ids=alvo_id)
            if msg is None:
                return None
            # thumb=-1 pega a maior miniatura disponivel (poucos KB)
            return await msg.download_media(file=str(cache), thumb=-1)

        def pronto(caminho, err):
            if err or not caminho:
                self._desenhar_aviso("não consegui carregar a miniatura")
                if err:
                    self.logmsg(f"  miniatura {alvo_id}: {err}")
                return
            # so pinta se o usuario ainda estiver na mesma imagem
            if self._fotos_prev and self._fotos_prev[self._idx_prev]["id"] == alvo_id:
                self._pintar(Path(caminho))

        self.runner.submit(_baixar(), pronto, self)

    def _pintar(self, caminho: Path):
        try:
            img = Image.open(caminho)
            img.thumbnail((296, 296))
            self._thumb_atual = ImageTk.PhotoImage(img)   # manter referencia viva
        except Exception as e:  # noqa: BLE001
            self._desenhar_aviso(f"imagem inválida: {e}")
            return
        self.canvas_prev.delete("all")
        self.canvas_prev.create_image(150, 150, image=self._thumb_atual)

    def _desenhar_aviso(self, texto):
        self.canvas_prev.delete("all")
        self.canvas_prev.create_text(150, 150, text=texto, fill="#999", width=260)
        self._thumb_atual = None

    def _selecionar_post(self):
        """Marca na arvore todos os arquivos do mesmo post."""
        item = getattr(self, "_item_prev", None)
        if not item or not item.get("grupo"):
            messagebox.showinfo("Post", "Este arquivo não faz parte de um post "
                                        "com vários itens.")
            return
        irmaos = self._por_grupo.get(item["grupo"], [])
        self._garantir_visivel([i["id"] for i in irmaos])
        self.tree_ext.selection_add(*[f"file::{i['id']}" for i in irmaos])

    def _marcar_atual(self):
        item = getattr(self, "_item_prev", None)
        if item:
            self.tree_ext.selection_add(f"file::{item['id']}")

    def _garantir_visivel(self, ids):
        """Abre as extensoes necessarias para que esses ids existam na arvore."""
        exts = set()
        for ext, itens in self.scan_index.items():
            if any(i["id"] in set(ids) for i in itens):
                exts.add(ext)
        for ext in exts:
            no = f"ext::{ext}"
            if self.tree_ext.exists(no):
                pai = self.tree_ext.parent(no)
                if pai:
                    self.tree_ext.item(pai, open=True)
                self.tree_ext.item(no, open=True)
                self.tree_ext.focus(no)
                self._expandir_no()

    def _expandir_categorias(self):
        """Abre todas as categorias (as extensoes carregam ao serem abertas)."""
        for iid in self.tree_ext.get_children():
            self.tree_ext.item(iid, open=True)

    def _itens_de(self, iid):
        """Expande um no selecionado na lista de arquivos que ele representa."""
        if iid.startswith("cat::"):
            cat = iid[5:]
            return [i for e in self._por_cat.get(cat, [])
                    for i in self.scan_index.get(e, [])]
        if iid.startswith("ext::"):
            return list(self.scan_index.get(iid[5:], []))
        if iid.startswith("file::"):
            it = self._por_id.get(int(iid[6:]))
            return [it] if it else []
        return []  # placeholders e "mais::" nao contam sozinhos

    def _selecao_efetiva(self):
        """Arquivos unicos cobertos pela selecao atual, aplicando dedup."""
        escolhidos = {}
        for iid in self.tree_ext.selection():
            for it in self._itens_de(iid):
                if self.dedup_var.get() and it["dup"]:
                    continue
                escolhidos[it["id"]] = it
        return list(escolhidos.values())

    def _update_selection_label(self):
        itens = self._selecao_efetiva()
        if not itens:
            self.sel_label.configure(text="Nada selecionado")
            return
        total = sum(i["size"] for i in itens)
        cats = {categoria_de(os.path.splitext(i["name"])[1].lower())
                for i in itens}
        resumo = ", ".join(sorted(cats)[:3])
        if len(cats) > 3:
            resumo += f" +{len(cats) - 3}"
        self.sel_label.configure(
            text=f"Selecionado: {len(itens)} arquivos / {human(total)}  [{resumo}]")


    def _update_disk(self):
        try:
            livre = shutil.disk_usage(Path(self.dest_var.get()).anchor or "/").free
            self.disk_label.configure(text=f"livre: {human(livre)}")
        except Exception:  # noqa: BLE001
            pass

    def _preview_org(self):
        """Mostra um exemplo do caminho resultante."""
        modo = self.org_var.get()
        sub = subpasta(modo, ".stl")
        exemplo = os.path.join(sub, "peca.stl") if sub else "peca.stl"
        self.org_label.configure(text=f"ex.: {exemplo}")

    def reorganizar(self):
        """Move arquivos ja existentes na pasta destino para as subpastas."""
        modo = self.org_var.get()
        dest = Path(self.dest_var.get()).expanduser()
        if not dest.exists():
            messagebox.showerror("Erro", "A pasta destino não existe.")
            return
        if modo == "Pasta única":
            messagebox.showinfo(
                "Nada a fazer",
                "Escolha um modo de organização diferente de 'Pasta única'.")
            return

        soltos = [f for f in dest.iterdir()
                  if f.is_file() and not f.name.startswith(".")]
        if not soltos:
            messagebox.showinfo("Nada a fazer",
                                "Não há arquivos soltos na raiz do destino.")
            return
        if not messagebox.askyesno(
            "Confirmar",
            f"Mover {len(soltos)} arquivos de\n{dest}\n"
            f"para subpastas no modo '{modo}'?"):
            return

        movidos, erros = 0, 0
        for f in soltos:
            try:
                data = None
                if modo.startswith("Ano-mês"):
                    from datetime import datetime
                    data = datetime.fromtimestamp(f.stat().st_mtime)
                sub = subpasta(modo, f.suffix, data)
                alvo_dir = dest / sub
                alvo_dir.mkdir(parents=True, exist_ok=True)
                destino = alvo_dir / f.name
                n = 1
                while destino.exists():
                    destino = alvo_dir / f"{f.stem}_{n}{f.suffix}"
                    n += 1
                shutil.move(str(f), str(destino))
                movidos += 1
            except Exception as e:  # noqa: BLE001
                self.logmsg(f"  erro em {f.name}: {e}")
                erros += 1
        self.logmsg(f"Reorganização concluída: {movidos} movidos, {erros} erros.")

    def choose_dest(self):
        d = filedialog.askdirectory(initialdir=self.dest_var.get())
        if d:
            self.dest_var.set(d)
            self._update_disk()

    # -------------------------------------------------------- download
    def start_download(self):
        if not self.tree_ext.selection():
            messagebox.showinfo(
                "Selecione",
                "Marque ao menos uma categoria, tipo ou arquivo na lista.")
            return

        alvo = self._selecao_efetiva()
        if not alvo:
            messagebox.showinfo("Selecione", "A seleção não cobre nenhum arquivo.")
            return

        total_bytes = sum(i["size"] for i in alvo)
        dest = Path(self.dest_var.get()).expanduser()
        dest.mkdir(parents=True, exist_ok=True)

        if not messagebox.askyesno(
            "Confirmar",
            f"Baixar {len(alvo)} arquivos ({human(total_bytes)}) para:\n{dest}?",
        ):
            return

        state_file = dest / f".baixados_{getattr(self.current_entity, 'id', 'x')}.json"
        ja = set()
        if self.resume_var.get() and state_file.exists():
            try:
                ja = set(json.loads(state_file.read_text()))
            except Exception:  # noqa: BLE001
                ja = set()
        alvo = [i for i in alvo if i["id"] not in ja]

        modo_org = self.org_var.get()
        self.cancel_flag.clear()
        self.btn_download.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.progress.configure(maximum=max(len(alvo), 1), value=0)

        async def _download():
            baixados = set(ja)
            feitos = 0
            pastas_criadas = set()
            ids = [i["id"] for i in alvo]

            for bloco in range(0, len(ids), 100):
                if self.cancel_flag.is_set():
                    break
                msgs = await self.client.get_messages(
                    self.current_entity, ids=ids[bloco:bloco + 100]
                )
                for msg in msgs:
                    if self.cancel_flag.is_set():
                        break
                    if msg is None or not msg.file:
                        continue
                    ext = (msg.file.ext or "").lower()
                    sub = subpasta(modo_org, ext, msg.date)
                    pasta = dest / sub if sub else dest
                    if sub and sub not in pastas_criadas:
                        pasta.mkdir(parents=True, exist_ok=True)
                        pastas_criadas.add(sub)

                    while True:
                        try:
                            caminho = await msg.download_media(file=str(pasta))
                            break
                        except FloodWaitError as e:
                            self.logmsg(f"  flood wait: aguardando {e.seconds}s")
                            await asyncio.sleep(e.seconds + 5)
                        except ChatForwardsRestrictedError:
                            self.logmsg("  grupo bloqueia salvamento de conteúdo.")
                            caminho = None
                            break
                        except Exception as e:  # noqa: BLE001
                            self.logmsg(f"  falha na msg {msg.id}: {e}")
                            caminho = None
                            break

                    feitos += 1
                    if caminho:
                        baixados.add(msg.id)
                    self.after(0, self._tick, feitos, len(alvo),
                               Path(caminho).name if caminho else "(pulado)")
                    if feitos % 20 == 0:
                        state_file.write_text(json.dumps(sorted(baixados)))
                    await asyncio.sleep(0.4)  # respiro anti flood

            state_file.write_text(json.dumps(sorted(baixados)))
            return feitos

        def done(res, err):
            self.btn_download.configure(state="normal")
            self.btn_cancel.configure(state="disabled")
            if err:
                self.logmsg(f"Erro no download: {err}")
            else:
                fim = "cancelado" if self.cancel_flag.is_set() else "concluído"
                self.logmsg(f"Download {fim}: {res} arquivos processados.")

        self.logmsg(f"Iniciando download de {len(alvo)} arquivos para {dest} "
                    f"(organização: {modo_org})")
        self.runner.submit(_download(), done, self)

    def _tick(self, feitos, total, nome):
        self.progress.configure(value=feitos)
        self.prog_label.configure(text=f"{feitos}/{total}")
        if feitos % 5 == 0 or feitos == total:
            self.logmsg(f"  [{feitos}/{total}] {nome}")


if __name__ == "__main__":
    App().mainloop()
