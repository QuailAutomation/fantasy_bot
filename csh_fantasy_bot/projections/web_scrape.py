from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys

        
def remote_scrape(process_page_func):

    chrome_options = Options()

    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-background-timer-throttling')
    chrome_options.add_argument('--disable-breakpad')
    chrome_options.add_argument('--disable-component-extensions-with-background-pages')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-features=TranslateUI,BlinkGenPropertyTrees')
    chrome_options.add_argument('--disable-ipc-flooding-protection')
    chrome_options.add_argument('--disable-renderer-backgrounding')
    chrome_options.add_argument('--enable-features=NetworkService,NetworkServiceInProcess')
    chrome_options.add_argument('--force-color-profile=srgb')
    chrome_options.add_argument('--hide-scrollbars')
    chrome_options.add_argument('--metrics-recording-only')
    chrome_options.add_argument('--mute-audio')
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--log-level=3")

    driver =  webdriver.Remote("http://192.168.1.220:3001/webdriver", chrome_options.to_capabilities())
    driver.implicitly_wait(5)
    # driver = webdriver.Chrome(chrome_options=chrome_options)
    driver.set_page_load_timeout(6000)

    return process_page_func(driver)
    