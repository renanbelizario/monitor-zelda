import os
import re
import asyncio
import random
import requests
from playwright.async_api import async_playwright

PRODUTOS = [
    {
        "loja": "Nintendo Store",
        "url": "https://www.nintendo.com/us/store/products/nintendo-switch-2-the-legend-of-zelda-40th-anniversary-edition-121642/",
        "preco_maximo": 520.00,
    },
    {
        "loja": "Best Buy",
        "url": "https://www.bestbuy.com/site/6691841.p?skuId=6691841&intl=nosplash",
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
TOTAL_RODADAS = 14  # 14 checagens simultâneas (~14 minutos por ciclo)


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


async def checar_produto(context, item):
    loja = item["loja"]
    url = item["url"]
    preco_maximo = item.get("preco_maximo", 520.00)
    page = await context.new_page()

    # Captura estado do botão diretamente da API interna da Best Buy (se responder em segundo plano)
    bestbuy_button_state = None

    async def interceptar_resposta(response):
        nonlocal bestbuy_button_state
        if loja == "Best Buy" and ("buttonState" in response.url or "fulfillment" in response.url):
            try:
                if response.status == 200:
                    dados = await response.text()
                    match = re.search(r'"buttonState"\s*:\s*"([A-Z_]+)"', dados)
                    if match:
                        bestbuy_button_state = match.group(1)
            except Exception:
                pass

    if loja == "Best Buy":
        page.on("response", interceptar_resposta)

    try:
        # Bloqueia imagens, fontes e mídia na Best Buy para carregar mais rápido e evitar timeout
        if loja == "Best Buy":
            await page.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,mp4}",
                lambda route: route.abort(),
            )

        await page.goto(url, wait_until="domcontentloaded", timeout=35000)
        await page.wait_for_timeout(6000 if loja == "Best Buy" else 5000)

        # Avaliação rápida via JSON interceptado da Best Buy
        if loja == "Best Buy" and bestbuy_button_state:
            if bestbuy_button_state in ["ADD_TO_CART", "PRE_ORDER"]:
                print(f"[{loja}] DISPONÍVEL ONLINE (API buttonState: {bestbuy_button_state})!")
                enviar_notificacao(
                    loja,
                    url,
                    f"CORRA! Estoque OFICIAL na {loja}! Status: {bestbuy_button_state}",
                )
                return item, True
            else:
                print(f"[{loja}] Esgotado via API ({bestbuy_button_state}).")
                return item, False

        texto_bruto = await page.locator("body").inner_text()
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
            return item, False

        # 2. Trava específica da Nintendo Store
        if loja == "Nintendo Store":
            if "sold out" in texto_lower or "out of stock" in texto_lower:
                print(f"[{loja}] Esgotado ('Sold out' detectado na página).")
                return item, False

        # 3. Trava específica da Best Buy (HTML fallback)
        if loja == "Best Buy":
            if "choose a country" in texto_lower:
                print(f"[{loja}] Bloqueio de seletor de país (Akamai/Geo).")
                return item, False
            if "sold out" in texto_lower or "coming soon" in texto_lower or "unavailable nearby" in texto_lower:
                print(f"[{loja}] Esgotado no HTML.")
                return item, False

        # 4. Trava específica da GameStop
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
                return item, False

        # 5. Verifica botão ou aviso claro de esgotado
        botao_esgotado = page.locator("button, input[type='submit']").filter(
            has_text=re.compile(
                r"sold out|out of stock|unavailable|not available|coming soon|check stores|available in stores",
                re.IGNORECASE,
            )
        ).first

        if await botao_esgotado.count() > 0:
            texto_esg = (await botao_esgotado.inner_text()).strip()
            print(f"[{loja}] Esgotado ('{texto_esg}').")
            return item, False

        # 6. Procura botões reais de compra online
        botao_compra = page.locator("button, input[type='submit']").filter(
            has_text=re.compile(
                r"^(add to cart|pre-order|pre-order now|buy now|ship it|add to bag)$",
                re.IGNORECASE,
            )
        ).first

        if await botao_compra.count() > 0:
            aria_disabled = await botao_compra.get_attribute("aria-disabled")
            if await botao_compra.is_disabled() or aria_disabled == "true":
                print(f"[{loja}] Botão de compra presente, mas desabilitado.")
                return item, False

            if not vendedor_oficial_confirmado(loja, texto_lower):
                print(f"[{loja}] Ignorado: anúncio de revendedor terceirizado.")
                return item, False

            if not preco_dentro_do_oficial(texto_bruto, preco_maximo):
                print(f"[{loja}] Ignorado: preço acima do teto (${preco_maximo:.2f}).")
                return item, False

            texto_botao = (await botao_compra.inner_text()).strip() or "Add to Cart"
            print(f"[{loja}] DISPONÍVEL ONLINE NO PREÇO OFICIAL! Botão: '{texto_botao}'")
            enviar_notificacao(
                loja,
                url,
                f"CORRA! Estoque OFICIAL na {loja} (até $520)! Botão: {texto_botao}",
            )
            return item, True

        print(f"[{loja}] Sem botão de compra online ativo.")
        return item, False

    except Exception as erro:
        print(f"[{loja}] Erro ao carregar (bloqueio WAF/timeout): {str(erro).splitlines()[0]}")
        return item, False
    finally:
        await page.close()


async def verificar():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-http2",
            ],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="America/New_York",
        )

        # Define cookies de sessão dos EUA para pular a tela de escolha de país da Best Buy
        await context.add_cookies(
            [
                {
                    "name": "intl_splash",
                    "value": "false",
                    "domain": ".bestbuy.com",
                    "path": "/",
                },
                {
                    "name": "vt",
                    "value": "us",
                    "domain": ".bestbuy.com",
                    "path": "/",
                },
            ]
        )

        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        for rodada in range(1, TOTAL_RODADAS + 1):
            print(f"\n=== Rodada Simultânea {rodada} de {TOTAL_RODADAS} ===")

            tarefas = [checar_produto(context, item) for item in PRODUTOS]
            await asyncio.gather(*tarefas)

            if rodada < TOTAL_RODADAS:
                espera = random.randint(45, 60)
                print(f"Aguardando {espera}s para a próxima rodada...")
                await asyncio.sleep(espera)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(verificar())
