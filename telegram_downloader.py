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
def _instalar(pacote: str, extra=()) -> bool:
    """Tenta instalar um pacote via pip. Devolve True se deu certo."""
    base = [sys.executable, "-m", "pip", "install", pacote, *extra]
    # em ambiente gerenciado (Homebrew/Debian) o pip recusa sem --user
    tentativas = [base, base + ["--user"]]
    for cmd in tentativas:
        print(f"→ {' '.join(cmd)}")
        if subprocess.call(cmd) == 0:
            importlib.invalidate_caches()
            return True
    return False


def _garantir(modulo: str, pacote: str = None, opcional: bool = False,
              extra=()) -> bool:
    """Importa o módulo; se faltar, instala o pacote correspondente."""
    pacote = pacote or modulo
    if importlib.util.find_spec(modulo) is not None:
        return True

    rotulo = "opcional" if opcional else "obrigatória"
    print(f"Dependência {rotulo} ausente: {pacote}. Instalando...")
    if _instalar(pacote, extra):
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


def _opcional_uma_vez(modulo, pacote, motivo, extra=()):
    """Tenta instalar um opcional; se falhar, registra e não insiste mais."""
    if importlib.util.find_spec(modulo) is not None:
        return
    marcador = os.path.join(os.path.expanduser("~"), ".tg_downloader",
                            f".sem_{pacote}")
    if os.path.exists(marcador):
        return
    if not _garantir(modulo, pacote, opcional=True, extra=extra):
        os.makedirs(os.path.dirname(marcador), exist_ok=True)
        with open(marcador, "w") as f:
            f.write(f"Não foi possível instalar {pacote} neste ambiente.\n"
                    f"{motivo}\nApague este arquivo para tentar de novo.\n")
        print("  (registrado; não tentarei de novo nas próximas aberturas)\n")


def _bootstrap():
    """Verifica dependências. Nada é instalado se já estiver presente."""
    _checar_tkinter()
    _garantir("telethon", "telethon")                       # obrigatória
    _opcional_uma_vez("PIL", "pillow",
                      "Sem ele, a pré-visualização não mostra imagens.")
    # cryptg é o ÚNICO acelerador que o Telethon usa (pycryptodome não serve).
    # Sem ele a descriptografia roda em Python puro, ~900x mais lenta.
    # --only-binary: só instala se houver versão pronta, nunca tenta compilar.
    _opcional_uma_vez("cryptg", "cryptg",
                      "Sem ele, downloads ficam MUITO lentos (Python puro).",
                      extra=("--only-binary", "cryptg"))


_bootstrap()


import asyncio
import json
import queue
import shutil
import threading
import time
import tkinter as tk
import webbrowser
import difflib
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageTk
    TEM_PIL = True
except ImportError:
    TEM_PIL = False

from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    ChatAdminRequiredError,
    ChatForwardsRestrictedError,
    ChatSendMediaForbiddenError,
    ChatWriteForbiddenError,
    FloodWaitError,
    SessionPasswordNeededError,
    SlowModeWaitError,
    UserBannedInChannelError,
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
    "Modelo (nome parecido)",
)


def categoria_de(ext: str) -> str:
    """Devolve a categoria de uma extensão (.stl -> modelos-3d)."""
    return _EXT2CAT.get((ext or "").lower(), "outros")


def subpasta(modo: str, ext: str, data=None, modelo=None) -> str:
    """Caminho relativo onde o arquivo deve ser salvo, conforme o modo."""
    if modo.startswith("Modelo"):
        return nome_de_pasta(modelo) if modelo else "_sem-nome"
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
# Agrupamento por nome parecido
# --------------------------------------------------------------------------
# palavras que nao identificam o modelo: removidas em qualquer posicao
_RUIDO = {
    "v", "ver", "version", "versao", "final", "fixed", "fix", "rev", "copy",
    "copia", "part", "parte", "parts", "pt", "plate", "print", "printable",
    "remix", "remixed", "resized", "scaled", "scale", "new", "novo", "old",
    "updated", "test", "teste", "sample", "preview", "render", "mm", "cm",
    "pla", "petg", "abs", "asa", "tpu", "a1", "a1mini", "mini", "p1s", "p1p",
    "x1", "x1c", "ams", "bambu", "bambulab", "nozzle", "multicolor", "color",
    "cor", "stl", "3mf", "obj", "step", "gcode", "file", "arquivo", "modelo",
    "model", "the", "by", "and", "e", "de", "do", "da", "dos", "das", "for",
    "with", "com", "sem", "no", "na", "of",
    # nomes genericos de camera/app, que nao identificam o modelo
    "img", "image", "imagem", "photo", "foto", "pic", "screenshot", "dsc",
    "pxl", "whatsapp", "telegram", "download", "untitled",
}
# partes de um mesmo modelo: removidas so no fim do nome
_PARTES = {
    "lid", "tampa", "base", "top", "bottom", "body", "corpo", "left", "right",
    "esquerda", "direita", "esq", "dir", "l", "r", "a", "b", "c", "d", "front",
    "back", "frente", "tras", "inner", "outer", "insert", "cap", "half",
    "metade", "side", "lado", "upper", "lower", "main", "principal",
}
_PADROES_RUIDO = re.compile(
    r"^(\d+|v\d+.*|rev\d+|ver\d+|part\d+|parte\d+|pt\d+|plate\d+|"
    r"\d+(x\d+)+|\d+mm|\d+cm|\d+x|x\d+|\d+pc?s?|\d+[a-z])$")


def _sem_acento(txt: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", txt)
                   if not unicodedata.combining(c))


def chave_nome(nome: str) -> str:
    """Reduz um nome de arquivo ao que identifica o modelo.

    'SuporteBancada_v2_part3 (1).stl' -> 'suporte bancada'
    """
    if not nome:
        return ""
    base = os.path.splitext(nome)[0]
    base = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", base)      # camelCase
    base = _sem_acento(base).lower()
    base = re.sub(r"\(\d+\)|\[\d+\]", " ", base)          # (1) [2]
    tokens = re.split(r"[^a-z0-9]+", base)
    tokens = [t for t in tokens
              if t and t not in _RUIDO and not _PADROES_RUIDO.match(t)]
    while len(tokens) > 1 and tokens[-1] in _PARTES:
        tokens.pop()
    chave = " ".join(tokens)
    return chave if len(chave) >= 3 else ""


def nome_de_pasta(nome: str) -> str:
    limpo = re.sub(r'[\\/:*?"<>|]+', " ", nome or "").strip()
    limpo = re.sub(r"\s+", " ", limpo)[:60].strip()
    return limpo or "_sem-nome"


_RESERVADOS_WIN = {"con", "prn", "aux", "nul",
                   *(f"com{i}" for i in range(1, 10)),
                   *(f"lpt{i}" for i in range(1, 10))}


def nome_de_arquivo(nome, msg_id, ext=""):
    """Nome válido em Windows, macOS e Linux; gera um se a mensagem não tiver."""
    nome = (nome or "").strip()
    if not nome:
        nome = f"{msg_id}{ext or ''}"
    nome = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", nome)
    base, extensao = os.path.splitext(nome)
    base = base.rstrip(" .") or str(msg_id)
    if base.lower() in _RESERVADOS_WIN:
        base = f"_{base}"
    if len(base) > 150:                      # margem para caminhos longos
        base = base[:150]
    return base + extensao


def caminho_livre(caminho: Path) -> Path:
    """Se o arquivo já existe, devolve 'nome (1).ext', 'nome (2).ext'..."""
    if not caminho.exists():
        return caminho
    n = 1
    while True:
        alt = caminho.with_name(f"{caminho.stem} ({n}){caminho.suffix}")
        if not alt.exists():
            return alt
        n += 1


