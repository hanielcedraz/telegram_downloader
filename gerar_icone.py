#!/usr/bin/env python3
"""
Gera o ícone do Telegram Downloader.

Uso:
    python gerar_icone.py ico  <caminho/icone.ico>       # Windows
    python gerar_icone.py png  <pasta/icone.iconset>     # macOS (vira .icns)

Precisa do Pillow. Se ele não estiver disponível, sai em silêncio —
o instalador segue sem ícone personalizado.
"""

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Pillow indisponivel; seguindo sem icone personalizado.")
    raise SystemExit(0)


def desenhar(tamanho: int) -> "Image.Image":
    S = tamanho
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # fundo arredondado azul com leve degradê
    raio = int(S * 0.22)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=raio, fill=(41, 128, 185, 255))

    # brilho: composto por cima, recortado no mesmo arredondamento
    brilho = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    db = ImageDraw.Draw(brilho)
    for i in range(S):
        db.line([(0, i), (S, i)], fill=(255, 255, 255, int(55 * (1 - i / S))))
    mascara = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mascara).rounded_rectangle(
        [0, 0, S - 1, S - 1], radius=raio, fill=255)
    brilho.putalpha(Image.composite(
        brilho.getchannel("A"), Image.new("L", (S, S), 0), mascara))
    img = Image.alpha_composite(img, brilho)

    # seta de download
    d = ImageDraw.Draw(img)
    cx = S // 2
    larg = int(S * 0.095)
    d.rectangle([cx - larg, int(S * 0.23), cx + larg, int(S * 0.52)],
                fill=(255, 255, 255, 255))
    d.polygon([(cx - int(S * 0.20), int(S * 0.49)),
               (cx + int(S * 0.20), int(S * 0.49)),
               (cx, int(S * 0.72))], fill=(255, 255, 255, 255))

    # bandeja
    d.rounded_rectangle([int(S * 0.22), int(S * 0.77),
                         int(S * 0.78), int(S * 0.845)],
                        radius=max(2, int(S * 0.02)),
                        fill=(255, 255, 255, 235))
    return img


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)

    formato, destino = sys.argv[1].lower(), Path(sys.argv[2])
    grande = desenhar(1024)

    if formato == "ico":
        destino.parent.mkdir(parents=True, exist_ok=True)
        grande.resize((256, 256), Image.LANCZOS).save(
            destino,
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                   (64, 64), (128, 128), (256, 256)],
        )
        print(f"icone gravado em {destino}")

    elif formato == "png":
        destino.mkdir(parents=True, exist_ok=True)
        for tam in (16, 32, 64, 128, 256, 512):
            grande.resize((tam, tam), Image.LANCZOS).save(
                destino / f"icon_{tam}x{tam}.png")
            grande.resize((tam * 2, tam * 2), Image.LANCZOS).save(
                destino / f"icon_{tam}x{tam}@2x.png")
        grande.save(destino / "icon_512x512@2x.png")
        print(f"iconset gravado em {destino}")

    else:
        print(f"formato desconhecido: {formato}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
