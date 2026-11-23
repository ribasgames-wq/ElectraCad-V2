#!/bin/bash
# Cria o instalador ElectraCad.dmg (rode num Mac, dentro da pasta electracad).  NÃO TESTADO num Mac real.
# Resultado: ElectraCad.dmg -> quem receber abre e arrasta o ElectraCad para "Applications".
set -e
cd "$(dirname "$0")"
PY=python3
command -v python3.13 >/dev/null 2>&1 && PY=python3.13   # PyInstaller costuma funcionar melhor com versões um pouco mais antigas
echo "==> 1/3  Preparando (1 a 3 minutos)"
rm -rf .venv-build build dist
$PY -m venv .venv-build
source .venv-build/bin/activate
pip install --quiet -r requirements.txt
if [ ! -f bin/dwg2dxf ]; then
  echo "==> Conversor de DWG (LibreDWG): compilando (5 a 15 minutos, só na primeira vez)"
  if command -v cmake >/dev/null 2>&1 && command -v git >/dev/null 2>&1; then
    rm -rf libredwg lw
    git clone --depth 1 https://github.com/LibreDWG/libredwg.git
    cmake -S libredwg -B lw -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DLIBREDWG_DISABLE_JSON=ON -DDISABLE_WERROR=ON -DENABLE_LTO=OFF
    cmake --build lw --target dwg2dxf dxf2dwg -j4
    mkdir -p bin
    cp "$(find lw -type f -name dwg2dxf | head -1)" bin/ && cp "$(find lw -type f -name dxf2dwg | head -1)" bin/ || rm -rf bin
  else
    echo "AVISO: sem cmake/git (instale com 'brew install cmake'). O DMG sairá sem o conversor de DWG; DXF funciona."
  fi
fi
echo "==> 2/3  Gerando o aplicativo"
iconutil -c icns assets/ElectraCad.iconset -o assets/ElectraCad.icns
EXTRA=""
[ -f bin/dwg2dxf ] && EXTRA="--add-binary bin/dwg2dxf:bin --add-binary bin/dxf2dwg:bin"
pyinstaller --noconfirm --windowed --name ElectraCad --osx-bundle-identifier br.electracad.app --icon assets/ElectraCad.icns --add-data "assets:assets" $EXTRA electracad.py
echo "==> 3/3  Gerando o ElectraCad.dmg"
rm -rf dmg_tmp ElectraCad.dmg
mkdir dmg_tmp
cp -R dist/ElectraCad.app dmg_tmp/
ln -s /Applications dmg_tmp/Applications
hdiutil create -volname ElectraCad -srcfolder dmg_tmp -ov -format UDZO ElectraCad.dmg
rm -rf dmg_tmp
echo
echo "Pronto: $(pwd)/ElectraCad.dmg"
echo "Em OUTRO Mac: abra o .dmg, arraste ElectraCad para Applications. Na primeira vez, clique com o botão direito no"
echo "aplicativo > Abrir > Abrir (o Mac avisa porque o programa não é assinado pela Apple)."
