import sys
from time import sleep
from typing import Any

import undetected_chromedriver as uc
from selenium.webdriver.firefox.webdriver import WebDriver
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support.expected_conditions import staleness_of, presence_of_element_located, element_to_be_clickable
from selenium.webdriver.common.keys import Keys
import urllib.parse
import re
import socket
from socket import socket as Socket
import threading

base_url = "https://translate.google.ru"
txt_xpath = "//textarea[@jsaction]"
det_xpath = "//a[@href='./details' and @jsaction]"

def get_options() -> uc.ChromeOptions:
    options = uc.ChromeOptions()

    options.add_argument('--disable-component-extensions-with-background-pages')
    options.add_argument('--disable-features=site-per-process')
    options.add_argument('--disable-threaded-scrolling')
    options.add_argument('--disable-threaded-animation')
    options.add_argument('--disable-features=MediaRouter')
    options.add_argument('--disable-sync')
    options.add_argument('--disable-breakpad')
    options.add_argument('--disable-background-networking')
    options.add_argument('--disable-notifications')
    options.add_argument('--autoplay-policy=user-gesture-required')
    options.add_argument('--disable-features=Translate')
    options.add_argument('--no-sandbox')
    options.add_argument('--headless=new')
    options.add_argument('--enable-javascript')
    options.add_argument('--disable-gpu')
    options.add_argument('--single-process')
    return options


def get_translate_url(lfrom: str, lto: str, text: str) -> str:
    return f"/details?sl={lfrom}&tl={lto}&text={urllib.parse.quote(text)}&op=translate&pli=1"

def get_browser() -> uc.Chrome:
    return uc.Chrome(enable_cdp_events=True, headless=True, use_subprocess=True, options=get_options(), version_main=120)

def get_select_word_script(word) -> str:
    res = f"var el = document.evaluate(\"{txt_xpath}\", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; "\
        f"el.value = \"{word}\"; el.textContent = \"{word}\"; el.select(); el.select(); el.click(); el.select(); el.select(); el.click()"
    print(res)
    return res
class WordTranslator:
    def __init__(self, browser: uc.Chrome, example_word, lfrom, lto):
        print(f"Create tab for translation from {lfrom} to {lto}. First word is {example_word}")
        self.browser = browser
        self.browser.switch_to.new_window('tab')
        self.browser.get(base_url+get_translate_url(lfrom, lto, example_word))
        #WebDriverWait(self.browser, 15).until(element_to_be_clickable((By.XPATH, txt_xpath+f"[contains(text(), \"{word}\")]")))
        #self.browser.execute_script(get_select_word_script(word))
        #self.browser.save_screenshot("/tmp/det_t_el.png")
        det_el = WebDriverWait(self.browser, 15).until(element_to_be_clickable((By.XPATH, det_xpath)))
        det_el.click()
        self.tab = self.browser.current_window_handle


    def translate_word(self, word: str) -> str:
        self.browser.switch_to.window(self.tab)
        print(f"Translate word \"{word}\" in tab with url \"{self.browser.current_url}\"")
        word = word.replace("\"", "").replace("'", "\\'")
        self.browser.execute_script(get_select_word_script(word))
        det_t_xpath = f"//div[./h3/span[text()='{word}']]/table"
        self.browser.save_screenshot("/tmp/det_t_el.png")
        det_t_el = WebDriverWait(self.browser, 4).until(presence_of_element_located((By.XPATH, det_t_xpath)))
        det_t_html = det_t_el.get_attribute('outerHTML')
        res = re.sub(r"(class|js\w+?|data[\w-]+?)\=\"[^\"]*?\"", "", det_t_html)
        res = re.sub(r"<(\w{1,4})[^>]*? aria-hidden=\"true\"[^>]*?>[^<]*?</\1>", "", res)
        res = re.sub(r"<(\w{1,4})[^>]*?display=\"none\"[^>]*?>[^<]*?</\1>", "", res)
        return re.sub(r" +", " ", res)


class PhraseTranslator:
    result_xpath = "//div[@dir='ltr']//span[contains(@jsaction, 'mouseover') and contains(@jsaction, 'mouseover')]"
    def __init__(self, browser: uc.Chrome):
        self.browser = browser
        self.browser.switch_to.new_window('tab')
        self.browser.get(base_url)
        self.tab = self.browser.current_window_handle

    def translate_phrase(self, text: str, lfrom: str, lto: str) -> str:
        self.browser.switch_to.window(self.tab)
        self.browser.get(base_url + get_translate_url(lfrom, lto, text))
        res_el = WebDriverWait(self.browser, 15).until(presence_of_element_located((By.XPATH, self.result_xpath)))
        return res_el.text

databases = ["en_ru", "ru_en"]
sample_words = {"en_ru": "starvation", "ru_en": "кризис"}
class CommonTranslator:
    def __init__(self):
        self.browser = get_browser()
        self.wts = {x: WordTranslator(self.browser, sample_words[x], *(x.split("_"))) for x in databases}
        self.pt = PhraseTranslator(self.browser)
        self.mutex = threading.Lock()

    def translate(self, text: str, db: str) -> str:
        lfrom, lto = db.split("_")
        with self.mutex:
            if re.match(r"\w+?\s+?\w+?", text):
                return self.pt.translate_phrase(text, lfrom, lto)
            else:
                try:
                    return self.wts[db].translate_word(text)
                except Exception as e:
                    print(e)
                    return self.pt.translate_phrase(text, lfrom, lto)
    def get_databases(self):
        return "\n".join([f"{x} \"{x}\"" for x in databases])

HOST = '127.0.0.1'
PORT = 2627
def handle_client(client_socket: Socket, translator: CommonTranslator):
    raw_data = socket.SocketIO(client_socket, "r").readline()
    command_str = raw_data.decode()

    print(f"Got command {command_str}")


    if command_str.upper().startswith("DEFINE"):
        rgxp = r"\w+? +(.+?) +(.+)"
        text = re.sub(rgxp, r"\2", command_str).replace("\n", "")
        db = re.sub(rgxp, r"\1", command_str).replace("\n", "")
        try:
            answer = translator.translate(text, db)
            client_socket.send("150 found\n".encode())
            client_socket.send(answer.encode())
            client_socket.send("\n.\n250 ok\n".encode())
        except Exception as e:
            print(e)
            client_socket.send("502 internal error\n".encode())
    elif command_str.upper().startswith("SHOW DB") or command_str.upper().startswith("SHOW DATABASES"):
        client_socket.send(f"150 {len(databases)} db found\n".encode())
        client_socket.send(translator.get_databases().encode())
        client_socket.send("\n.\n250 ok\n".encode())
    else:
        client_socket.send("505 unknown command\n".encode())

    # Close the client socket
    client_socket.close()


def start_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((HOST, PORT))

    server_socket.listen(5)

    print(f"[*] Listening on {HOST}:{PORT}")
    translator = CommonTranslator()

    while True:
        # Accept a connection from a client
        client_socket, addr = server_socket.accept()
        print(f"[*] Accepted connection from {addr[0]}:{addr[1]}")

        # Handle the client in a new thread
        client_handler = threading.Thread(target=handle_client, args=(client_socket, translator, ))
        client_handler.start()


if __name__ == "__main__":
    start_server()