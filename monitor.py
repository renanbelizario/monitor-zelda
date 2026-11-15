import os
import re
import time
import random
import requests
from playwright.sync_api import sync_playwright

# Lista completa com os links diretos das 5 lojas e teto máximo de US$ 520.00
PRODUTOS = [
    {
        "loja": "Nintendo Store",
        "url": "https://www.nintendo.com/us/store/products/nintendo-switch-2-the-legend-of-zelda-40th-anniversary-edition-121642/",
        "preco_maximo": 520.00,
    },
    {
        "loja": "Best Buy",
        "url": "https://www.bestbuy.com/product/switch-2-the-legend-of-zelda-40th-anniversary-edition/J7GSL57HTY/sku/6691841",
        "preco_maximo": 520.00,
    },
    {
        "loja": "GameStop",
        "url": "https://www.gamestop.com/consoles-hardware/nintendo-switch-2/products/nintendo-switch-2-the-legend-of-zelda-40th-anniversary-edition/20037854.html",
        "preco_maximo": 520.00,
    },
    {
        "loja": "Walmart",
        "url": "https://www.walmart.com/ip/Nintendo-Switch-2-The-Legend-of-Zelda-40th-Anniversary-Edition/21002656445",
        "preco_maximo": 520.00,
    },
    {
        "loja": "Amazon",
        "url": "https://a.co/d/04cWwKgD",
        "preco_maximo": 520.00,
    },
]

TOPICO_NTFY = os.environ.get("TOPICO_NTFY")
TOTAL_RODADAS = 8


def enviar_notificacao(loja, url, mensagem):
    if not TOPICO_NTFY:
        print("ERRO: Variável TOPICO_NTFY não configurada nos Secrets!")
        return

    requests.post(
        f"https://ntfy.sh/{TOPICO_NTFY}",
        data=mensagem.encode("utf-8"),
        headers={
            "Title": f"ESTOQUE OFICIAL ({loja}): Switch 2 Zelda!",
            "Priority": "urgent",
            "Tags": "rotating_light,video_game",
            "Click": url,
        },
    )


def preco_dentro_do_oficial(texto_pagina, preco_maximo):
    precos_encontrados = re.findall(r"\$(\d{3,4}(?:\.\d{2})?)", texto_pagina)
    if not precos_encontrados:
        return True

    valores = [float(p) for p in precos_encontrados if float(p) >= 350.0]
    if not valores:
        return True

    menor_preco = min(valores)
    print(f"   Menor preço detectado: ${menor_preco:.2f}")
    return menor_preco <= preco_maximo


def vendedor_oficial_confirmado(loja, texto_lower):
    if loja == "Amazon":
        return bool(
            re.search(r"(shipper\s*/\s*seller|sold by)[:\s]*amazon\.com", texto_lower)
        )
    if loja == "Walmart":
        return (
            "sold and shipped by walmart.com" in texto_lower
            or "sold and shipped by walmart" in texto_lower
        )
    return True


def checar_produto(page, item):
    loja = item["loja"]
    url = item["url"]
    preco_maximo = item.get("preco_maximo", 520.00)
    print(f"[{loja}] Acessando página...")

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(5000)

        texto_bruto = page.locator("body").inner_text()
        texto_lower = texto_bruto.lower()

        # 1. Filtro contra páginas desativadas, erros ou CAPTCHA
        termos_bloqueio = [
            "whoops!",
            "can't be found",
            "we could not find this page",
            "uh-oh",
            "verify you are human",
            "robot or human",
            "enter the characters you see below",
            "access denied",
            "captcha",
        ]
        if any(termo in texto_lower for termo in termos_bloqueio):
            print(f"[{loja}] Página desativada, erro ou CAPTCHA. Ignorando.")
            return False

        # 2. Trava específica da GameStop: ignora item exclusivo de loja física ("Available In Stores")
        if loja == "GameStop":
            termos_loja_fisica = [
                "not available",
                "out of stock",
                "exclusively in stores",
                "available in stores",
                "shop in person",
            ]
            if any(termo in texto_lower for termo in termos_loja_fisica):
                print(f"[{loja}] Esgotado online (apenas loja física).")
                return False

        # 3. Trava específica da Best Buy: ignora quando exibe apenas retirada indisponível
        if loja == "Best Buy":
            if "shipping unavailable" in texto_lower or "choose pickup location" in texto_lower:
                print(f"[{loja}] Esgotado online.")
                return False

        # 4. Verifica se existe botão ou aviso claro de esgotado
        botao_esgotado = page.locator("button, input[type='submit']").filter(
            has_text=re.compile(
                r"sold out|out of stock|unavailable|not available|coming soon|check stores|available in stores",
                re.IGNORECASE,
            )
        ).first

        if botao_esgotado.count() > 0:
            print(f"[{loja}] Esgotado ('{botao_esgotado.inner_text().strip()}').")
            return False

        # 5. Procura APENAS botões reais de compra (removido 'a' para não confundir com links do menu como 'Pre-Order')
        botao_compra = page.locator("button, input[type='submit']").filter(
            has_text=re.compile(
                r"^(add to cart|pre-order|pre-order now|buy now|ship it|add to bag)$",
                re.IGNORECASE,
            )
        ).first

        if botao_compra.count() > 0 and not botao_compra.is_disabled():
            if not vendedor_oficial_confirmado(loja, texto_lower):
                print(f"[{loja}] Ignorado: anúncio de revendedor terceirizado.")
                return False

            if not preco_dentro_do_oficial(texto_bruto, preco_maximo):
                print(f"[{loja}] Ignorado: preço acima do teto (${preco_maximo:.2f}).")
                return False

            texto_botao = botao_compra.inner_text().strip() or "Add to Cart"
            print(f"[{loja}] DISPONÍVEL ONLINE NO PREÇO OFICIAL! Botão: '{texto_botao}'")
            enviar_notificacao(
                loja,
                url,
                f"CORRA! Estoque OFICIAL na {loja} (até $520)! Botão: {texto_botao}",
            )
            return True

        print(f"[{loja}] Sem botão de compra online ativo.")
        return False

    except Exception as erro:
        print(f"[{loja}] Erro ao carregar: {erro}")
        return False


def verificar():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="America/New_York",
        )

        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = context.new_page()

        for rodada in range(1, TOTAL_RODADAS + 1):
            print(f"\n=== Rodada {rodada} de {TOTAL_RODADAS} ===")
            for item in list(PRODUTOS):
                encontrou = checar_produto(page, item)
                if encontrou:
                    PRODUTOS.remove(item)
                time.sleep(random.randint(3, 5))

            if not PRODUTOS:
                print("Todos os itens monitorados foram encontrados! Encerrando.")
                break

            if rodada < TOTAL_RODADAS:
                espera = random.randint(35, 50)
                print(f"Aguardando {espera}s para a próxima rodada...")
                time.sleep(espera)

        browser.close()


if __name__ == "__main__":
    verificar()
