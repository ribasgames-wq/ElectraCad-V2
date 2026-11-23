# ElectraCad (macOS)

Editor e visualizador de DXF/DWG 2D, feito com Python, PyQt6 e ezdxf.

## Instalar como aplicativo (recomendado)

Dentro da pasta `electracad`, no Terminal:

```bash
bash instalar_mac.sh
```

Isso copia o programa para `~/ElectraCad` e cria o aplicativo `~/Applications/ElectraCad.app`.
Abra com dois cliques e arraste para o Dock. Para atualizar numa versão futura, rode o comando de novo.

## Rodar pelo Terminal (alternativa)

```bash
cd ~/Downloads/electracad
source .venv/bin/activate
python electracad.py
```

Na primeira vez, crie o ambiente antes: `python3 -m venv .venv`, depois `source .venv/bin/activate` e `pip install PyQt6 ezdxf`.

Para gerar o aplicativo `ElectraCad.app`: `./build_mac.sh`.

## Instalar em outro Mac

**Jeito simples (recomendado):** copie a pasta `electracad` (ou o .zip) para o outro Mac, instale o Python em
python.org/downloads (se ainda não tiver) e rode, dentro da pasta, `bash instalar_mac.sh`. Precisa de internet.

**Arquivo .dmg:** no Mac onde o programa funciona, rode `bash criar_dmg.sh`. Ele gera `ElectraCad.dmg`; no outro Mac
abra o arquivo e arraste o ElectraCad para Applications. Na primeira vez: botão direito no aplicativo > Abrir > Abrir
(o programa não é assinado pela Apple; assinar exige conta de desenvolvedor paga). O `criar_dmg.sh` ainda não foi testado.

## Projeto elétrico

- **Símbolos:** painel "Símbolos elétricos" à esquerda. Clique no símbolo, depois no desenho (vários seguidos); `R` + Enter gira 90°; Esc encerra.
  O tamanho é ajustado pela unidade do desenho; para mudar: Configurar > Tamanho dos símbolos.
- **Menu Elétrica / barra Elétrica:** camadas padrão (ELE-...), eletroduto no teto (contínuo) e no piso (tracejado),
  contar símbolos, inserir legenda (tabela com símbolo, descrição e quantidade), quadro de cargas e PDF (Arquivo > Exportar PDF).
- **Quadro de cargas:** você digita circuitos (tipo, tensão, fases, potência) e o programa sugere seção do cabo e disjuntor
  (NBR 5410, tabela 36, cobre/PVC, método B1) e distribui as fases. É um apoio: não calcula queda de tensão nem agrupamento.
  Salva em CSV (abre no Excel) ou desenha a tabela no desenho.
- **Atenção:** os símbolos são os de uso comum no Brasil, mas NÃO foram conferidos com a NBR 5444 (norma paga). Compare com a sua.
- Tipos de linha (tracejado etc.) e espessuras agora aparecem na tela (Exibir > Mostrar espessuras de linha).
- Comandos novos: `SIM`, `CONTAR`, `LEGENDA`, `QC`, `PDF`, `ELE`, `ET`, `EP`, `UNI`, `CABOS`, `FOLHA`, `LM`, `FOCO`, `GRADE`.

## Se aparecer um erro

O programa não fecha mais sozinho: mostra uma janela com o erro, e tudo fica gravado no arquivo
`ElectraCad_erro.log` na sua pasta pessoal. Se o problema se repetir, mande esse arquivo (ou o texto do erro).

## Se o programa fechar sozinho ao abrir um DWG

1. Veja se ficou algum registro de erro: `cat ~/ElectraCad_erro.log`
2. Rode o diagnóstico (ele lê o arquivo passo a passo e grava onde parou):
   ```bash
   cd ~/Downloads/electracad
   source .venv/bin/activate
   python diagnostico.py ARRASTE_O_ARQUIVO_AQUI.dwg
   ```
   (arraste o arquivo do Finder para a janela do Terminal para colar o caminho)
3. Depois: `cat ~/ElectraCad_diagnostico.txt` e envie o resultado. Se travar de novo, acrescente `--lento` ao comando.

## Desenhar linhas retas

- **ORTO** (botão laranja na barra de baixo, tecla F8) já começa ligado: a linha só vai na horizontal ou na vertical.
- **POLAR** (F10) deixa o ângulo livre, mas "gruda" a cada 15°. Ligar um desliga o outro.
- **Distância exata:** com a linha em andamento, aponte o mouse na direção desejada, digite a medida (ex.: `5`) e tecle Enter.
- **Coordenadas:** `x,y` absoluta, `@dx,dy` relativa ao último ponto, `10<45` distância e ângulo.
  Para decimais use ponto (`1.5`). A vírgula separa x de y.

## Snap (atrair para pontos dos objetos, F3)

Extremidade (quadrado), ponto médio (triângulo), centro (círculo), quadrante (losango),
interseção (X) e perpendicular (canto em L). O nome aparece ao lado do ponto.

