# Concilia

Conferência de extratos bancários em OFX. Aplicativo desktop usado no fluxo de
trabalho da Esquema Assessoria Contábil.

```
python app_desktop.py                  # abre a janela
python app_desktop.py extrato.ofx      # já abre com o arquivo carregado
python ofx_parser.py extrato.ofx       # imprime o extrato em JSON
python -m unittest                     # roda os testes
```

## O que o programa faz

- Lê OFX 1.x (SGML) e 2.x (XML), incluindo arquivos com mais de uma conta
  (conta corrente + cartão de crédito no mesmo arquivo).
- Reconstrói o **saldo após cada lançamento** a partir do saldo consolidado
  informado pelo banco (`LEDGERBAL`), e mostra o saldo anterior do período.
- Localiza lançamentos por texto (vários termos, em qualquer ordem) e filtra
  por créditos ou débitos. Os totais no rodapé acompanham o que está filtrado.
- Ordena por qualquer coluna, clicando no cabeçalho.
- Exporta em **PDF**, **XLSX** e **CSV** — sempre o que está sendo exibido, e o
  PDF avisa quando a exportação está filtrada.
- Duplo clique em uma linha mostra os detalhes (documento, FITID, referência).

### Atalhos

| Atalho | Ação |
| --- | --- |
| `Ctrl+O` | abrir arquivo |
| `F5` | recarregar o arquivo atual |
| `Ctrl+F` | ir para a busca |
| `Esc` | limpar a busca |
| `Ctrl+C` | copiar só o histórico das linhas selecionadas |
| `Ctrl+Shift+C` | copiar as linhas inteiras, prontas para colar no Excel |
| `Ctrl+A` | selecionar todos os lançamentos |
| `Ctrl+P` | exportar em PDF |

Também é possível arrastar o arquivo OFX para dentro da janela.

## Instalação nas máquinas do escritório

O instalador está anexado à release mais recente: `Concilia-1.0.0-setup.exe`.

Instala para o usuário atual, **sem pedir senha de administrador**. Cria atalho
no menu iniciar, opcionalmente na área de trabalho, e associa os arquivos `.ofx`
e `.qfx` ao programa — dá para dar duplo clique no extrato que ele abre direto.

A associação usa um ProgId próprio: se a máquina já tem outro programa que abre
OFX, os dois continuam aparecendo em "Abrir com", nenhum atropela o outro. A
desinstalação remove tudo, inclusive as preferências em `%APPDATA%\Concilia`.

Instalação silenciosa, para distribuir por script:

```
Concilia-1.0.0-setup.exe /VERYSILENT /NORESTART /TASKS=associar,desktopicon
```

## Desenvolvimento

O parser e a interface usam **apenas a biblioteca padrão** (Python 3.10+).
`reportlab`, `openpyxl`, `windnd` e `pillow` são opcionais e carregados só
quando a função correspondente é usada — veja `requirements.txt`.

```
pip install -r requirements.txt
```

Sem `reportlab` ou `openpyxl` o programa continua funcionando: ele avisa qual
pacote falta e a exportação em CSV segue disponível sem instalar nada.

### Gerando o executável e o instalador

```powershell
.\build.ps1                 # gera dist\Concilia\Concilia.exe
.\build_installer.ps1       # gera dist\Concilia-1.0.0-setup.exe (roda o build antes)
```

O `build_installer.ps1` precisa do [Inno Setup 6](https://jrsoftware.org/isdl.php).

O build usa `--onedir` de propósito. Com `--onefile` o executável se descompacta
em uma pasta temporária **a cada abertura**, o que costuma custar de 2 a 5
segundos toda vez. Em `--onedir` a janela abre em cerca de 0,7 s na primeira
execução e mais rápido nas seguintes.

Ao subir a versão, altere `VERSAO` em `app_desktop.py` e `#define Versao` em
`installer.iss`. **Não altere o `AppId`** no `installer.iss`: é ele que faz o
instalador reconhecer e substituir a instalação anterior em vez de criar uma
segunda cópia.

## Arquivos

| Arquivo | Conteúdo |
| --- | --- |
| `ofx_parser.py` | parser do formato OFX; não depende da interface |
| `app_desktop.py` | interface Tkinter |
| `test_ofx_parser.py` | testes do parser (`python -m unittest`) |
| `installer.iss` | script do instalador (Inno Setup) |
| `build.ps1` / `build_installer.ps1` | geração do executável e do instalador |
| `concilia.ico` / `concilia.png` | ícone do programa |
| `legacy/` | versão anterior, mantida para consulta |

Se existir um `logo.png` na pasta, ele aparece no cabeçalho da janela no lugar
do nome do programa — é o lugar de colocar o logo do escritório.

## Notas de manutenção

**O parser lê o arquivo em uma passagem só.** Um único `finditer` percorre o
texto e monta uma árvore de tags; os campos são lidos dessa árvore. A versão
anterior fazia uma expressão regular por campo de cada lançamento.

**A busca por tags é em largura, não em profundidade.** `<LEDGERBAL>` e
`<BANKACCTFROM>` são filhos diretos de `<STMTRS>`, mas aparecem no arquivo
depois de `<BANKTRANLIST>`. Em profundidade, cada consulta desceria por todos os
lançamentos antes de encontrá-los.

**Nada pesado é importado na inicialização.** É o que mantém a abertura rápida,
tanto no script quanto no executável. Ao adicionar uma biblioteca nova, importe
dentro da função que a usa, não no topo do arquivo.

**Codificação é adivinhada por pontuação.** Bancos brasileiros mandam cp1252,
latin-1 e UTF-8 sem que o cabeçalho seja confiável. O parser testa os candidatos
e escolhe o resultado com menos indícios de acentuação corrompida.

O arquivo lido é apenas lido: o programa nunca grava por cima do OFX original.
