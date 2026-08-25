"""Gera o icone do programa e as imagens do assistente de instalacao.

    python gerar_imagens.py

Produz:
    concilia.ico / concilia.png       icone do programa
    instalador/painel*.bmp            painel lateral do assistente
    instalador/marca*.bmp             marca no topo das paginas internas

O Inno Setup escolhe automaticamente o arquivo de melhor resolucao para a
escala de tela do usuario, por isso cada imagem sai em varios tamanhos. O
formato e BMP porque e o unico aceito em qualquer versao do Inno Setup.
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

AZUL = (2, 132, 199)         # #0284c7, o mesmo destaque da interface
AZUL_ESCURO = (7, 89, 133)   # #075985
BRANCO = (255, 255, 255)

PASTA_INSTALADOR = "instalador"

# O Inno usa a variante mais proxima da escala da tela (100%, 125%, 150%, 200%)
TAMANHOS_PAINEL = [(164, 314), (192, 386), (246, 459), (328, 628)]
TAMANHOS_MARCA = [(55, 58), (64, 68), (92, 97), (110, 116)]


def desenhar_marca(d: ImageDraw.ImageDraw, x: int, y: int, lado: int, cor=BRANCO) -> None:
    """Duas barras alinhadas (os lancamentos batendo) e a marca de conferido."""
    espessura = int(lado * 0.085)
    largura = int(lado * 0.46)
    esquerda = x + (lado - largura) // 2

    for deslocamento in (0.30, 0.46):
        topo = y + int(lado * deslocamento)
        d.rounded_rectangle(
            [esquerda, topo, esquerda + largura, topo + espessura],
            radius=espessura // 2,
            fill=cor,
        )

    p1 = (x + int(lado * 0.30), y + int(lado * 0.685))
    p2 = (x + int(lado * 0.45), y + int(lado * 0.80))
    p3 = (x + int(lado * 0.72), y + int(lado * 0.60))
    d.line([p1, p2, p3], fill=cor, width=espessura, joint="curve")
    for ponta in (p1, p3):
        r = espessura // 2
        d.ellipse([ponta[0] - r, ponta[1] - r, ponta[0] + r, ponta[1] + r], fill=cor)


def fonte(tamanho: int, negrito: bool = False):
    for nome in (("segoeuib.ttf", "segoeui.ttf") if negrito else ("segoeui.ttf",)):
        try:
            return ImageFont.truetype(nome, tamanho)
        except OSError:
            continue
    return ImageFont.load_default()


def gerar_icone() -> None:
    escala = 4
    lado = 256 * escala
    img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, lado - 1, lado - 1], radius=int(lado * 0.22), fill=AZUL + (255,))
    desenhar_marca(d, 0, 0, lado)
    img = img.resize((256, 256), Image.LANCZOS)
    img.save("concilia.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    img.save("concilia.png")
    print("concilia.ico / concilia.png")


def gerar_painel() -> None:
    """Painel lateral das paginas de boas-vindas e de conclusao."""
    for largura, altura in TAMANHOS_PAINEL:
        escala = 4
        img = Image.new("RGB", (largura * escala, altura * escala), AZUL)
        d = ImageDraw.Draw(img)
        L, A = img.size

        # degrade vertical, do azul de destaque para o azul escuro
        for y in range(A):
            t = y / A
            d.line(
                [(0, y), (L, y)],
                fill=tuple(int(AZUL[i] + (AZUL_ESCURO[i] - AZUL[i]) * t) for i in range(3)),
            )

        lado_marca = int(L * 0.44)
        desenhar_marca(d, (L - lado_marca) // 2, int(A * 0.24), lado_marca)

        nome = fonte(int(L * 0.155), negrito=True)
        legenda = fonte(int(L * 0.062))
        centro = L // 2
        d.text((centro, int(A * 0.545)), "Concilia", font=nome, fill=BRANCO, anchor="ma")
        d.text(
            (centro, int(A * 0.665)),
            "Conferência de extratos",
            font=legenda,
            fill=(186, 230, 253),
            anchor="ma",
        )

        caminho = os.path.join(PASTA_INSTALADOR, f"painel-{largura}x{altura}.bmp")
        img.resize((largura, altura), Image.LANCZOS).save(caminho)
        print(caminho)


def gerar_marca() -> None:
    """Marca pequena no topo das paginas internas (fundo branco do assistente)."""
    for largura, altura in TAMANHOS_MARCA:
        escala = 8
        img = Image.new("RGB", (largura * escala, altura * escala), BRANCO)
        d = ImageDraw.Draw(img)
        L, A = img.size

        lado = int(min(L, A) * 0.86)
        x, y = (L - lado) // 2, (A - lado) // 2
        d.rounded_rectangle([x, y, x + lado, y + lado], radius=int(lado * 0.22), fill=AZUL)
        desenhar_marca(d, x, y, lado)

        caminho = os.path.join(PASTA_INSTALADOR, f"marca-{largura}x{altura}.bmp")
        img.resize((largura, altura), Image.LANCZOS).save(caminho)
        print(caminho)


if __name__ == "__main__":
    os.makedirs(PASTA_INSTALADOR, exist_ok=True)
    gerar_icone()
    gerar_painel()
    gerar_marca()