def _duracao(seg: float) -> str:
    seg = int(seg)
    if seg < 60:
        return f"{seg}s"
    if seg < 3600:
        return f"{seg // 60}min"
    h, m = divmod(seg // 60, 60)
    return f"{h}h{m:02d}"


def agrupar_por_nome(itens, limiar=0.86):
    """Agrupa itens ({'name', 'ext'?, 'grupo'?, 'legenda'?}) em modelos.

    Criterios, combinados:
      1. mesma chave de nome
      2. chaves muito parecidas (difflib, comparando so vizinhos proximos)
      3. mesmo post do Telegram (grouped_id) - leva fotos sem nome junto
    Devolve (rotulo_por_indice, nome_por_rotulo).
    """
    n = len(itens)
    pai = list(range(n))

    def achar(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i

    def unir(a, b):
        ra, rb = achar(a), achar(b)
        if ra != rb:
            pai[rb] = ra

    chaves = [chave_nome(it.get("name") or "") for it in itens]

    # 1. chave identica
    primeiro = {}
    for i, k in enumerate(chaves):
        if not k:
            continue
        if k in primeiro:
            unir(i, primeiro[k])
        else:
            primeiro[k] = i

    # 2. chaves parecidas: blocos pelas 3 primeiras letras, ordenados, e cada
    #    chave comparada so com os ultimos representantes (vizinhos na ordem)
    blocos = defaultdict(list)
    for k in primeiro:
        blocos[k[:3]].append(k)
    for ks in blocos.values():
        if len(ks) < 2:
            continue
        ks.sort()
        reps = []
        for k in ks:
            for r in reps[-12:]:
                # filtro barato por tamanho antes do calculo completo
                if abs(len(k) - len(r)) > max(len(k), len(r)) * (1 - limiar) + 1:
                    continue
                sm = difflib.SequenceMatcher(None, k, r)
                if sm.quick_ratio() >= limiar and sm.ratio() >= limiar:
                    unir(primeiro[k], primeiro[r])
                    break
            else:
                reps.append(k)

    # 3. mesmo post
    por_post = {}
    for i, it in enumerate(itens):
        g = it.get("grupo")
        if not g:
            continue
        if g in por_post:
            unir(i, por_post[g])
        else:
            por_post[g] = i

    # monta os grupos e escolhe um nome para cada
    membros = defaultdict(list)
    for i in range(n):
        membros[achar(i)].append(i)

    rotulo, nomes = {}, {}
    for cid, idxs in enumerate(membros.values()):
        cont = Counter()
        for i in idxs:
            rotulo[i] = cid
            if chaves[i]:
                ext = itens[i].get("ext") or os.path.splitext(
                    itens[i].get("name") or "")[1]
                cont[chaves[i]] += 3 if categoria_de(ext) == "modelos-3d" else 1
        if cont:
            nome = cont.most_common(1)[0][0].title()
        else:
            leg = next((itens[i].get("legenda") for i in idxs
                        if itens[i].get("legenda")), "")
            nome = leg.splitlines()[0][:50].strip() if leg else ""
        nomes[cid] = nome or "(sem nome)"
    return rotulo, nomes


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
                    try:
                        tk_root.after(0, callback, res, err)
                    except (tk.TclError, RuntimeError):
                        pass                 # janela/aba ja foi fechada
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
# Ícone do app (PNG embutido: barra de tarefas, Dock e janelas)
# --------------------------------------------------------------------------
ICONE_PNG = {
    256: (
        "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"
        "AqNPaMXk/wFM1Imt4v665QAAAABJRU5ErkJggg=="
    ),
    48: (
        "iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAYAAABXAvmHAAAEC0lEQVR42u2aT2gUVxzHv+/tm7eZ"
        "kGS35hBo7SEKBtKlsRQPGoo5lFAECdrN3ntoWasg9CQFTTRHPdiDJOCx1MpumiCBUrTCSk1yCGKi"
        "60IMhkIMbSBNdrMhOzszO78e2lmXUOP+mcxmqL/bzr438/nu+/P7vt8sQ0n0x2K+eCRSAIDw8GQI"
        "XEQtWD2GWehEHUIRvhQHT8AyR0bPdCe3MwIAewVPvniEFcLDkyESYlDXjdNNLQG2uZEh1DFsBimV"
        "MWaag6NnupM2a1GAfeHzG7+d1MHu7AXw1woB9f109pMJm5nZQ2LDwwPxSkTMx0DEwiNTH+QtegIP"
        "hZ+zD0ejx55xMEYkxGBTS4B5Bb6pJcBIiEEwRiw8PBny2q9fOgocXETh1eAiyi1YPV7lt2D18Hol"
        "KSfCMAudHB4P4dSN1rZMnD3erkc+fn/H3Sz2aIluPvzd3+T3OZIoHR2BlgbFX04bvUCOZXlHBWxo"
        "Rt71jcipG+V0c1faujoCdUkFbwW8FfA/FyA284WabXS1ScmJZ4t6gG/vX4uQqgXoBaLltFb8nM6Z"
        "ZUFsaEY+nTP9gFYUr0pB0seYawIyOYOOHthH3QdbDfvalm75u/YH/QD0nfp27Q/6v/2sA42SF9tN"
        "vvhLmV5cQ0BVmCsCVCmQ+iPLvz5+0N/R1myD6OX07Whr1jvamosVkfmVrPxxZolUWd1kYN1XE1bF"
        "VQEfY5mcQQDw/RdHWImIimJ+JSvP3Z5FJmdQQFVYNSaPVzv/7eG+MP606oV8Yfwp1QIPAKJaY5UD"
        "SJUCy2kNp0amlPHoMaOS/udjs2I5rUGVAvZoup7IcroJW8T52KyoBH56cY2pUtTsTGvOxLaI6cU1"
        "dv3+8ze2v37/OZyCd8xK2CC3Zl4qsUdLtNNx8tbMS8XJM4HjXujavQX5y7M/5fbrD1+symv3FqQn"
        "zNyliRTNr2Rl6Xb5TfzJrlS7d82NfvXD4yLwuduze7+s8l/r4tTIlGJbD88JAIBSs7cnBLwXbHDl"
        "kFKJ8LIFHD2wj76LHDbdEGAnOscWcTpnsvbWRlfgAaC9tdEs93zBDYtS1VrZeoYqBQyLUoKABIAd"
        "S+xBVdCDhVXl3aCquwH3YGFVBlXxxp2LgAQLXb7bJQV/XO5UckNAOfAAoJvWRwwAQkO/jgYaxGkn"
        "a5a7PX0ymjmWvPhpmIOIwbKGvAJfNIKWNQQixvsjcZ4c6J3T8nqfFxazKgW0vN6XHOid64/E+b9/"
        "NfjnbX3npZ9PvtPceMdJu+skOACsZ7f6UldOTNjMHADikUihPxbzpa6cmFjf1A5lNHOstNNeAM9o"
        "5tj6pnaoFL5Y2rCj9IvQ5btd4OxLBvQonNXlTaZhUYqABCy6mRzondvOCAB/A/dd+/pn7gbJAAAA"
        "AElFTkSuQmCC"
    ),
    32: (
        "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAC70lEQVR42sVXTUwTQRT+Znd2muWn"
        "NeABYxqiqDEh0XgigRAvHuqlB6AN3rhJ4oWeOVTixRt4MIHECyeTLRDBRIkxejAlHojKYe1BSiSk"
        "IZrYtBQYuz8dT9tAbEt3KeWdZmfnfe97b2a+ySMAENE0ORGN2sNzySAhdEJAhA3T7kEDjSlymoCs"
        "CGHNLD4c2HFiEmcwNJscMW1ore1+clDYEzgDc7AVGdGl8YGFiKbJBACGZpMjrMWfOKvAlYgYh3uR"
        "pfGBBTI8lwwaFrZxDsYouiVC6ERru580O3hru58QQickARFuVumP2kFhTwiIMPVy2veLVsX5Nh91"
        "hWOYdg/1wn7y/k2iyNKxOdMu4dmHTdeV9ETg7o2LRqX5V98y0naWy26wpEbuq9vgDSdQ63w0hIBb"
        "8HOpgOtDWE9Wbq+Xm4rVhZw9NMENqy4yeW4iz02ojILJ5PQEDFugo0XB4K0ukuemEVAVVm3t4LXO"
        "8ppPm39EJscRUJXaBAy7unY4GWQPTfRd6UR/TwcAGNXWx+5dNwAgtVsovtV/MZXRchKeDqHjyA0L"
        "scSGSO0WTlS61G5BjM2vszw3TwwOANTZ21qmMgpuWJhc1tnzB3fIpYCvahUml3V21Kch15AbFlRG"
        "kclxPHr5tWpKQ7OflUyO1x3clQ44gJkcR0zb+M8vpm1ImRw/tvbMhGhtKys/fv29/D39/gd7l/rt"
        "SSyoVwVLfMmwm11+AMCL5E+0+ahoKoE2HxVP3qSIM/YsxbV+9l/tsAOqUspzUwqoSskNsOOT56a0"
        "tpWVPRGYjt52gpY8JFf27Xv6sSoBySwhXUtUTvva1cIwS0hTAbGiMiVW6eqMza+zyxdU7Bct1y+i"
        "4+NczUriZvw1V0hvfDXoY/RcGpOiYXVL+lRop2hZEefhaIapjKJoWRF9KrQjRTRN1uOhxfw+H1UZ"
        "xVkScfDz+3xUj4cWy82p0yH3xleDhMoTBCSsSGhoe26WkBYQK8KyZ/SpULk9/wfJm2kFINGujgAA"
        "AABJRU5ErkJggg=="
    ),
}


# --------------------------------------------------------------------------
# Tema visual
# --------------------------------------------------------------------------
PALETA = {
    "fundo":      "#eef1f5",   # fundo da janela
    "cartao":     "#ffffff",   # superficies
    "borda":      "#dde2e9",
    "texto":      "#1e2530",
    "suave":      "#6b7382",   # texto secundario
    "acento":     "#2f7fd1",
    "acento_esc": "#24659f",
    "acento_luz": "#e8f1fb",
    "ok":         "#2e9e5b",
    "alerta":     "#c0392b",
    "listra":     "#f7f9fb",   # linha alternada
    "log_fundo":  "#1e2530",
    "log_texto":  "#d7dde5",
}


def _familia_fonte():
    """Escolhe a fonte de interface mais adequada ao sistema."""
    import tkinter.font as tkfont
    disponiveis = set(tkfont.families())
    preferidas = {
        "Darwin":  ("SF Pro Text", "Helvetica Neue", "Lucida Grande"),
        "Windows": ("Segoe UI Variable Text", "Segoe UI", "Tahoma"),
    }.get(platform.system(), ("Inter", "Ubuntu", "DejaVu Sans"))
    for nome in preferidas:
        if nome in disponiveis:
            return nome
    return "TkDefaultFont"


def _familia_mono():
    import tkinter.font as tkfont
    disponiveis = set(tkfont.families())
    for nome in ("SF Mono", "JetBrains Mono", "Menlo", "Cascadia Mono",
                 "Consolas", "DejaVu Sans Mono"):
        if nome in disponiveis:
            return nome
    return "TkFixedFont"


def aplicar_tema(root):
    """Configura o estilo ttk inteiro. Devolve o dicionario de fontes."""
    P = PALETA
    fam = _familia_fonte()
    mono = _familia_mono()
    base = 12 if platform.system() == "Darwin" else 10

    F = {
        "corpo":   (fam, base),
        "peq":     (fam, base - 1),
        "forte":   (fam, base, "bold"),
        "h1":      (fam, base + 8, "bold"),
        "h2":      (fam, base + 3, "bold"),
        "h3":      (fam, base + 1, "bold"),
        "mono":    (mono, base - 1),
    }

    st = ttk.Style(root)
    st.theme_use("clam")          # o unico tema realmente customizavel
    root.configure(bg=P["fundo"])

    st.configure(".", background=P["fundo"], foreground=P["texto"],
                 font=F["corpo"], borderwidth=0, focuscolor=P["acento"])

    st.configure("TFrame", background=P["fundo"])
    st.configure("Cartao.TFrame", background=P["cartao"], relief="flat")
    st.configure("Barra.TFrame", background=P["cartao"])

    st.configure("TLabel", background=P["fundo"], foreground=P["texto"])
    st.configure("Cartao.TLabel", background=P["cartao"])
    st.configure("H1.TLabel", font=F["h1"])
    st.configure("H2.TLabel", font=F["h2"])
    st.configure("H3.TLabel", font=F["h3"])
    st.configure("Suave.TLabel", foreground=P["suave"], font=F["peq"])
    st.configure("SuaveCartao.TLabel", background=P["cartao"],
                 foreground=P["suave"], font=F["peq"])

    # --- botoes
    st.configure("TButton", padding=(14, 7), relief="flat",
                 background="#e4e8ee", foreground=P["texto"], font=F["corpo"])
    st.map("TButton",
           background=[("pressed", "#cfd6df"), ("active", "#d8dee6"),
                       ("disabled", "#eef0f3")],
           foreground=[("disabled", "#a8afba")])

    st.configure("Acento.TButton", background=P["acento"], foreground="white",
                 font=F["forte"], padding=(18, 8))
    st.map("Acento.TButton",
           background=[("pressed", P["acento_esc"]), ("active", "#3a8bdd"),
                       ("disabled", "#b9cfe6")],
           foreground=[("disabled", "#eef3f8")])

    st.configure("Perigo.TButton", background="#f3e2e0",
                 foreground=P["alerta"], padding=(14, 7))
    st.map("Perigo.TButton", background=[("active", "#ecd2cf")])

    st.configure("Plano.TButton", background=P["cartao"],
                 foreground=P["acento"], padding=(10, 6))
    st.map("Plano.TButton", background=[("active", P["acento_luz"])])

    # --- campos
    st.configure("TEntry", fieldbackground=P["cartao"], foreground=P["texto"],
                 bordercolor=P["borda"], lightcolor=P["borda"],
                 darkcolor=P["borda"], borderwidth=1, padding=6,
                 insertcolor=P["texto"])
    st.map("TEntry", bordercolor=[("focus", P["acento"])])

    st.configure("TCombobox", fieldbackground=P["cartao"], background=P["cartao"],
                 bordercolor=P["borda"], arrowcolor=P["suave"],
                 borderwidth=1, padding=5)
    st.map("TCombobox",
           fieldbackground=[("readonly", P["cartao"])],
           bordercolor=[("focus", P["acento"])])

    st.configure("TCheckbutton", background=P["fundo"], foreground=P["texto"],
                 indicatorcolor=P["cartao"], indicatormargin=(0, 0, 8, 0),
                 indicatorrelief="flat", bordercolor=P["borda"],
                 lightcolor=P["cartao"], darkcolor=P["cartao"],
                 focuscolor=P["fundo"], padding=(0, 4))
    st.map("TCheckbutton",
           indicatorcolor=[("selected", P["acento"]), ("active", P["acento_luz"])],
           bordercolor=[("selected", P["acento"])],
           background=[("active", P["fundo"])])

    # --- abas
    st.configure("TNotebook", background=P["fundo"], borderwidth=0,
                 tabmargins=(0, 0, 0, 0))
    st.configure("TNotebook.Tab", background="#e2e6ec", foreground=P["suave"],
                 padding=(22, 11), font=F["corpo"], borderwidth=0,
                 bordercolor=P["fundo"], lightcolor="#e2e6ec",
                 darkcolor="#e2e6ec")
    st.map("TNotebook.Tab",
           background=[("selected", P["cartao"]), ("active", "#eaeef4")],
           foreground=[("selected", P["acento"])],
           lightcolor=[("selected", P["cartao"])],
           expand=[("selected", (0, 0, 0, 0))])

    # --- tabelas
    st.configure("Treeview", background=P["cartao"], fieldbackground=P["cartao"],
                 foreground=P["texto"], borderwidth=0, rowheight=28,
                 font=F["corpo"])
    st.map("Treeview",
           background=[("selected", P["acento"])],
           foreground=[("selected", "white")])
    st.configure("Treeview.Heading", background="#e7ebf1", foreground=P["suave"],
                 font=F["peq"], relief="flat", padding=(8, 8))
    st.map("Treeview.Heading", background=[("active", "#dfe4ec")])

    # --- diversos
    st.configure("TProgressbar", background=P["acento"], troughcolor="#dfe4ec",
                 borderwidth=0, thickness=8)
    st.configure("TPanedwindow", background=P["fundo"])
    st.configure("Sash", sashthickness=8, gripcount=0)
    st.configure("TLabelframe", background=P["fundo"], bordercolor=P["borda"],
                 borderwidth=1, relief="solid")
    st.configure("TLabelframe.Label", background=P["fundo"],
                 foreground=P["suave"], font=F["peq"])
    st.configure("TScrollbar", background="#dfe4ec", troughcolor=P["fundo"],
                 bordercolor=P["fundo"], arrowcolor=P["suave"], borderwidth=0)
    st.map("TScrollbar", background=[("active", "#ccd3dd")])

    return F


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
class AbaAnalise(ttk.Frame):
    """Uma aba de análise: dados, árvore, pré-visualização e download de um
    único grupo. Cada aba é independente, então várias podem rodar juntas."""

    def __init__(self, parent, app, entity, nome):
        super().__init__(parent, padding=10)
        self.app = app
        self.nome = nome
        self.current_entity = entity

        self.scan_index = {}       # ext -> lista de dicts {id, size, name}
        self._por_cat = {}         # categoria -> lista de extensoes
        self._por_id = {}          # msg id -> item
        self._por_grupo = {}       # grouped_id -> itens do mesmo post
        self._grupos_nome = {}     # id do modelo -> {nome, itens, busca}
        self._grupo_de_id = {}     # msg id -> id do modelo
        self._thumb_atual = None   # referencia viva da imagem no Tk
        self._item_prev = None
        self._fotos_prev = []
        self._idx_prev = 0
        self._busca_job = None
        self.cancel_flag = threading.Event()
        self.baixando = False
        self.analisando = False

        pasta = Path.home() / "Downloads" / "telegram" / nome_de_pasta(nome)
        self.dest_var = tk.StringVar(self, value=str(pasta))
        self.dedup_var = tk.BooleanVar(self, value=True)
        self.resume_var = tk.BooleanVar(self, value=True)
        self.limit_var = tk.StringVar(self, value="0")
        self.org_var = tk.StringVar(self, value="Categoria")
        self.vis_var = tk.StringVar(self, value="Categoria / tipo")
        self.busca_var = tk.StringVar(self)

        self._montar()
        self.grupo_label.configure(text=nome)
        self._preview_org()

    # recursos compartilhados vem da janela principal
    client = property(lambda self: self.app.client)
    runner = property(lambda self: self.app.runner)
    F = property(lambda self: self.app.F)

    def logmsg(self, txt):
        curto = self.nome if len(self.nome) <= 22 else self.nome[:21] + "…"
        self.app.logmsg(f"[{curto}] {txt}")

    def _titulo(self, prefixo="", sufixo=""):
        """Texto da aba: nome + estado (analisando, baixando, tamanho)."""
        nome = self.nome if len(self.nome) <= 26 else self.nome[:25] + "…"
        try:
            self.app.nb.tab(self, text=f"{prefixo}{nome}{sufixo}  ")
        except tk.TclError:
            pass

    def _titulo_final(self):
        total = sum(i["size"] for v in self.scan_index.values() for i in v)
        self._titulo(sufixo=f"  ·  {human(total)}" if total else "")


    def _montar(self):
        tab = self

        head = ttk.Frame(tab)
        head.pack(side="top", fill="x", pady=(0, 8))
        self.grupo_label = ttk.Label(head, text="Nenhum grupo selecionado",
                                     style="H3.TLabel")
        self.grupo_label.pack(side="left")
        ttk.Label(head, text="Limite de msgs (0 = tudo):").pack(side="left", padx=(20, 4))
        ttk.Entry(head, textvariable=self.limit_var, width=8).pack(side="left")
        self.btn_scan = ttk.Button(head, text="Analisar", style="Acento.TButton",
                                   command=self.start_scan)
        self.btn_scan.pack(side="left", padx=8)

        # ---- controles fixos: empacotados de baixo para cima, ANTES da tabela,
        #      para que encolher a aba nunca os esconda
        act = ttk.Frame(tab)
        act.pack(side="bottom", fill="x", pady=(12, 0))
        self.btn_download = ttk.Button(act, text="Baixar selecionados",
                                       style="Acento.TButton",
                                       command=self.start_download)
        self.btn_download.pack(side="left")
        self.btn_enc = ttk.Button(act, text="Encaminhar...",
                                  command=self.encaminhar_selecionados)
        self.btn_enc.pack(side="left", padx=8)
        self.btn_cancel = ttk.Button(act, text="Cancelar", state="disabled",
                                     style="Perigo.TButton",
                                     command=lambda: self.cancel_flag.set())
        self.btn_cancel.pack(side="left")
        barras = ttk.Frame(act)
        barras.pack(side="left", padx=12, fill="x", expand=True)
        linha = ttk.Frame(barras)
        linha.pack(fill="x")
        self.progress = ttk.Progressbar(linha, mode="determinate", length=380,
                                        maximum=1000)
        self.progress.pack(side="left", fill="x", expand=True)
        self.prog_label = ttk.Label(linha, text="", width=12, anchor="e")
        self.prog_label.pack(side="left", padx=(8, 0))
        self.prog_info = ttk.Label(barras, text="", style="Suave.TLabel")
        self.prog_info.pack(fill="x", pady=(4, 0))

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
        self.org_label = ttk.Label(org, text="", style="Suave.TLabel")
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
        self.sel_label = ttk.Label(sel, text="Nada selecionado", style="H3.TLabel")
        self.sel_label.pack(side="left", padx=16)

        # ---- corpo: arvore a esquerda, pre-visualizacao a direita
        vis = ttk.Frame(tab)
        vis.pack(side="top", fill="x", pady=(0, 8))
        ttk.Label(vis, text="Mostrar lista por:").pack(side="left")
        combo_vis = ttk.Combobox(vis, textvariable=self.vis_var, state="readonly",
                                 width=24, values=("Categoria / tipo",
                                                   "Modelo (nome parecido)"))
        combo_vis.pack(side="left", padx=(6, 18))
        combo_vis.bind("<<ComboboxSelected>>", lambda _e: self._trocar_visao())
        ttk.Label(vis, text="Buscar:").pack(side="left")
        self.ent_busca = ttk.Entry(vis, textvariable=self.busca_var, width=28)
        self.ent_busca.pack(side="left", padx=6)
        self.busca_var.trace_add("write", lambda *_a: self._agendar_busca())
        self.vis_info = ttk.Label(vis, text="", style="Suave.TLabel")
        self.vis_info.pack(side="left", padx=12)

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
        self.tree_ext.tag_configure("cat", font=self.F["forte"],
                                    background=PALETA["acento_luz"])
        self.tree_ext.tag_configure("ext", font=self.F["corpo"])
        self.tree_ext.tag_configure("par", background=PALETA["listra"])
        self.tree_ext.tag_configure("dup", foreground=PALETA["suave"])

        # ---- painel de pre-visualizacao
        prev = ttk.Frame(split, padding=(10, 0, 0, 0))
        split.add(prev, weight=2)
        ttk.Label(prev, text="Pré-visualização", style="H3.TLabel").pack(anchor="w")

        self.canvas_prev = tk.Canvas(prev, width=300, height=300,
                                     bg=PALETA["cartao"], relief="flat",
                                     highlightthickness=1,
                                     highlightbackground=PALETA["borda"])
        self.canvas_prev.pack(pady=(6, 6))
        self._msg_prev = self.canvas_prev.create_text(
            150, 150, text="selecione um arquivo", fill="#999", width=260)

        self.prev_info = ttk.Label(prev, text="", wraplength=300,
                                   justify="left", style="Suave.TLabel")
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

        ttk.Button(prev, text="Selecionar todo o post", style="Acento.TButton",
                   command=self._selecionar_post).pack(anchor="w", pady=(12, 0))
        ttk.Button(prev, text="Marcar este arquivo",
                   command=self._marcar_atual).pack(anchor="w", pady=(6, 0))


    # ------------------------------------------------------------- log
    def start_scan(self):
        if self.current_entity is None:
            messagebox.showinfo("Selecione", "Escolha um grupo primeiro.")
            return
        try:
            limite = int(self.limit_var.get() or 0)
        except ValueError:
            limite = 0

        self.btn_scan.configure(state="disabled")
        self.analisando = True
        self._titulo("⏳ ")
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
            if not self.winfo_exists():
                return                       # aba fechada durante a analise
            self.analisando = False
            self.btn_scan.configure(state="normal")
            if err:
                self._titulo()
                self.logmsg(f"Erro na análise: {err}")
                return
            self.scan_index = res
            self._render_scan()
            self._titulo_final()
            self._agrupar_modelos()

        self.runner.submit(_scan(), done, self)

    def _render_scan(self, log=True):
        """Monta a arvore: categoria -> extensao -> arquivos (sob demanda)."""
        self._posts_com_foto = None
        self.tree_ext.heading("tipo", text="Categoria / tipo / arquivo")
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
                "", "end", iid=f"cat::{cat}", tags=("cat",),
                values=(cat, qtd_cat, human(tot_cat), tot_cat), open=False)

            for ext in exts:
                itens = self.scan_index[ext]
                tot = sum(i["size"] for i in itens)
                no_ext = self.tree_ext.insert(
                    no_cat, "end", iid=f"ext::{ext}", tags=("ext",),
                    values=(f"    {ext}", len(itens), human(tot), tot))
                # placeholder: faz aparecer a setinha; conteudo carrega ao abrir
                self.tree_ext.insert(no_ext, "end",
                                     iid=f"ph::{ext}", values=("carregando...",))

        if not log:
            self._update_selection_label()
            return
        g_qtd = sum(len(v) for v in self.scan_index.values())
        g_tot = sum(i["size"] for v in self.scan_index.values() for i in v)
        dups = [i for v in self.scan_index.values() for i in v if i["dup"]]
        self.logmsg(
            f"Análise concluída: {g_qtd} arquivos | {human(g_tot)} | "
            f"{len(dups)} prováveis duplicatas ({human(sum(i['size'] for i in dups))})"
        )
        self._update_disk()
        self._update_selection_label()

    # ---------------------------------------------- visao por modelo
    def _agrupar_modelos(self):
        """Agrupa por nome parecido numa thread, sem travar a janela."""
        todos = []
        for ext, itens in self.scan_index.items():
            for it in itens:
                it["ext"] = ext
                todos.append(it)
        self.vis_info.configure(text="agrupando por nome...")

        def trabalho():
            rotulo, nomes = agrupar_por_nome(todos)
            grupos = defaultdict(list)
            for i, it in enumerate(todos):
                grupos[rotulo[i]].append(it)
            resultado = {}
            for cid, itens in grupos.items():
                termos = " ".join(_sem_acento(i["name"] or "").lower() for i in itens)
                resultado[cid] = {
                    "nome": nomes[cid],
                    "itens": itens,
                    "tam": sum(i["size"] for i in itens),
                    "busca": _sem_acento(nomes[cid]).lower() + " " + termos,
                }
            try:
                self.after(0, self._modelos_prontos, resultado)
            except (tk.TclError, RuntimeError):
                pass

        threading.Thread(target=trabalho, daemon=True).start()

    def _modelos_prontos(self, resultado):
        self._grupos_nome = resultado
        self._grupo_de_id = {it["id"]: cid for cid, g in resultado.items()
                             for it in g["itens"]}
        multi = sum(1 for g in resultado.values() if len(g["itens"]) > 1)
        self.logmsg(f"Agrupamento por nome: {len(resultado)} modelos "
                    f"({multi} com mais de um arquivo).")
        if self.vis_var.get().startswith("Modelo"):
            self._render_nomes()
        else:
            self.vis_info.configure(text="")

    def _trocar_visao(self):
        if self.vis_var.get().startswith("Modelo"):
            if not self._grupos_nome:
                self.vis_info.configure(
                    text="analise um grupo primeiro" if not self.scan_index
                    else "agrupando por nome...")
                return
            self._render_nomes()
        else:
            self.vis_info.configure(text="")
            if self.scan_index:
                self._render_scan(log=False)

    def _agendar_busca(self):
        """Espera o usuario parar de digitar antes de filtrar."""
        if self._busca_job:
            self.after_cancel(self._busca_job)
        self._busca_job = self.after(250, self._aplicar_busca)

    def _aplicar_busca(self):
        self._busca_job = None
        if not self.vis_var.get().startswith("Modelo"):
            if self.busca_var.get().strip() and self._grupos_nome:
                self.vis_var.set("Modelo (nome parecido)")
            else:
                return
        self._render_nomes()

    def _render_nomes(self):
        """Arvore: modelo -> arquivos (stl, 3mf, fotos...)."""
        t = self.tree_ext
        t.heading("tipo", text="Modelo / arquivo")
        t.delete(*t.get_children())
        termo = _sem_acento(self.busca_var.get().strip()).lower()

        grupos = [(cid, g) for cid, g in self._grupos_nome.items()
                  if not termo or termo in g["busca"]]
        grupos.sort(key=lambda kv: (-(len(kv[1]["itens"]) > 1), -kv[1]["tam"]))
        multi = [(c, g) for c, g in grupos if len(g["itens"]) > 1]
        unicos = [(c, g) for c, g in grupos if len(g["itens"]) == 1]
        self._unicos_visiveis = [c for c, _g in unicos]

        limite = 2000
        for cid, g in multi[:limite]:
            exts = sorted({i["ext"].lstrip(".") or "?" for i in g["itens"]})
            rotulo = f"{g['nome']}    ·  {' · '.join(exts)}"
            no = t.insert("", "end", iid=f"grp::{cid}", tags=("cat",),
                          values=(rotulo, len(g["itens"]), human(g["tam"]), g["tam"]))
            t.insert(no, "end", iid=f"ph::g{cid}", values=("carregando...",))

        if unicos:
            tot = sum(g["tam"] for _c, g in unicos)
            no = t.insert("", "end", iid="unicos::", tags=("cat",),
                          values=(f"Arquivos sem par", len(unicos), human(tot), tot))
            t.insert(no, "end", iid="ph::unicos", values=("carregando...",))

        txt = f"{len(multi)} modelos agrupados · {len(unicos)} arquivos sem par"
        if len(multi) > limite:
            txt += f" · mostrando {limite} — use a busca"
        self.vis_info.configure(text=txt)
        self._update_selection_label()

    def _inserir_arquivo(self, pai, it, n):
        """Linha de arquivo individual na arvore (comum as duas visoes)."""
        com_foto = getattr(self, "_posts_com_foto", None)
        if com_foto is None:
            com_foto = self._posts_com_foto = {
                g for g, v in self._por_grupo.items()
                if any(i.get("foto") for i in v)}
        marca = "  (dup)" if it["dup"] else ""
        if it.get("grupo") in com_foto and not it.get("foto"):
            marca += "  🖼"
        nome = it["name"] or ("(foto)" if it.get("foto")
                              else f"(sem nome) msg {it['id']}")
        tags = []
        if n % 2:
            tags.append("par")
        if it["dup"]:
            tags.append("dup")
        self.tree_ext.insert(
            pai, "end", iid=f"file::{it['id']}", tags=tuple(tags),
            values=(f"        {nome}{marca}", "", human(it["size"]), it["size"]))

    def _carregar_filhos(self, iid):
        """Preenche um no de modelo (ou o de arquivos sem par) sob demanda."""
        t = self.tree_ext
        filhos = t.get_children(iid)
        if not (len(filhos) == 1 and filhos[0].startswith("ph::")):
            return
        t.delete(filhos[0])
        if iid == "unicos::":
            itens = [self._grupos_nome[c]["itens"][0]
                     for c in getattr(self, "_unicos_visiveis", [])]
        else:
            itens = self._grupos_nome.get(int(iid[5:]), {}).get("itens", [])
        ordem = {"modelos-3d": 0, "compactados": 1, "imagens": 2}
        itens = sorted(itens, key=lambda i: (ordem.get(categoria_de(i["ext"]), 3),
                                             (i["name"] or "").lower()))
        for n, it in enumerate(itens[:1500]):
            self._inserir_arquivo(iid, it, n)

    def _expandir_no(self, _evt=None, iid=None):
        """Carrega os arquivos de um no na primeira vez que ele abre."""
        iid = iid or self.tree_ext.focus()
        if iid.startswith("grp::") or iid == "unicos::":
            self._carregar_filhos(iid)
            return
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
        for n, it in enumerate(itens[:limite]):
            marca = "  (dup)" if it["dup"] else ""
            if it.get("grupo") in com_foto and not it.get("foto"):
                marca += "  🖼"
            nome = it["name"] or f"(sem nome) msg {it['id']}"
            tags = []
            if n % 2:
                tags.append("par")
            if it["dup"]:
                tags.append("dup")
            self.tree_ext.insert(
                iid, "end", iid=f"file::{it['id']}", tags=tuple(tags),
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

        # ids de mensagem se repetem entre grupos: o cache inclui o grupo
        gid = getattr(self.current_entity, "id", 0)
        cache = THUMB_DIR / f"{gid}_{foto['id']}.jpg"
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
        existentes = [f"file::{i['id']}" for i in irmaos
                      if self.tree_ext.exists(f"file::{i['id']}")]
        if existentes:
            self.tree_ext.selection_add(*existentes)

    def _marcar_atual(self):
        item = getattr(self, "_item_prev", None)
        if item and self.tree_ext.exists(f"file::{item['id']}"):
            self.tree_ext.selection_add(f"file::{item['id']}")

    def _garantir_visivel(self, ids):
        """Abre os nos necessarios para que esses ids existam na arvore."""
        if self.vis_var.get().startswith("Modelo"):
            for cid in {self._grupo_de_id.get(i) for i in ids} - {None}:
                no = f"grp::{cid}"
                if not self.tree_ext.exists(no):
                    no = "unicos::"
                if self.tree_ext.exists(no):
                    self._carregar_filhos(no)
                    self.tree_ext.item(no, open=True)
            return
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
        """Abre os nos de primeiro nivel (na visao por modelo, ate 300)."""
        modelo = self.vis_var.get().startswith("Modelo")
        for n, iid in enumerate(self.tree_ext.get_children()):
            if modelo:
                if n >= 300:
                    break
                self._carregar_filhos(iid)
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
        if iid.startswith("grp::"):
            return list(self._grupos_nome.get(int(iid[5:]), {}).get("itens", []))
        if iid == "unicos::":
            return [self._grupos_nome[c]["itens"][0]
                    for c in getattr(self, "_unicos_visiveis", [])]
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
        sub = subpasta(modo, ".stl", modelo="Suporte Bancada")
        exemplo = os.path.join(sub, "suporte_bancada_v2.stl") if sub \
            else "suporte_bancada_v2.stl"
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

        # no modo por modelo, agrupa os proprios arquivos locais pelo nome
        modelo_de = {}
        if modo.startswith("Modelo"):
            locais = [{"name": f.name, "ext": f.suffix.lower()} for f in soltos]
            rotulo, nomes = agrupar_por_nome(locais)
            modelo_de = {f: nomes[rotulo[i]] for i, f in enumerate(soltos)}

        movidos, erros = 0, 0
        for f in soltos:
            try:
                data = None
                if modo.startswith("Ano-mês"):
                    from datetime import datetime
                    data = datetime.fromtimestamp(f.stat().st_mtime)
                sub = subpasta(modo, f.suffix, data, modelo_de.get(f))
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

        aviso = ""
        if getattr(self.app, "cripto_lenta", False):
            horas = total_bytes / (0.4 * 1024 * 1024) / 3600
            aviso = (f"\n\n⚠ A criptografia rápida (cryptg) não está instalada.\n"
                     f"Nessa velocidade (~0,4 MB/s) isso levaria cerca de "
                     f"{horas:.0f} h.\nVeja no log como instalar antes de continuar.")
        if not messagebox.askyesno(
            "Confirmar",
            f"Baixar {len(alvo)} arquivos ({human(total_bytes)}) para:\n{dest}?"
            + aviso,
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
        self.baixando = True
        self._titulo("⬇ ")
        self.btn_download.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.progress.configure(maximum=1000, value=0)
        self.prog_info.configure(text="preparando...")

        async def _download():
            baixados = set(ja)
            feitos = 0
            pastas_criadas = set()
            ids = [i["id"] for i in alvo]
            prog = {"total": sum(i["size"] for i in alvo) or 1, "concluido": 0,
                    "inicio": time.monotonic(), "ultimo": 0.0}

            class Cancelado(Exception):
                pass

            for bloco in range(0, len(ids), 100):
                if self.cancel_flag.is_set():
                    break
                msgs = await self.client.get_messages(
                    self.current_entity, ids=ids[bloco:bloco + 100])
                for msg in msgs:
                    if self.cancel_flag.is_set():
                        break
                    if msg is None or not msg.file:
                        continue
                    ext = (msg.file.ext or "").lower()
                    cid = self._grupo_de_id.get(msg.id)
                    modelo = self._grupos_nome[cid]["nome"] if cid is not None else None
                    sub = subpasta(modo_org, ext, msg.date, modelo)
                    pasta = dest / sub if sub else dest
                    if sub not in pastas_criadas:
                        pasta.mkdir(parents=True, exist_ok=True)
                        pastas_criadas.add(sub)

                    tamanho = msg.file.size or 0
                    nome = nome_de_arquivo(msg.file.name, msg.id, ext)
                    final = pasta / nome
                    # ja existe com o mesmo tamanho: baixado antes, pula
                    if final.exists() and final.stat().st_size == tamanho:
                        caminho = str(final)
                        self._agendar(self._status_arquivo, feitos + 1, len(alvo),
                                      nome, 1.0, tamanho, prog, True)
                    else:
                        final = caminho_livre(final)
                        parcial = final.with_name(final.name + ".part")
                        self._agendar(self._status_arquivo, feitos + 1, len(alvo),
                                      nome, 0.0, tamanho, prog, False)

                        def andamento(recebido, total, _n=nome, _t=tamanho,
                                      _f=feitos):
                            if self.cancel_flag.is_set():
                                raise Cancelado()
                            agora = time.monotonic()
                            if agora - prog["ultimo"] < 0.25:     # no max 4x/s
                                return
                            prog["ultimo"] = agora
                            prog["atual"] = recebido
                            self._agendar(self._status_arquivo, _f + 1, len(alvo),
                                          _n, recebido / (total or _t or 1), _t,
                                          prog, False)

                        caminho = None
                        while True:
                            try:
                                await msg.download_media(file=str(parcial),
                                                         progress_callback=andamento)
                                os.replace(parcial, final)
                                caminho = str(final)
                                break
                            except Cancelado:
                                break
                            except FloodWaitError as e:
                                self.logmsg(f"  flood wait: aguardando {e.seconds}s")
                                await asyncio.sleep(e.seconds + 5)
                            except ChatForwardsRestrictedError:
                                self.logmsg("  grupo bloqueia salvamento de conteúdo.")
                                break
                            except Exception as e:  # noqa: BLE001
                                self.logmsg(f"  falha em {nome}: {e}")
                                break
                        if caminho is None:
                            try:
                                parcial.unlink()      # nao deixa arquivo pela metade
                            except OSError:
                                pass
                        if self.cancel_flag.is_set():
                            break

                    prog["concluido"] += tamanho
                    prog["atual"] = 0
                    feitos += 1
                    if caminho:
                        baixados.add(msg.id)
                    if not self._agendar(self._tick, feitos, len(alvo),
                                         Path(caminho).name if caminho else "(pulado)",
                                         prog):
                        break                         # aba fechada
                    if feitos % 20 == 0:
                        state_file.write_text(json.dumps(sorted(baixados)))
                    await asyncio.sleep(0.4)          # respiro anti flood

            state_file.write_text(json.dumps(sorted(baixados)))
            return feitos

        def done(res, err):
            self.baixando = False
            if not self.winfo_exists():
                return
            self._titulo_final()
            self.btn_download.configure(state="normal")
            self.btn_cancel.configure(state="disabled")
            if err:
                self.logmsg(f"Erro no download: {err}")
            else:
                fim = "cancelado" if self.cancel_flag.is_set() else "concluído"
                self.logmsg(f"Download {fim}: {res} arquivos processados.")
                self.prog_info.configure(text=f"Download {fim} — {res} arquivos.")
                if not self.cancel_flag.is_set():
                    self.progress.configure(value=1000)

        self.logmsg(f"Iniciando download de {len(alvo)} arquivos para {dest} "
                    f"(organização: {modo_org})")
        self.runner.submit(_download(), done, self)

    # ----------------------------------------------------- encaminhar
    def encaminhar_selecionados(self):
        """Encaminha os arquivos marcados para outro grupo/canal."""
        itens = self._selecao_efetiva()
        if not itens:
            messagebox.showinfo("Selecione",
                                "Marque ao menos um arquivo, tipo ou modelo.")
            return
        if not self.client:
            messagebox.showwarning("Atenção", "Conecte-se primeiro.")
            return

        total = sum(i["size"] for i in itens)
        win = tk.Toplevel(self)
        win.title("Encaminhar")
        win.configure(bg=PALETA["fundo"])
        win.transient(self.winfo_toplevel())
        frm = ttk.Frame(win, padding=24)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Encaminhar arquivos", style="H2.TLabel").pack(anchor="w")
        ttk.Label(frm, text=f"{len(itens)} arquivos · {human(total)} · de "
                            f"{self.nome}", style="Suave.TLabel").pack(anchor="w",
                                                                      pady=(2, 16))

        ttk.Label(frm, text="Para qual grupo ou canal:").pack(anchor="w")
        destinos = [f"{nome}" for nome, _k, _d, _e in self.app.dialogs]
        escolha = tk.StringVar(self)
        combo = ttk.Combobox(frm, textvariable=escolha, values=destinos,
                             state="readonly", width=46)
        combo.pack(fill="x", pady=(4, 8))
        if not destinos:
            ttk.Label(frm, text="Sua lista de grupos ainda não foi carregada — "
                               "use o campo abaixo.",
                      style="Suave.TLabel").pack(anchor="w")

        ttk.Label(frm, text="ou @username / link:").pack(anchor="w", pady=(6, 0))
        manual = tk.StringVar(self)
        ttk.Entry(frm, textvariable=manual).pack(fill="x", pady=(4, 12))

        sem_origem = tk.BooleanVar(self, value=False)
        silencioso = tk.BooleanVar(self, value=False)
        ttk.Checkbutton(frm, text="Ocultar a origem (sem o \"encaminhado de\")",
                        variable=sem_origem).pack(anchor="w")
        ttk.Checkbutton(frm, text="Enviar sem notificar os membros",
                        variable=silencioso).pack(anchor="w", pady=(4, 0))

        ttk.Label(frm, text="Os arquivos não são baixados: o Telegram copia "
                            "direto entre as conversas.",
                  style="Suave.TLabel", wraplength=420,
                  justify="left").pack(anchor="w", pady=(14, 0))

        def seguir():
            idx = combo.current()
            alvo_manual = manual.get().strip()
            if alvo_manual:
                alvo = alvo_manual.rstrip("/").split("/")[-1].lstrip("@")
                self.runner.submit(self.client.get_entity(alvo),
                                   lambda ent, err: self._confirmar_encaminhar(
                                       win, ent, err, itens, total,
                                       sem_origem.get(), silencioso.get()),
                                   self)
            elif idx >= 0:
                ent = self.app.dialogs[idx][3]
                self._confirmar_encaminhar(win, ent, None, itens, total,
                                           sem_origem.get(), silencioso.get())
            else:
                messagebox.showinfo("Destino",
                                    "Escolha um grupo ou informe um @username.",
                                    parent=win)

        botoes = ttk.Frame(frm)
        botoes.pack(fill="x", pady=(20, 0))
        ttk.Button(botoes, text="Cancelar",
                   command=win.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(botoes, text="Encaminhar", style="Acento.TButton",
                   command=seguir).pack(side="right")

        self.after(20, lambda: self.app._ajustar_janela(win, 500))

    def _confirmar_encaminhar(self, win, ent, err, itens, total, sem_origem,
                              silencioso):
        if err:
            messagebox.showerror("Erro", f"Não consegui encontrar o destino:\n{err}",
                                 parent=win)
            return
        nome_dest = (getattr(ent, "title", None) or getattr(ent, "username", None)
                     or str(getattr(ent, "id", ent)))
        if getattr(ent, "id", None) == getattr(self.current_entity, "id", object()):
            messagebox.showwarning("Destino", "A origem e o destino são o mesmo "
                                              "grupo.", parent=win)
            return
        if not messagebox.askyesno(
                "Confirmar envio",
                f"Encaminhar {len(itens)} arquivos ({human(total)})\n"
                f"de: {self.nome}\npara: {nome_dest}?",
                parent=win):
            return
        win.destroy()
        self._encaminhar(ent, nome_dest, itens, sem_origem, silencioso)

    def _encaminhar(self, destino, nome_dest, itens, sem_origem, silencioso):
        ids = sorted(i["id"] for i in itens)
        self.cancel_flag.clear()
        self.btn_enc.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.progress.configure(maximum=1000, value=0)
        self.logmsg(f"Encaminhando {len(ids)} arquivos para {nome_dest}...")

        async def _envio():
            enviados = 0
            for bloco in range(0, len(ids), 100):
                if self.cancel_flag.is_set():
                    break
                lote = ids[bloco:bloco + 100]
                while True:
                    try:
                        await self.client.forward_messages(
                            destino, lote, from_peer=self.current_entity,
                            drop_author=sem_origem or None,
                            silent=silencioso or None)
                        break
                    except FloodWaitError as e:
                        self.logmsg(f"  flood wait: aguardando {e.seconds}s")
                        await asyncio.sleep(e.seconds + 5)
                    except SlowModeWaitError as e:
                        self.logmsg(f"  modo lento no destino: {e.seconds}s")
                        await asyncio.sleep(e.seconds + 2)
                    except ChatForwardsRestrictedError:
                        raise RuntimeError(
                            "o grupo de origem bloqueia encaminhamento")
                    except (ChatWriteForbiddenError, ChatAdminRequiredError,
                            ChatSendMediaForbiddenError,
                            UserBannedInChannelError) as e:
                        raise RuntimeError(
                            f"sem permissão para enviar no destino ({type(e).__name__})")
                    except ChannelPrivateError:
                        raise RuntimeError("destino privado ou inacessível")
                enviados += len(lote)
                self._agendar(self._tick_envio, enviados, len(ids))
                await asyncio.sleep(1)       # respiro entre lotes
            return enviados

        def done(res, err):
            if not self.winfo_exists():
                return
            self.btn_enc.configure(state="normal")
            self.btn_cancel.configure(state="disabled")
            if err:
                self.logmsg(f"Encaminhamento interrompido: {err}")
                self.prog_info.configure(text=f"Falhou: {err}")
                messagebox.showerror("Não foi possível encaminhar", str(err))
            else:
                fim = "cancelado" if self.cancel_flag.is_set() else "concluído"
                self.logmsg(f"Encaminhamento {fim}: {res} arquivos.")
                self.prog_info.configure(
                    text=f"Encaminhamento {fim} — {res} arquivos para {nome_dest}.")

        self.runner.submit(_envio(), done, self)

    def _tick_envio(self, enviados, total):
        self.progress.configure(value=1000 * enviados / total)
        self.prog_label.configure(text=f"{enviados}/{total}")
        self.prog_info.configure(text=f"encaminhando... {enviados} de {total}")

    def _agendar(self, func, *args):
        """Chama func na thread da interface. False se a aba já foi fechada."""
        try:
            self.after(0, func, *args)
            return True
        except (tk.TclError, RuntimeError):
            return False

    def _tick(self, feitos, total, nome, prog):
        self.prog_label.configure(text=f"{feitos}/{total}")
        self.progress.configure(value=1000 * prog["concluido"] / prog["total"])
        if feitos <= 3 or feitos % 10 == 0 or feitos == total:
            self.logmsg(f"  [{feitos}/{total}] {nome}")

    def _status_arquivo(self, n, total, nome, fracao, tamanho, prog, pulado):
        """Linha de detalhe: arquivo atual, %, velocidade e tempo restante."""
        feito = prog["concluido"] + fracao * tamanho
        self.progress.configure(value=1000 * feito / prog["total"])
        self.prog_label.configure(text=f"{n - 1}/{total}")
        decorrido = max(time.monotonic() - prog["inicio"], 0.001)
        vel = feito / decorrido
        falta = (prog["total"] - feito) / vel if vel > 0 else 0
        curto = nome if len(nome) <= 42 else nome[:40] + "…"
        if pulado:
            txt = f"{curto}  ·  já existia, pulado"
        else:
            txt = (f"{curto}  ·  {fracao * 100:.0f}% de {human(tamanho)}"
                   f"  ·  {human(vel)}/s  ·  faltam {_duracao(falta)}")
        self.prog_info.configure(text=txt)



class App(tk.Tk):
    def __init__(self):
        # Obs. Windows: nao definimos AppUserModelID de proposito. Aberto pelo
        # atalho, o Windows associa a janela a ele e "Fixar na barra de
        # tarefas" fixa o proprio atalho (icone e argumentos corretos).
        super().__init__()
        self._aplicar_icone()
        self.title("Telegram Downloader")
        self.geometry("1180x780")
        self.minsize(880, 620)

        self.runner = AsyncRunner()
        self.client = None
        self.cfg = load_config()

        self.dialogs = []          # lista de (nome, tipo, id, entity)
        self.abas = {}             # id do grupo -> AbaAnalise
        self.log_queue = queue.Queue()
        self.status_var = tk.StringVar(value="Desconectado")
        self.filter_var = tk.StringVar()

        self._build_ui()
        self._drain_log()
        self.cripto_lenta = self._verificar_cripto()
        self.after(300, self._auto_connect)

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        P = PALETA
        self.F = aplicar_tema(self)

        # ---- cabeçalho
        topo = tk.Frame(self, bg=P["cartao"], height=64)
        topo.pack(fill="x")
        topo.pack_propagate(False)
        tk.Frame(self, bg=P["borda"], height=1).pack(fill="x")

        marca = tk.Frame(topo, bg=P["cartao"])
        marca.pack(side="left", padx=18)
        self.logo = tk.Canvas(marca, width=34, height=34, bg=P["cartao"],
                              highlightthickness=0)
        self.logo.pack(side="left", pady=15)
        self._desenhar_logo()
        textos = tk.Frame(marca, bg=P["cartao"])
        textos.pack(side="left", padx=10)
        tk.Label(textos, text="Telegram Downloader", bg=P["cartao"],
                 fg=P["texto"], font=self.F["h3"]).pack(anchor="w")
        tk.Label(textos, text="baixe arquivos de grupos com organização",
                 bg=P["cartao"], fg=P["suave"], font=self.F["peq"]).pack(anchor="w")

        direita = tk.Frame(topo, bg=P["cartao"])
        direita.pack(side="right", padx=18)
        self.btn_login = ttk.Button(direita, text="Conectar",
                                    style="Plano.TButton", command=self._open_login)
        self.btn_login.pack(side="right", pady=16)
        self.pill = tk.Label(direita, textvariable=self.status_var,
                             bg="#f0f2f5", fg=P["suave"], font=self.F["peq"],
                             padx=12, pady=5)
        self.pill.pack(side="right", padx=12, pady=16)
        self.status_var.trace_add("write", lambda *_a: self._pintar_pill())

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

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
        self._criar_imgs_fechar()
        self.nb.bind("<ButtonPress-1>", self._clique_aba, add="+")
        self.nb.bind("<ButtonRelease-1>", lambda e: self._clique_aba(e, soltou=True),
                     add="+")
        self.nb.bind("<Motion>", self._hover_aba, add="+")
        self.nb.bind("<Leave>", lambda _e: self._hover_aba(None), add="+")
        for tecla in ("<Command-w>", "<Control-w>"):
            try:
                self.bind_all(tecla, lambda _e: self._fechar_atual())
            except tk.TclError:
                pass

        # --- log (arraste a divisória acima para aumentar)
        log_frame = ttk.Frame(paned)
        cab = ttk.Frame(log_frame)
        cab.pack(fill="x", pady=(8, 2))
        ttk.Label(cab, text="Atividade", style="H3.TLabel").pack(side="left")
        ttk.Label(cab, text="arraste a divisória acima para ampliar",
                  style="Suave.TLabel").pack(side="left", padx=10)
        ttk.Button(cab, text="Limpar", style="Plano.TButton",
                   command=self._clear_log).pack(side="right")

        caixa = ttk.Frame(log_frame)
        caixa.pack(fill="both", expand=True)
        self.log = tk.Text(caixa, height=8, wrap="word", font=self.F["mono"],
                           bg=PALETA["log_fundo"], fg=PALETA["log_texto"],
                           insertbackground=PALETA["log_texto"],
                           relief="flat", padx=12, pady=10,
                           selectbackground=PALETA["acento"])
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

    def _ajustar_janela(self, win, largura_min=460):
        """Dimensiona o diálogo pelo conteúdo e centraliza sobre o app."""
        if not win.winfo_exists():
            return
        win.update_idletasks()
        w = max(win.winfo_reqwidth(), largura_min)
        h = win.winfo_reqheight() + 10
        x = self.winfo_rootx() + (self.winfo_width() - w) // 2
        y = self.winfo_rooty() + max(40, (self.winfo_height() - h) // 3)
        win.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
        win.minsize(w, h)
        win.lift()
        win.focus_force()

    def _aplicar_icone(self):
        """Ícone da janela, da barra de tarefas (Windows) e do Dock (macOS)."""
        try:
            self._icones = [tk.PhotoImage(master=self, data=ICONE_PNG[t])
                            for t in (256, 48, 32)]
            # True: vale também para os diálogos (Toplevel) abertos depois
            self.iconphoto(True, *self._icones)
        except tk.TclError:
            pass
        # no Windows, o .ico gerado pelo instalador fica mais nítido
        if platform.system() == "Windows":
            for pasta in (Path(__file__).resolve().parent,
                          Path(os.environ.get("LOCALAPPDATA", "")) / "TelegramDownloader"):
                ico = pasta / "icone.ico"
                if ico.exists():
                    try:
                        self.iconbitmap(default=str(ico))
                    except tk.TclError:
                        pass
                    break

    def _verificar_cripto(self):
        """Informa qual criptografia o Telethon vai usar. Devolve True se lenta."""
        try:
            import cryptg  # noqa: F401
            self.logmsg("Criptografia: cryptg (rápida).")
            return False
        except ImportError:
            pass
        try:
            from telethon.crypto import libssl
            if libssl.encrypt_ige and libssl.decrypt_ige:
                self.logmsg("Criptografia: OpenSSL do sistema (rápida).")
                return False
        except Exception:  # noqa: BLE001
            pass
        self.logmsg("⚠ Criptografia em Python puro: downloads ficarão MUITO "
                    "lentos (~0,4 MB/s). Para corrigir, feche o app e rode:")
        self.logmsg(f'   "{sys.executable}" -m pip install cryptg')
        marcador = APP_DIR / ".sem_cryptg"
        if marcador.exists():
            self.logmsg(f"   e apague {marcador} para o app tentar sozinho.")
        return True

    def _desenhar_logo(self):
        """Miniatura do icone desenhada direto no canvas."""
        c, P = self.logo, PALETA
        if getattr(self, "_icones", None):
            c.create_image(17, 17, image=self._icones[2])   # o mesmo do app
            return
        c.create_rectangle(1, 1, 33, 33, fill=P["acento"], outline="")
        c.create_rectangle(15, 8, 20, 19, fill="white", outline="")
        c.create_polygon(11, 17, 24, 17, 17.5, 25, fill="white", outline="")
        c.create_rectangle(9, 27, 26, 29, fill="white", outline="")

    def _pintar_pill(self):
        """Colore a etiqueta de status conforme o estado."""
        txt = self.status_var.get().lower()
        P = PALETA
        if "conectado" in txt:
            fundo, frente = "#e6f4ec", P["ok"]
        elif "erro" in txt or "não" in txt or "nao" in txt:
            fundo, frente = "#fbeae8", P["alerta"]
        elif "conectando" in txt:
            fundo, frente = P["acento_luz"], P["acento"]
        else:
            fundo, frente = "#f0f2f5", P["suave"]
        self.pill.configure(bg=fundo, fg=frente)

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _build_tab_grupos(self):
        tab = ttk.Frame(self.nb, padding=10)
        self.nb.add(tab, text="  Grupos  ")

        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Button(bar, text="Carregar grupos", style="Acento.TButton",
                   command=self.load_dialogs).pack(side="left")
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
        ttk.Label(rodape, text="Cada grupo analisado abre numa aba própria — "
                               "dá para analisar vários e comparar.",
                  style="Suave.TLabel").pack(side="left")
        ttk.Button(rodape, text="Analisar grupo selecionado  →",
                   style="Acento.TButton",
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
        self.tree_dialogs.tag_configure("par", background=PALETA["listra"])


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
        win.configure(bg=PALETA["fundo"])
        self.after(20, lambda: self._ajustar_janela(win, 540))
        win.transient(self)
        frm = ttk.Frame(win, padding=24)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Telegram Downloader",
                  style="H1.TLabel").pack(anchor="w")
        ttk.Label(frm, text="Baixe arquivos de grupos e canais de forma organizada",
                  style="Suave.TLabel").pack(anchor="w", pady=(2, 18))

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

        ttk.Button(frm, text="Começar", style="Acento.TButton",
                   command=seguir).pack(anchor="w", pady=(20, 0))
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
        win.configure(bg=PALETA["fundo"])
        self.after(20, lambda: self._ajustar_janela(win, 560))
        frm = ttk.Frame(win, padding=22)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Credenciais do Telegram",
                  style="H2.TLabel").pack(anchor="w")

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

        ttk.Button(frm, text="Salvar e conectar", style="Acento.TButton",
                   command=salvar).pack(pady=14)

    def _open_phone_dialog(self):
        win = tk.Toplevel(self)
        win.title("Login")
        win.configure(bg=PALETA["fundo"])
        self.after(20, lambda: self._ajustar_janela(win, 460))
        frm = ttk.Frame(win, padding=24)
        frm.pack(fill="both", expand=True)

        phone = tk.StringVar(value=self.cfg.get("phone", ""))
        code = tk.StringVar()
        pwd = tk.StringVar()

        ttk.Label(frm, text="Entrar no Telegram", style="H2.TLabel").pack(anchor="w")
        ttk.Label(frm, text="O código de acesso chega no próprio app do Telegram.",
                  style="Suave.TLabel").pack(anchor="w", pady=(2, 16))

        ttk.Label(frm, text="Telefone (ex: +5571999999999)").pack(anchor="w")
        ttk.Entry(frm, textvariable=phone, width=34).pack(fill="x", pady=(4, 8))

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

        ttk.Button(frm, text="Enviar código", style="Acento.TButton",
                   command=enviar_codigo).pack(anchor="w", pady=(4, 0))

        ttk.Label(frm, text="Código recebido").pack(anchor="w", pady=(18, 0))
        ttk.Entry(frm, textvariable=code).pack(fill="x", pady=(4, 0))
        ttk.Label(frm, text="Senha 2FA (se houver)").pack(anchor="w", pady=(12, 0))
        ttk.Entry(frm, textvariable=pwd, show="•").pack(fill="x", pady=(4, 0))

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

        b = ttk.Button(frm, text="Entrar", style="Acento.TButton",
                       command=entrar, state="disabled")
        b.pack(anchor="e", pady=(20, 0))
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
            self.tree_dialogs.insert("", "end", iid=str(i),
                                     tags=("par",) if i % 2 else (),
                                     values=(nome, kind, did))

    def use_manual(self):
        alvo = self.manual_var.get().strip()
        if not alvo:
            return
        if not self.client:
            messagebox.showwarning("Atenção", "Conecte-se primeiro.")
            return
        alvo = alvo.rstrip("/").split("/")[-1].lstrip("@")

        def done(ent, err):
            if err:
                self.logmsg(f"Não consegui resolver '{alvo}': {err}")
                return
            nome = getattr(ent, "title", None) or getattr(ent, "username", alvo)
            self.abrir_analise(ent, nome)

        self.runner.submit(self.client.get_entity(alvo), done, self)

    def analyze_selected(self):
        sel = self.tree_dialogs.selection()
        if not sel:
            messagebox.showinfo("Selecione", "Escolha um grupo na lista.")
            return
        for iid in sel:                      # vários de uma vez: uma aba cada
            nome, _kind, _did, ent = self.dialogs[int(iid)]
            self.abrir_analise(ent, nome)

    # --------------------------------------------------------- abas
    def abrir_analise(self, entity, nome):
        """Abre (ou traz para frente) a aba de análise deste grupo."""
        chave = getattr(entity, "id", None) or nome
        aba = self.abas.get(chave)
        if aba is not None and aba.winfo_exists():
            self.nb.select(aba)
            return aba
        aba = AbaAnalise(self.nb, self, entity, nome)
        self.nb.add(aba, text=nome, image=self._img_x, compound="right")
        self.abas[chave] = aba
        aba._titulo()
        self.nb.select(aba)
        aba.start_scan()
        return aba

    def fechar_aba(self, idx):
        if idx == 0:
            return                           # a aba de grupos é fixa
        aba = self.nametowidget(self.nb.tabs()[idx])
        if getattr(aba, "baixando", False):
            if not messagebox.askyesno(
                    "Download em andamento",
                    f"'{aba.nome}' ainda está baixando. Cancelar e fechar?"):
                return
        aba.cancel_flag.set()
        self.nb.forget(aba)
        for k, v in list(self.abas.items()):
            if v is aba:
                del self.abas[k]
        aba.destroy()
        self._aba_hover = None

    def _fechar_atual(self):
        try:
            idx = self.nb.index("current")
        except tk.TclError:
            return
        self.fechar_aba(idx)

    def _criar_imgs_fechar(self):
        """Um X desenhado pixel a pixel, normal e em destaque."""
        def x(cor, fundo=None):
            img = tk.PhotoImage(master=self, width=16, height=16)
            if fundo:
                img.put(fundo, to=(1, 1, 15, 15))
            for i in range(4, 12):
                for dx in (0, 1):
                    img.put(cor, (min(i + dx, 11), i))
                    img.put(cor, (max(15 - i - dx, 4), i))
            return img
        self._img_x = x(PALETA["suave"])
        self._img_x_hover = x("#ffffff", PALETA["alerta"])
        self._aba_hover = None

    def _aba_sob(self, x, y):
        """Índice da aba sob o cursor, ou None."""
        try:
            idx = self.nb.index(f"@{x},{y}")
        except (tk.TclError, ValueError):
            return None
        return idx if isinstance(idx, int) else None

    def _no_x(self, x, y, idx):
        """True se (x, y) está sobre o X da aba idx (fim do rótulo)."""
        borda = x
        while borda < self.nb.winfo_width() and self._aba_sob(borda, y) == idx:
            borda += 2
        return x >= borda - 44

    def _clique_aba(self, evt, soltou=False):
        idx = self._aba_sob(evt.x, evt.y)
        if not idx:                          # None ou 0 (Grupos)
            return None
        if self._no_x(evt.x, evt.y, idx):
            if soltou:
                self.fechar_aba(idx)
            return "break"                   # não troca de aba ao clicar no X
        return None

    def _hover_aba(self, evt):
        alvo = None
        if evt is not None:
            idx = self._aba_sob(evt.x, evt.y)
            if idx and self._no_x(evt.x, evt.y, idx):
                alvo = idx
        if alvo == self._aba_hover:
            return
        self._aba_hover = alvo
        for i, t in enumerate(self.nb.tabs()):
            if i:
                self.nb.tab(t, image=self._img_x_hover if i == alvo
                            else self._img_x)


if __name__ == "__main__":
    App().mainloop()
