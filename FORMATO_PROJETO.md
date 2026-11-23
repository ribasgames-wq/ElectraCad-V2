# Formato de projeto ElectraCad (JSON)

Arquivo que a IA do ElectraCad (Base44) pode gerar e que o ElectraCad desktop abre em **Arquivo > Importar projeto (JSON da IA)**.
O desktop também exporta nesse formato (**Arquivo > Exportar projeto**), para voltar ao app online.

- Coordenadas em `unidade` ("mm", "cm" ou "m"), com **Y para cima**, origem em (0, 0).
- Todos os blocos são opcionais; itens inválidos são ignorados e listados num aviso.

```json
{
  "formato": "electracad-projeto",
  "versao": 1,
  "unidade": "m",
  "nome": "Casa 01",
  "paredes": [ { "pontos": [[0,0],[10,0],[10,8],[0,8]], "fechada": true } ],
  "ambientes": [ { "nome": "Sala", "x": 1.0, "y": 1.0 } ],
  "simbolos": [
    { "tipo": "luz_teto", "x": 2.5, "y": 2.0, "rotacao": 0, "circuito": "C1" },
    { "tipo": "tomada_baixa", "x": 0.2, "y": 3.0, "rotacao": 90, "circuito": "C2" }
  ],
  "eletrodutos": [ { "tipo": "teto", "pontos": [[2.5,2.0],[5,2.0]] } ],
  "circuitos": [
    { "nome": "Iluminação social", "tipo": "Iluminação", "tensao": 127, "fases": "F+N", "potencia_va": 600 },
    { "nome": "Chuveiro", "tipo": "TUE", "tensao": 220, "fases": "F+F", "potencia_va": 5500 }
  ]
}
```

Campos: `rotacao` em graus (anti-horário). `eletrodutos[].tipo`: "teto" (linha contínua) ou "piso" (tracejado).
`circuitos[].tipo`: "Iluminação", "TUG" ou "TUE". `fases`: "F+N", "F+F" ou "3F". Potência em VA.

## Valores aceitos em `simbolos[].tipo`

| tipo | Descrição | Categoria |
|---|---|---|
| `luz_teto` | Ponto de luz no teto | Iluminação |
| `arandela` | Arandela (luz na parede) | Iluminação |
| `fluorescente` | Luminária fluorescente | Iluminação |
| `embutido` | Luminária embutida (spot) | Iluminação |
| `emergencia` | Luminária de emergência | Iluminação |
| `int_1s` | Interruptor simples (1 seção) | Interruptores |
| `int_2s` | Interruptor de 2 seções | Interruptores |
| `int_paralelo` | Interruptor paralelo (three-way) | Interruptores |
| `dimmer` | Dimmer | Interruptores |
| `sensor_presenca` | Sensor de presença | Interruptores |
| `tomada_baixa` | Tomada baixa (0,30 m) | Tomadas |
| `tomada_media` | Tomada média (1,30 m) | Tomadas |
| `tomada_alta` | Tomada alta (2,00 m) | Tomadas |
| `tue` | Tomada de uso específico (TUE) | Tomadas |
| `quadro_dist` | Quadro de distribuição | Quadros e caixas |
| `medidor` | Medidor (kWh) | Quadros e caixas |
| `caixa_passagem` | Caixa de passagem | Quadros e caixas |
| `ventilador` | Ventilador de teto | Equipamentos |
| `ar_cond` | Ar-condicionado | Equipamentos |
| `motor` | Motor | Equipamentos |
| `campainha` | Campainha / cigarra | Equipamentos |
| `terra` | Aterramento | Aterramento |

## Pedido para colar no construtor do Base44

> No meu app, adicione um botão "Exportar para ElectraCad Desktop" que baixa um arquivo .json no formato abaixo
> (formato = "electracad-projeto", versao = 1). Use a unidade "m", Y para cima. Cada símbolo da planta deve virar um item
> de "simbolos" usando SOMENTE os valores de "tipo" da lista. Paredes viram "paredes", nomes de cômodos viram "ambientes",
> a tubulação vira "eletrodutos" e a tabela de cargas vira "circuitos". Também adicione um botão "Importar do desktop"
> que lê esse mesmo formato. [cole aqui o conteúdo do arquivo FORMATO_PROJETO.md]
