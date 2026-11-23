#!/bin/bash
# Instala o ElectraCad como aplicativo no Mac: cria ~/Applications/ElectraCad.app
# Uso (dentro da pasta electracad):   bash instalar_mac.sh
set -e
cd "$(dirname "$0")"

DEST="$HOME/ElectraCad"                 # onde ficam o programa e as peças (Python, PyQt6, ezdxf)
APP="$HOME/Applications/ElectraCad.app" # o ícone que você abre com dois cliques

echo "==> 1/4  Conferindo o Python"
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERRO: o Python 3 não foi encontrado. Instale em python.org/downloads e rode este script de novo."
  exit 1
fi
python3 --version

echo "==> 2/4  Copiando o programa para $DEST"
mkdir -p "$DEST"
cp electracad.py geom.py estilo.py eletrica.py dwgconv.py marca.py folha.py projeto_io.py unifilar.py diagnostico.py "$DEST"/
rm -rf "$DEST/assets"; cp -R assets "$DEST"/assets
[ -d bin ] && { rm -rf "$DEST/bin"; cp -R bin "$DEST"/bin; }

echo "==> 3/4  Instalando as peças (1 a 3 minutos na primeira vez)"
python3 -m venv "$DEST/.venv"
if ! "$DEST/.venv/bin/pip" install --quiet --upgrade PyQt6 ezdxf; then
  echo "ERRO: não foi possível instalar PyQt6/ezdxf. Verifique a internet e rode de novo."
  exit 1
fi

echo "==> Conversor de DWG (LibreDWG)"
if [ -x "$DEST/bin/dwg2dxf" ] || command -v dwg2dxf >/dev/null 2>&1 || [ -x /opt/homebrew/bin/dwg2dxf ]; then
  echo "Já existe."
elif command -v brew >/dev/null 2>&1; then
  brew install libredwg || echo "AVISO: não consegui instalar o LibreDWG. DXF funciona; para DWG instale o ODA File Converter."
else
  echo "AVISO: o Homebrew (brew.sh) não está instalado, então não há conversor de DWG. DXF funciona normalmente."
  echo "       Para DWG: instale o Homebrew e rode este script de novo, ou use o instalador pronto (.dmg)."
fi

echo "==> 4/4  Criando o aplicativo em $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
iconutil -c icns assets/ElectraCad.iconset -o "$APP/Contents/Resources/ElectraCad.icns" 2>/dev/null || true

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>ElectraCad</string>
  <key>CFBundleDisplayName</key><string>ElectraCad</string>
  <key>CFBundleIdentifier</key><string>br.electracad.app</string>
  <key>CFBundleExecutable</key><string>ElectraCad</string>
  <key>CFBundleIconFile</key><string>ElectraCad</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>2.1</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/ElectraCad" <<'LAUNCH'
#!/bin/bash
cd "$HOME/ElectraCad"
exec "$HOME/ElectraCad/.venv/bin/python" electracad.py "$@"
LAUNCH
chmod +x "$APP/Contents/MacOS/ElectraCad"

echo
echo "Pronto! O aplicativo está em: $APP"
echo "Abra a pasta 'Applications' dentro da sua pasta pessoal (Finder > Ir > Pasta pessoal),"
echo "ou digite no Terminal:   open ~/Applications"
echo "Depois arraste o ElectraCad para o Dock para ter sempre à mão."
