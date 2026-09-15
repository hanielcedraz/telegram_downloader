#!/bin/bash
# ---------------------------------------------------------------------------
# Instalador do Telegram Downloader para macOS
#
# Cria um aplicativo de verdade (.app), com icone, que abre com duplo clique
# sem precisar de terminal nem de ativar ambiente virtual.
#
# Uso:
#     chmod +x instalar_mac.sh
#     ./instalar_mac.sh
# ---------------------------------------------------------------------------
set -e

NOME="Telegram Downloader"
BASE="$HOME/.tg_downloader"
VENV="$BASE/venv"
APP="/Applications/$NOME.app"
SCRIPT_ORIGEM="$(cd "$(dirname "$0")" && pwd)/telegram_downloader.py"

echo ""
echo "==========================================="
echo "  Instalando $NOME"
echo "==========================================="
echo ""

# --- 1. localizar o script -------------------------------------------------
if [ ! -f "$SCRIPT_ORIGEM" ]; then
    echo "ERRO: telegram_downloader.py nao encontrado ao lado deste instalador."
    echo "Coloque os dois arquivos na mesma pasta e rode de novo."
    exit 1
fi

# --- 2. encontrar um Python com Tk 8.6 -------------------------------------
echo "[1/5] Procurando um Python adequado..."

PY=""
for cand in python3.13 python3.12 python3.11 python3.10 \
            /opt/homebrew/bin/python3 /usr/local/bin/python3 \
            /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        ver=$("$cand" -c "import tkinter; print(tkinter.TkVersion)" 2>/dev/null || echo "0")
        if [ "$(echo "$ver >= 8.6" | bc -l 2>/dev/null)" = "1" ]; then
            PY="$cand"
            echo "      encontrado: $cand (Tk $ver)"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    echo ""
    echo "Nenhum Python com Tcl/Tk 8.6 foi encontrado."
    if command -v brew >/dev/null 2>&1; then
        echo "Instalando via Homebrew (pode levar alguns minutos)..."
        brew install python@3.12 python-tk@3.12
        PY="$(brew --prefix)/bin/python3.12"
    else
        echo "Homebrew nao esta instalado."
        echo "Baixe o Python em https://www.python.org/downloads/macos"
        echo "instale e rode este script de novo."
        exit 1
    fi
fi

# --- 3. ambiente virtual e dependencias ------------------------------------
echo "[2/5] Preparando ambiente virtual..."
mkdir -p "$BASE"
if [ ! -x "$VENV/bin/python" ]; then
    "$PY" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip
echo "[3/5] Instalando bibliotecas (telethon, pillow, pycryptodome)..."
"$VENV/bin/python" -m pip install --quiet telethon pillow pycryptodome || \
    "$VENV/bin/python" -m pip install --quiet telethon pillow

# --- 4. copiar o script -----------------------------------------------------
cp "$SCRIPT_ORIGEM" "$BASE/telegram_downloader.py"

# --- 5. montar o bundle .app ------------------------------------------------
echo "[4/5] Criando o aplicativo..."
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>            <string>$NOME</string>
    <key>CFBundleDisplayName</key>     <string>$NOME</string>
    <key>CFBundleExecutable</key>      <string>launcher</string>
    <key>CFBundleIdentifier</key>      <string>com.local.tgdownloader</string>
    <key>CFBundleVersion</key>         <string>2.0</string>
    <key>CFBundleShortVersionString</key><string>2.0</string>
    <key>CFBundlePackageType</key>     <string>APPL</string>
    <key>CFBundleIconFile</key>        <string>icone</string>
    <key>NSHighResolutionCapable</key> <true/>
    <key>LSMinimumSystemVersion</key>  <string>11.0</string>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/launcher" <<LAUNCHER
#!/bin/bash
exec "$VENV/bin/python" "$BASE/telegram_downloader.py" 2>>"$BASE/erros.log"
LAUNCHER
chmod +x "$APP/Contents/MacOS/launcher"

# --- 6. gerar o icone -------------------------------------------------------
echo "[5/5] Gerando icone..."
ICONSET="$BASE/icone.iconset"
rm -rf "$ICONSET"

GERADOR="$(cd "$(dirname "$0")" && pwd)/gerar_icone.py"
if [ -f "$GERADOR" ]; then
    "$VENV/bin/python" "$GERADOR" png "$ICONSET" || true
fi

if [ -d "$ICONSET" ] && command -v iconutil >/dev/null 2>&1; then
    iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/icone.icns" 2>/dev/null || true
    rm -rf "$ICONSET"
fi

# --- 7. atalho na area de trabalho -----------------------------------------
DESKTOP="$HOME/Desktop"
[ -d "$HOME/Área de Trabalho" ] && DESKTOP="$HOME/Área de Trabalho"
rm -f "$DESKTOP/$NOME"
ln -s "$APP" "$DESKTOP/$NOME"

# limpa a quarentena para nao pedir autorizacao
xattr -cr "$APP" 2>/dev/null || true
touch "$APP"

echo ""
echo "==========================================="
echo "  Pronto!"
echo ""
echo "  Aplicativo:  $APP"
echo "  Atalho:      $DESKTOP/$NOME"
echo ""
echo "  Abra com duplo clique. Na primeira vez o app"
echo "  pede as credenciais e tem um botao que leva"
echo "  direto a pagina onde obte-las."
echo "==========================================="
echo ""

open -R "$APP" 2>/dev/null || true