## Ferramentas (barras no alto, ou digite o comando)

| Comando | Ação |
|---|---|
| L / PL / REC | Linha / polilinha (C fecha) / retângulo |
| C / A | Círculo / arco por 3 pontos |
| T | Texto |
| DLI / DAL | Cota linear / cota alinhada |
| DI | Medir distância entre dois pontos |
| M / CO | Mover / copiar (vários destinos até Enter) |
| RO / SC | Girar (clique ou graus) / escalar (fator) |
| MI | Espelhar (mantém o original) |
| O | Deslocar (digite a distância, clique o objeto, clique o lado) |
| TR / EX | Aparar / estender linhas |
| F | Fechar o canto entre duas linhas |
| X | Explodir polilinha ou bloco |
| E ou Backspace | Apagar |
| U ou ⌘Z | Desfazer (vários níveis) |
| ZE / ZW | Zoom total / zoom por janela |
| LA | Criar ou trocar de camada |

**Enter ou Espaço** sem comando repete o último. **Esc** cancela.

## Mouse e trackpad

- Dois dedos ou roda: zoom no cursor.
- **Option + arrastar** (ou botão do meio): mover a tela.
- Clique seleciona; Shift soma. Arrastar da esquerda para a direita seleciona só o que estiver inteiro dentro; da direita para a esquerda, tudo que a janela tocar.
- Arraste um arquivo DXF/DWG para a janela para abrir.

## DWG

O ElectraCad 2.0 abre DWG com o **LibreDWG** (software livre, GPLv3), que vai dentro do instalador: não precisa do ODA.
Limites: lê quase todos os DWG, mas objetos muito novos podem ser ignorados; ao **gravar** DWG usa o formato R2000.
Para salvar DWG moderno com fidelidade total, o ODA File Converter continua funcionando como opção (Configurar > ODA).
Se um DWG não abrir direito, salve-o como DXF no AutoCAD/ZWCAD e abra o DXF.

## Instalar no Mac (passo a passo)

1. Instale o Python em python.org/downloads (se ainda não tiver).
2. Abra o Terminal, digite `cd ` (com espaço), arraste a pasta `electracad` para a janela e tecle Enter.
3. Digite `bash instalar_mac.sh` e tecle Enter. O aplicativo fica em `~/Applications/ElectraCad.app` (arraste para o Dock).
4. Para abrir DWG, o script tenta instalar o conversor LibreDWG pelo Homebrew (brew.sh). Sem Homebrew, só DXF abre.

`bash criar_dmg.sh` gera um `ElectraCad.dmg` para levar a outro Mac (sem o conversor de DWG embutido).

## Novidades da versão 2.1

- **Mais área de trabalho:** uma única barra fina (Desenhar, Editar e Elétrica viraram menus suspensos), painéis Camadas e Símbolos em abas,
  janela abre maximizada, **Tela limpa** (Ctrl+Shift+F) esconde barras e painéis, **Grade** (F7).
- **Botão direito** do mouse = Enter (ou repete o último comando), como no AutoCAD.
- **Abrir recente** no menu Arquivo.
- **Importar/Exportar projeto (JSON):** liga o ElectraCad desktop ao app de IA (Base44). Veja `FORMATO_PROJETO.md` e `exemplo_projeto.json`.
- **Folha com carimbo** (Elétrica > Inserir folha com carimbo): A4 a A0, escala 1:N, campos do projeto.
- **Lista de materiais (CSV)** a partir dos símbolos do desenho.
- **Diagrama unifilar automático** (Elétrica > Diagrama unifilar): desenha barramento, disjuntores, seções e fases a partir do quadro de cargas.
  O disjuntor geral, o DR e o DPS ficam por conta do projetista (o desenho avisa).
- **Lista de cabos (CSV):** condutores, seção, disjuntor e corrente por circuito.
- Ainda **não** tem: referência cruzada entre folhas, lista de bornes e bibliotecas de fabricantes.

## Cores e logo

Paleta da empresa em `marca.py` (azul #0A2E5C, laranja #F58220, cinza #A6A6A6, branco). A logo fica em `assets/logo.png`:
para trocar, substitua o arquivo (de preferência PNG grande com fundo transparente). Fundo do desenho: Exibir > Alternar fundo claro/escuro.

## Limitações conhecidas

- É 2D. Sólidos 3D, imagens e objetos OLE não aparecem.
- Aparar e estender funcionam em linhas (ainda não em arcos, círculos e polilinhas).
- Deslocar não funciona em polilinhas com trechos curvos.
- Cotas e hachuras de arquivos existentes aparecem, mas não têm edição própria.
- Testes automáticos: `python3 tests_geom.py`, `tests_eletrica.py` e `tests_projeto.py`. A interface foi verificada só com bibliotecas simuladas, não em um Mac real: relate qualquer problema.
