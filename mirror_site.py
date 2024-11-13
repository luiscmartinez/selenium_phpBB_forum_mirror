from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urljoin, urlparse, parse_qs, urlunparse

import os
import time
import requests
from bs4 import BeautifulSoup
import logging
import pickle
import json
import re

class ForumMirror:
    def __init__(self, base_url, output_dir, login_config=None):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        self.output_dir = output_dir
        self.visited_urls = set()
        self.forum_sections = set()  # Track forum section numbers
        self.topics = set()  # Track topic numbers
        self.login_config = login_config
        os.makedirs(self.output_dir, exist_ok=True)  # Ensure output directory exists
        self.setup_logging()
        self.setup_driver()
        # Create the file for storing visited URLs
        self.visited_urls_file = os.path.join(self.output_dir, "visited_urls.txt")
        with open(self.visited_urls_file, 'w') as f:
            f.write("Visited URLs:\n")

    def save_url_to_file(self, url):
        """Save each visited URL to a file."""
        with open(self.visited_urls_file, 'a') as f:
            f.write(url + '\n')

    def setup_logging(self):
        logging.basicConfig(
            filename='forum_mirror.log',
            level=logging.DEBUG,  # Set to DEBUG level for detailed output
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    def setup_driver(self):
        chrome_options = Options()
        # chrome_options.add_argument('--headless')  # Uncomment for headless mode
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')
        self.driver = webdriver.Chrome(options=chrome_options)

    def perform_login(self):
        if not self.login_config:
            logging.warning("No login configuration provided")
            return False

        try:
            self.driver.get(self.login_config['login_url'])
            logging.info("Navigating to login page")
            time.sleep(3)

            # Check for existing cookies
            if os.path.exists('cookies.pkl'):
                cookies = pickle.load(open('cookies.pkl', 'rb'))
                for cookie in cookies:
                    try:
                        self.driver.add_cookie(cookie)
                    except Exception as e:
                        logging.error(f"Error loading cookie: {str(e)}")
                self.driver.refresh()
                time.sleep(3)
                
                if self.check_login_success():
                    logging.info("Successfully logged in using cookies")
                    return True

            # Perform login
            username_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, self.login_config['username_selector']))
            )
            username_field.send_keys(self.login_config['username'])

            password_field = self.driver.find_element(By.CSS_SELECTOR, self.login_config['password_selector'])
            password_field.send_keys(self.login_config['password'])

            login_button = self.driver.find_element(By.CSS_SELECTOR, self.login_config['login_button_selector'])
            login_button.click()

            time.sleep(5)

            if self.check_login_success():
                logging.info("Login successful")
                pickle.dump(self.driver.get_cookies(), open('cookies.pkl', 'wb'))
                return True
            else:
                logging.error("Login failed")
                return False

        except Exception as e:
            logging.error(f"Login error: {str(e)}")
            return False

    def check_login_success(self):
        print("Checking login success status")
        if self.login_config["username"] in self.driver.page_source:
            print("Login successful!")
            return True
        else:
            print("Login failed!")
            return False

    def is_forum_section_link(self, url):
        """Check if URL is a forum section link"""
        parsed = urlparse(url)
        if parsed.path.endswith('viewforum.php'):
            params = parse_qs(parsed.query)
            return 'f' in params
        return False

    def get_section_number(self, url):
        """Extract forum section number from URL"""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        return params.get('f', [None])[0]

    def is_topic_link(self, url):
        """Check if URL is a topic link"""
        parsed = urlparse(url)
        return parsed.path.endswith('viewtopic.php') and 't' in parse_qs(parsed.query)

    def normalize_url(self, url):
        """
        Normalize a URL to avoid duplicates by:
        - Converting to lowercase
        - Removing trailing slashes
        - Sorting query parameters
        - Removing unnecessary parameters
        - Handling relative URLs
        """
        try:
            # Parse the URL
            parsed = urlparse(url)
            
            # Handle relative URLs
            if not parsed.netloc:
                url = urljoin(self.base_url, url)
                parsed = urlparse(url)
            
            # Get the query parameters
            params = parse_qs(parsed.query)
            
            # Keep only necessary parameters
            important_params = {}
            
            # For forum sections, keep 'f'
            if self.is_forum_section_link(url):
                if 'f' in params:
                    important_params['f'] = params['f'][0]
            
            # For topics, keep 'f', 't', and 'start'
            elif self.is_topic_link(url):
                if 'f' in params:
                    important_params['f'] = params['f'][0]
                if 't' in params:
                    important_params['t'] = params['t'][0]
                if 'start' in params:
                    important_params['start'] = params['start'][0]
            
            # Reconstruct query string with sorted parameters
            query = '&'.join(f"{k}={v}" for k, v in sorted(important_params.items()))
            # Reconstruct the URL
            normalized = urlunparse((
                parsed.scheme,
                parsed.netloc.lower(),
                parsed.path.rstrip('/'),
                '',
                query,
                ''
            ))
            logging.debug(f"Normalized URL: {normalized}")
            return normalized
        
        except Exception as e:
            logging.error(f"Error normalizing URL {url}: {str(e)}")
            return url

    def download_assets(self, soup, base_folder):
        """Download and update paths for images, CSS, and other assets"""
        # Handle images
        for img in soup.find_all('img'):
            if img.get('src'):
                try:
                    img_url = urljoin(self.base_url, img['src'])
                    img_path = os.path.join('assets', os.path.basename(img_url))
                    full_img_path = os.path.join(base_folder, img_path)
                    
                    os.makedirs(os.path.dirname(full_img_path), exist_ok=True)
                    
                    response = requests.get(img_url)
                    with open(full_img_path, 'wb') as f:
                        f.write(response.content)
                    
                    img['src'] = f'../../{img_path}'
                except Exception as e:
                    logging.error(f"Failed to download image {img_url}: {str(e)}")

        # Handle CSS
        for css in soup.find_all('link', rel='stylesheet'):
            if css.get('href'):
                try:
                    css_url = urljoin(self.base_url, css['href'])
                    css_path = os.path.join('assets', os.path.basename(css_url))
                    full_css_path = os.path.join(base_folder, css_path)
                    
                    os.makedirs(os.path.dirname(full_css_path), exist_ok=True)
                    
                    response = requests.get(css_url)
                    with open(full_css_path, 'wb') as f:
                        f.write(response.content)
                    
                    css['href'] = f'../../{css_path}'
                except Exception as e:
                    logging.error(f"Failed to download CSS {css_url}: {str(e)}")

    def mirror_page(self, url):
        if url in self.visited_urls:
            return []

        self.visited_urls.add(url)
        self.save_url_to_file(url)  # Save the URL to file
        logging.info(f"Mirroring page: {url}")

        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(2)
            
            html_content = self.driver.page_source
            soup = BeautifulSoup(html_content, 'html.parser')
            
            output_file = self.create_directory_structure(url)
            self.download_assets(soup, self.output_dir)
            
            # Save the HTML
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            
            # Find forum section links
            new_urls = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('./'):
                    href = href[2:]  # Remove leading ./
                full_url = urljoin(url, href)
                if self.is_forum_section_link(full_url):
                    section_num = self.get_section_number(full_url)
                    if section_num and section_num not in self.forum_sections:
                        self.forum_sections.add(section_num)
                        new_urls.append(full_url)
            
            return new_urls

        except Exception as e:
            logging.error(f"Failed to mirror {url}: {str(e)}")
            return []

    def get_topic_number(self, url):
        """Extract topic number from URL"""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        return params.get('t', [None])[0]

    def create_directory_structure(self, url):
        """Create appropriate directory structure for saving files"""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        
        if parsed.path.endswith('viewforum.php') and 'f' in params:
            section_num = params['f'][0]
            path = f'forum/section_{section_num}/index.html'
        elif parsed.path.endswith('viewtopic.php') and 't' in params:
            topic_num = params['t'][0]
            section_num = params.get('f', ['unknown'])[0]
            start_param = params.get('start', ['0'])[0]
            path = f'forum/section_{section_num}/topic_{topic_num}/page_{start_param}.html'
        else:
            path = parsed.path.lstrip('/')
            if not path:
                path = 'index.html'
            elif not path.endswith('.html'):
                path = os.path.join(path, 'index.html')

        full_path = os.path.join(self.output_dir, path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        return full_path

    def get_pagination_urls(self, soup, current_url):
        """Extract pagination URLs from the page"""
        pagination_urls = set()
        
        for link in soup.find('ul', class_='pagination').find_all('a'):
            href = link.get('href')
            if href:
                full_url = urljoin(current_url, href)
                pagination_urls.add(self.normalize_url(full_url))
                
        return list(pagination_urls)

    def mirror_topic(self, topic_url):
        """Mirror an entire topic including all its pages"""
        if topic_url in self.visited_urls:
            return []

        logging.info(f"Mirroring topic: {topic_url}")
        new_urls = []

        try:
            self.driver.get(topic_url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(2)
            
            html_content = self.driver.page_source
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Save the current page
            output_file = self.create_directory_structure(topic_url)
            self.download_assets(soup, self.output_dir)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            
            self.visited_urls.add(topic_url)
            
            # Get pagination URLs
            pagination_urls = self.get_pagination_urls(soup, topic_url)
            new_urls.extend(pagination_urls)
            
            return new_urls

        except Exception as e:
            logging.error(f"Failed to mirror topic {topic_url}: {str(e)}")
            return []

    def mirror_section(self, section_url):
        """Mirror an entire forum section including all topics"""
        if section_url in self.visited_urls:
            return []

        logging.info(f"Mirroring section: {section_url}")
        new_urls = []

        try:
            self.driver.get(section_url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(2)
            
            html_content = self.driver.page_source
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Save the current page
            output_file = self.create_directory_structure(section_url)
            self.download_assets(soup, self.output_dir)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            
            self.visited_urls.add(section_url)
            
            # Find all topic links
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('./'):
                    href = href[2:]
                full_url = urljoin(section_url, href)
                
                if self.is_topic_link(full_url):
                    topic_num = self.get_topic_number(full_url)
                    if topic_num and topic_num not in self.topics:
                        self.topics.add(topic_num)
                        new_urls.append(full_url)
            
            # Get pagination URLs for the section
            pagination_urls = self.get_pagination_urls(soup, section_url)
            new_urls.extend(pagination_urls)
            
            return new_urls

        except Exception as e:
            logging.error(f"Failed to mirror section {section_url}: {str(e)}")
            return []

    def mirror_forum(self, max_sections=None):
        try:
            if self.login_config and not self.perform_login():
                logging.error("Failed to login. Aborting mirror process.")
                return

            urls_to_visit = [self.base_url]
            sections_processed = 0

            while urls_to_visit:
                url = urls_to_visit.pop(0)
                
                if self.is_forum_section_link(url):
                    if max_sections and sections_processed >= max_sections:
                        break
                    new_urls = self.mirror_section(url)
                    sections_processed += 1
                elif self.is_topic_link(url):
                    new_urls = self.mirror_topic(url)
                else:
                    new_urls = self.mirror_page(url)
                
                # Ensure new URLs are not already visited
                urls_to_visit.extend([u for u in new_urls if u not in self.visited_urls])
                logging.info(f"Queue size: {len(urls_to_visit)}, Visited: {len(self.visited_urls)}")

        except Exception as e:
            logging.error(f"Mirror process failed: {str(e)}")
        finally:
            self.driver.quit()
            logging.info(f"Mirroring complete. Processed {len(self.forum_sections)} sections and {len(self.topics)} topics")

if __name__ == "__main__":
    # Load login configuration
    with open('login_config.json', 'r') as f:
        login_config = json.load(f)

    base_url = login_config['base_url'] 
    output_directory = "mirrored_forum"
    
    mirror = ForumMirror(base_url, output_directory, login_config=login_config)
    mirror.mirror_forum(max_sections=None)
