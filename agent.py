from requests_html import HTMLSession
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import requests
import json
import sys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def bing_custom_search(query, subscription_key, custom_config_id="c1eab574-17b1-4ec6-b5da-4819a382c3e2"):
    """
    Perform a Bing custom search and return the first result URL.
    """
    base_url = "https://api.bing.microsoft.com/v7.0/custom/search"
    headers = {
        "Ocp-Apim-Subscription-Key": subscription_key
    }
    params = {
        "q": query,
        "customconfig": custom_config_id,
        "mkt": "en-US"
    }

    try:
        response = requests.get(base_url, headers=headers, params=params)
        response.raise_for_status()
        results = response.json()

        if "webPages" in results and "value" in results["webPages"]:
            return results["webPages"]["value"][0]["url"]
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error making search request: {e}")
        return None


def setup_html_session():
    """Initialize and return an HTML session"""
    return HTMLSession()


def extract_content_with_formatting(url):
    """
    Extract content from the URL using Selenium and return it in markdown format and a list of image URLs.
    Returns a tuple of (markdown_content, image_urls).
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    image_urls = []

    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(url)

        # Wait for main content to load
        wait = WebDriverWait(driver, 10)
        main_content = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "Pubs_mainContent__5jvpQ")))

        # Get the page source after JavaScript has rendered
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        main_content = soup.select_one("div.Pubs_mainContent__5jvpQ")

        if not main_content:
            print("Couldn't find the main content div.")
            return None, []

        markdown_content = []

        for elem in main_content.descendants:
            if elem.name == 'img':
                img_url = elem.get('src')
                alt_text = elem.get('alt', '')

                if img_url and img_url.startswith("https://pubs2-images"):
                    img_url = urljoin(url, img_url)
                    image_urls.append(img_url)
                    markdown_content.append(f'\n![{alt_text}]({img_url})\n')

            elif elem.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                if elem.text.strip():
                    heading_level = elem.name[1]
                    heading_text = elem.text.strip()
                    markdown_content.append(f'\n{"#" * int(heading_level)} {heading_text}\n')

            elif elem.name == 'p':
                if elem.text.strip():
                    markdown_content.append(f'\n{elem.text.strip()}\n')

            elif elem.name == 'a':
                href = elem.get('href')
                if href and elem.text.strip():
                    markdown_content.append(f'[{elem.text.strip()}]({urljoin(url, href)})')

            elif isinstance(elem, str):
                text = elem.strip()
                if text and elem.parent.name not in ['a', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    markdown_content.append(text)

        return '\n'.join(markdown_content), image_urls

    except Exception as e:
        print(f"Error extracting content: {e}")
        return None, []

    finally:
        driver.quit()


def search_and_scrape_userguides(query, subscription_key):
    """
    Main function that combines search and scraping functionality.
    Returns markdown-formatted content and image URLs from the first search result.
    """
    url = bing_custom_search(query, subscription_key)
    if not url:
        return "No results found for the search query.", []

    content, image_urls = extract_content_with_formatting(url)
    if not content:
        return "Could not extract content from the webpage.", []

    return content, image_urls


def main():
    subscription_key = "339ca07c9a1e466f8786e48690598be0"  # Replace with your actual key
    query = input("Enter your search query: ").strip()

    if not query:
        print("No query entered. Exiting.")
        sys.exit(1)

    result, images = search_and_scrape_userguides(query, subscription_key)
    print("\n--- Extracted Content ---\n")
    print(result)
    print("\n--- Image URLs ---\n")
    for img_url in images:
        print(img_url)


if __name__ == "__main__":
    main()
