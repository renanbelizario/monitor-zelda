import os
import re
import time
import random
import requests
from playwright.sync_api import sync_playwright

# Link oficial exato do produto na Nintendo Store US
URL_PRODUTO = "https://www.nintendo.com/us/store/products/nintendo-switch-2-the-legend-of-zelda-40th-anniversary-edition-121642/"

# Lê exclusivamente do GitHub Secrets
TOPICO_NTFY = os.environ.get("TOPICO_NTFY")

# 15 checagens com intervalo aleatório (45s a 65s) = ~14 minutos por rodada
TOTAL_CHECAGENS = 15


def enviar_notificacao(mensagem):
    if not TOPICO_NTFY:
        print("ERRO: Variável TOPICO_NTFY não configurada nos Secrets!")
        return

    requests.post(
        f"https://ntfy.sh/{TOPICO_NTFY}",
        data=mensagem.encode("utf-8"),
        headers={
            "Title": "ESTOQUE: Switch 2 Zelda 40th Edition!",
            "Priority": "urgent",
            "Tags": "rotating_light,video_game",
            "Click": URL_PRODUTO,
        },
    )


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

        for tentativa in range(1, TOTAL_CHECAGENS + 1):
            print(f"\n--- Checagem {tentativa} de {TOTAL_CHECAGENS} ---")
            try:
                page.goto(URL_PRODUTO, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(5000)

                url_atual = page.url
                print(f"URL atual: {url_atual}")

                if "121642" not in url_atual:
                    print("Redirecionado para fora do produto. Tentando acessar novamente...")
                    page.goto(URL_PRODUTO, wait_until="load", timeout=45000)
                    page.wait_for_timeout(5000)

                texto_pagina = page.locator("body").inner_text()

                # Proteção contra página 404 ("Whoops!") ou erro de carregamento
                if "whoops!" in texto_pagina.lower() or "can't be found" in texto_pagina.lower():
                    print("Aviso: Página retornou 'Whoops!' (erro temporário). Ignorando...")
                else:
                    # 1. Verifica se ainda existe botão explícito de "Sold out"
                    botao_esgotado = page.locator("button").filter(
                        has_text=re.compile(r"sold out|out of stock|unavailable", re.IGNORECASE)
                    ).first

                    if botao_esgotado.count() > 0:
                        print(f"Ainda esgotado: '{botao_esgotado.inner_text().strip()}'")
                    else:
                        # 2. Procura qualquer botão de compra habilitado (ex: "Add to cart")
                        botao_compra = page.locator("button").filter(
                            has_text=re.compile(
                                r"add to cart|buy|order|purchase|pre-order|select|check availability",
                                re.IGNORECASE,
                            )
                        ).first

                        if botao_compra.count() > 0 and not botao_compra.is_disabled():
                            texto_botao = botao_compra.inner_text().strip()
                            print(f"DISPONÍVEL! Botão encontrado: '{texto_botao}'")
                            enviar_notificacao(
                                f"CORRA! O Switch 2 Zelda 40th Edition voltou! Botão: {texto_botao}"
                            )
                            break
                        else:
                            # 3. Rede de segurança: avisa se o "Sold out" sumiu de uma página válida do produto
                            if "zelda" in page.title().lower() and "499" in texto_pagina:
                                print("ALERTA DE MUDANÇA: O botão 'Sold out' desapareceu da página!")
                                enviar_notificacao(
                                    "ATENÇÃO! O aviso de 'Sold out' sumiu da página do Zelda 40th Edition. Confira agora!"
                                )
                                break

            except Exception as erro:
                print(f"Aviso na checagem {tentativa}: {erro}")

            if tentativa < TOTAL_CHECAGENS:
                espera = random.randint(45, 65)
                print(f"Aguardando {espera} segundos para a próxima checagem...")
                time.sleep(espera)

        browser.close()


if __name__ == "__main__":
    verificar()
