from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from fake_useragent import UserAgent
import time


def fetch_html_by_selenium(url: str, wait_seconds: int = 3) -> str:
    ua = UserAgent().random

    options = Options()
    options.add_argument(f"user-agent={ua}")
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)

    try:
        driver.get(url)
        time.sleep(wait_seconds)
        return driver.page_source
    finally:
        driver.quit()


if __name__ == "__main__":
    url = "https://www.shaanxi.gov.cn/xw/"
    html = fetch_html_by_selenium(url)

    with open("page_source_shanxi.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("HTML 已保存到 page_source.html")