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
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US"
        )
        page = context.new_page()

        try:
            for tentativa in range(1, TOTAL_CHECAGENS + 1):
                print(f"\n--- Checagem {tentativa} de {TOTAL_CHECAGENS} ---")
                
                if tentativa == 1:
                    page.goto(URL_PRODUTO, wait_until="domcontentloaded", timeout=30000)
                else:
                    page.reload(wait_until="domcontentloaded", timeout=30000)

                marcador = page.locator('span[data-drawer-id="add-to-cart-drawer"]')
                marcador.wait_for(state="attached", timeout=20000)

                botao = page.locator('span[data-drawer-id="add-to-cart-drawer"]').locator("xpath=preceding::button")
                
                page.wait_for_function(
                    """(btn) => btn && btn.innerText.trim() !== '' && !btn.innerText.toLowerCase().includes('loading')""",
                    arg=botao.element_handle(),
                    timeout=15000
                )

                texto_botao = botao.inner_text().strip()
                esta_desabilitado = botao.is_disabled()

                print(f"Status: '{texto_botao}' | Desabilitado: {esta_desabilitado}")

                if not esta_desabilitado and "sold out" not in texto_botao.lower():
                    print("DISPONÍVEL! Disparando alerta urgente para o iPhone...")
                    enviar_notificacao(f"CORRA! O Switch 2 Zelda Edition voltou! Botão: {texto_botao}")
                    break
                
                if tentativa < TOTAL_CHECAGENS:
                    time.sleep(INTERVALO_SEGUNDOS)

        except Exception as erro:
            print(f"Erro durante a verificação: {erro}")
        finally:
            browser.close()

if __name__ == "__main__":
    verificar()
