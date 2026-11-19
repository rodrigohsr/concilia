# Concilia

Leitor de extratos bancários em OFX para Windows. Abre o arquivo, mostra os
lançamentos com o saldo de cada linha e exporta para PDF, Excel ou CSV.

## Instalação

Baixe o instalador na [última release](https://github.com/rodrigohsr/concilia/releases/latest)
e execute.

Para instalar para todos os usuários de um servidor de terminal, rode como
administrador:

```powershell
.\instalar_no_servidor.ps1
```

## Uso

Abra o `.ofx` pelo botão, arrastando para a janela ou com duplo clique no
arquivo. A busca aceita vários termos e o filtro separa créditos de débitos.
Clique no cabeçalho de uma coluna para ordenar.

Clique na caixa à esquerda, ou aperte Espaço, para marcar um lançamento como
conferido. O botão Editar permite corrigir o histórico. As marcas e as
correções ficam salvas no computador; o arquivo OFX não é alterado.

| Atalho | Ação |
| --- | --- |
| `Ctrl+O` | abrir arquivo |
| `F5` | recarregar |
| `Ctrl+F` | buscar |
| `Espaço` | marcar as linhas selecionadas como conferidas |
| `Ctrl+C` | copiar o histórico das linhas selecionadas |
| `Ctrl+Shift+C` | copiar as linhas inteiras |
| `Ctrl+P` | exportar em PDF |

## Desenvolvimento

Requer Python 3.10 ou mais novo.

```
pip install -r requirements.txt
python app_desktop.py
python -m unittest
```

Para gerar o instalador, com o [Inno Setup 6](https://jrsoftware.org/isdl.php)
instalado:

```powershell
.\build_installer.ps1
```

Para publicar uma versão, altere `VERSAO` em `app_desktop.py` e `Versao` em
`installer.iss`, gere o instalador e anexe o `.exe` a uma release com a tag
`vX.Y.Z`.
