import time
import requests
from playwright.sync_api import sync_playwright

URL_PRODUTO = "https://nintendo.com"
TOPICO_NTFY = "meu_alerta_de_switch_2_8042"

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
        # Argumentos para evitar bloqueio de bot na Nintendo Store
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US"
        )
        page = context.new_page()

        for tentativa in range(1, TOTAL_CHECAGENS + 1):
            print(f"\n--- Checagem {tentativa} de {TOTAL_CHECAGENS} ---")
            try:
                if tentativa == 1:
                    page.goto(URL_PRODUTO, wait_until="networkidle", timeout=45000)
                else:
                    page.reload(wait_until="networkidle", timeout=45000)

                # Espera 3 segundos extras para o JavaScript terminar de carregar o botão
                page.wait_for_timeout(3000)

                titulo_pagina = page.title()
                print(f"Página carregada: {titulo_pagina}")

                # Procura botões que contenham algum dos textos de status de compra
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
                    print(f"Sucesso! Botão: '{texto_botao}' | Desabilitado: {esta_desabilitado}")

                    if not esta_desabilitado and "sold out" not in texto_botao.lower():
                        print("DISPONÍVEL! Disparando alerta urgente para o iPhone...")
                        enviar_notificacao(f"CORRA! O Switch 2 Zelda Edition voltou! Botão: {texto_botao}")
                        break
                else:
                    # Imprime um trecho do texto da página para sabermos o que apareceu na tela
                    texto_visivel = page.locator("body").inner_text()[:300].replace("\n", " ")
                    print(f"Botão não encontrado. Texto na tela: {texto_visivel}")

            except Exception as erro:
                print(f"Aviso na checagem {tentativa}: {erro}")

            if tentativa < TOTAL_CHECAGENS:
                time.sleep(INTERVALO_SEGUNDOS)

        browser.close()

if __name__ == "__main__":
    verificar()
