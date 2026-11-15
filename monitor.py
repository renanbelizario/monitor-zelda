import os
import time
import requests
from playwright.sync_api import sync_playwright

URL_PRODUTO = "https://nintendo.com"
TOPICO_NTFY = os.environ.get("TOPICO_NTFY") or "meu_alerta_de_switch_2_8042"

TOTAL_CHECAGENS = 15
INTERVALO_SEGUNDOS = 60

def enviar_notificacao(mensagem):
    requests.post(
        f"https://ntfy.sh{TOPICO_NTFY}",
        data=mensagem.encode("utf-8"),
        headers={
            "Title": "ESTOQUE: Switch 2 Zelda Edition!",
            "Priority": "urgent",
            "Tags": "rotating_light,video_game",
            "Click": URL_PRODUTO
        }
    )

def verificar():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="America/New_York"
        )
        
        # Esconde a assinatura de robô do Playwright
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = context.new_page()

        for tentativa in range(1, TOTAL_CHECAGENS + 1):
            print(f"\n--- Checagem {tentativa} de {TOTAL_CHECAGENS} ---")
            try:
                # Navega direto para a URL do produto em toda checagem (evita ficar preso na home)
                page.goto(URL_PRODUTO, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(5000)

                url_atual = page.url
                titulo_pagina = page.title()
                print(f"URL atual: {url_atual}")
                print(f"Título: {titulo_pagina}")

                # Se a Nintendo redirecionou para a home, tenta forçar a ida novamente
                if "121642" not in url_atual:
                    print("Redirecionado para fora do produto. Tentando acessar novamente...")
                    page.goto(URL_PRODUTO, wait_until="load", timeout=45000)
                    page.wait_for_timeout(5000)

                botao = page.locator("button").filter(
                    has_text="Sold out"
                ).or_(
                    page.locator("button").filter(has_text="Add to cart")
                ).or_(
                    page.locator("button").filter(has_text="Pre-order")
                ).first

                if botao.count() > 0:
                    texto_botao = botao.inner_text().strip()
                    esta_desabilitado = botao.is_disabled()
                    print(f"SUCESSO! Botão: '{texto_botao}' | Desabilitado: {esta_desabilitado}")

                    if not esta_desabilitado and "sold out" not in texto_botao.lower():
                        print("DISPONÍVEL! Disparando alerta urgente para o iPhone...")
                        enviar_notificacao(f"CORRA! O Switch 2 Zelda Edition voltou! Botão: {texto_botao}")
                        break
                else:
                    texto_visivel = page.locator("body").inner_text()[:250].replace("\n", " ")
                    print(f"Botão não encontrado. Texto na tela: {texto_visivel}")

            except Exception as erro:
                print(f"Aviso na checagem {tentativa}: {erro}")

            if tentativa < TOTAL_CHECAGENS:
                time.sleep(INTERVALO_SEGUNDOS)

        browser.close()

if __name__ == "__main__":
    verificar()
