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
from selenium.common.exceptions import TimeoutException # Add this import

class ForumMirror:
    def __init__(self, base_url, output_dir, login_config=None):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        self.output_dir = output_dir
        self.visited_urls = set()
        self.forum_sections = set()
        self.topics = set()
        self.login_config = login_config
        self.start_url = login_config.get("start_url", base_url) if login_config else base_url
        os.makedirs(self.output_dir, exist_ok=True)
        self.setup_logging()
        self.setup_driver()
        self.visited_urls_file = os.path.join(self.output_dir, "visited_urls.txt")

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

            username_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, self.login_config['username_selector']))
            )
            username_field.send_keys(self.login_config['username'])

            password_field = self.driver.find_element(By.CSS_SELECTOR, self.login_config['password_selector'])
            password_field.send_keys(self.login_config['password'])

            login_button = self.driver.find_element(By.CSS_SELECTOR, self.login_config['login_button_selector'])
            login_button.click()

            time.sleep(5) # Consider replacing with WebDriverWait for a specific condition after login

            # Pass page_source to check_login_success
            if self.check_login_success(self.driver.page_source):
                logging.info("Login successful")
                pickle.dump(self.driver.get_cookies(), open('cookies.pkl', 'wb'))
                return True
            else:
                logging.error("Login failed")
                return False

        except Exception as e:
            logging.error(f"Login error: {str(e)}")
            return False

    def check_login_success(self, page_source): # Modified to accept page_source
        if self.login_config["username"] in page_source:  
            print("Login successful!")
            return True
        else:
            print("Login failed!")
            return False


    def get_section_number(self, url):
        """Extract forum section number from URL"""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        return params.get('f', [None])[0]

    def is_topic_link(self, url):
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
            
            query = '&'.join(f"{k}={v}" for k, v in sorted(important_params.items()))
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
                    img_url = urljoin(self.base_url, img['src']) # Use self.base_url for broader context if needed, or current page's base
                    img_name = os.path.basename(urlparse(img_url).path) # Get a cleaner basename
                    if not img_name: # Handle cases where basename might be empty (e.g. /)
                        img_name = f"image_{hash(img_url)}.png" # Fallback name

                    img_path = os.path.join('assets', img_name)
                    full_img_path = os.path.join(self.output_dir, img_path) # Assets relative to output_dir
                    
                    os.makedirs(os.path.dirname(full_img_path), exist_ok=True)
                    
                    response = requests.get(img_url, stream=True)
                    response.raise_for_status()
                    with open(full_img_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    # Adjust relative path based on typical depth of HTML files
                    # e.g., forum/section_X/index.html or forum/section_X/topic_Y/page_Z.html
                    # This needs to be robust. If HTML is at output_dir/index.html, path is 'assets/...'
                    # If HTML is at output_dir/forum/section_X/index.html, path is '../../assets/...'
                    # We need to calculate depth from self.output_dir to the current HTML file's dir.
                    # For simplicity, assuming a common structure or making it configurable might be better.
                    # The previous '../../' assumed HTML files are two levels deep.
                    # Let's keep it simple for now, but this could be a point of refinement.
                    img['src'] = f'../../assets/{img_name}' # Adjusted to use self.output_dir/assets structure
                except requests.exceptions.RequestException as e:
                    logging.error(f"Failed to download image {img_url}: {e}")
                except Exception as e:
                    logging.error(f"Error processing image {img.get('src')}: {str(e)}")

        # Handle CSS
        for css in soup.find_all('link', rel='stylesheet'):
            if css.get('href'):
                try:
                    css_url = urljoin(self.base_url, css['href'])
                    css_name = os.path.basename(urlparse(css_url).path)
                    if not css_name:
                        css_name = f"style_{hash(css_url)}.css"

                    css_path = os.path.join('assets', css_name)
                    full_css_path = os.path.join(self.output_dir, css_path) # Assets relative to output_dir
                    
                    os.makedirs(os.path.dirname(full_css_path), exist_ok=True)
                    
                    response = requests.get(css_url, stream=True)
                    response.raise_for_status()
                    with open(full_css_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    css['href'] = f'../../assets/{css_name}' # Adjusted
                except requests.exceptions.RequestException as e:
                    logging.error(f"Failed to download CSS {css_url}: {e}")
                except Exception as e:
                    logging.error(f"Error processing CSS {css.get('href')}: {str(e)}")

    def _process_page_content(self, html_content, url_original):
        """Parses HTML content, saves it, and extracts new URLs in their original form."""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        output_file = self.create_directory_structure(url_original)
        # Pass the directory of the output_file to download_assets for correct relative path calculation if needed
        # For now, download_assets assumes assets are relative to self.output_dir and HTML paths are adjusted accordingly.
        self.download_assets(soup, os.path.dirname(output_file))
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(str(soup))
        
        new_urls_original_form = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('./'):
                href = href[2:]
            
            full_url_original = urljoin(url_original, href) # Use the original URL for resolving
            normalized_full_url = self.normalize_url(full_url_original) 
            
            if self.is_forum_section_link(normalized_full_url):
                section_num = self.get_section_number(normalized_full_url)
                # Check against self.forum_sections (which stores section_num)
                # to avoid adding duplicates if section already processed or known
                if section_num and section_num not in self.forum_sections:
                    # self.forum_sections.add(section_num) # Add when section is actually processed
                    new_urls_original_form.append(full_url_original) # Add original form
        
        return new_urls_original_form

    def mirror_page(self, url_original):
        normalized_url = self.normalize_url(url_original)
        if normalized_url in self.visited_urls:
            logging.info(f"Skipping already mirrored (normalized) page: {normalized_url} (original: {url_original})")
            return []

        logging.info(f"Mirroring page: {url_original} (normalized: {normalized_url})")

        try:
            self.driver.get(url_original) 
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(self.login_config.get("page_load_delay", 2))
            
            html_content = self.driver.page_source
            new_discovered_urls_original_form = self._process_page_content(html_content, url_original) 

            self.visited_urls.add(normalized_url)
            self.save_url_to_file(normalized_url)
            return new_discovered_urls_original_form

        except Exception as e:
            logging.error(f"Failed to mirror {url_original}: {str(e)}")
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

    def get_pagination_urls(self, soup, current_url_original):
        """Extracts pagination URLs in their original, fully-qualified form."""
        pagination_urls_original_form = set()
        pagination_ul = soup.find('ul', class_='pagination')
        if pagination_ul:
            for link in pagination_ul.find_all('a'):
                href = link.get('href')
                if href:
                    full_url_original = urljoin(current_url_original, href)
                    pagination_urls_original_form.add(full_url_original)
                
        return list(pagination_urls_original_form)

    def _process_topic_page_content(self, html_content, topic_url_original):
        """Parses topic HTML content, saves it, and extracts pagination URLs (original form)."""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        output_file = self.create_directory_structure(topic_url_original)
        self.download_assets(soup, os.path.dirname(output_file))
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(str(soup))
        
        pagination_urls_original = self.get_pagination_urls(soup, topic_url_original)
        return pagination_urls_original

    def mirror_topic(self, topic_url_original):
        """Fetches a topic page using Selenium, then processes its content."""
        normalized_topic_url = self.normalize_url(topic_url_original)
        if normalized_topic_url in self.visited_urls:
            logging.info(f"Skipping already mirrored (normalized) topic: {normalized_topic_url} (original: {topic_url_original})")
            return []

        logging.info(f"Mirroring topic: {topic_url_original} (normalized: {normalized_topic_url})")
        
        try:
            self.driver.get(topic_url_original)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(self.login_config.get("page_load_delay", 2))
            
            html_content = self.driver.page_source
            
            new_page_urls_original_form = self._process_topic_page_content(html_content, topic_url_original) 
            
            self.visited_urls.add(normalized_topic_url)
            self.save_url_to_file(normalized_topic_url)
            
            topic_num = self.get_topic_number(normalized_topic_url)
            if topic_num:
                 self.topics.add(topic_num)


            return new_page_urls_original_form

        except Exception as e:
            logging.error(f"Failed to mirror topic {topic_url_original}: {str(e)}")
            return []

    def _process_section_page_content(self, html_content, section_url_original):
        """Parses section HTML, saves it, extracts topic and pagination URLs (original form)."""
        soup = BeautifulSoup(html_content, 'html.parser')
        new_urls_original_form = []

        output_file = self.create_directory_structure(section_url_original)
        self.download_assets(soup, os.path.dirname(output_file))

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(str(soup))
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if href.startswith('./'): 
                href = href[2:]
            
            full_url_original = urljoin(section_url_original, href)
            normalized_full_url = self.normalize_url(full_url_original)

            if self.is_topic_link(normalized_full_url):
                # topic_num = self.get_topic_number(normalized_full_url) # topics are added when topic itself is mirrored
                new_urls_original_form.append(full_url_original)
        
        pagination_urls_original = self.get_pagination_urls(soup, section_url_original)
        new_urls_original_form.extend(pagination_urls_original)
        
        return new_urls_original_form

    def mirror_section(self, section_url_original):
        """Fetches a section page, handles locks, then processes content."""
        normalized_section_url = self.normalize_url(section_url_original)

        try:
            self.driver.get(section_url_original)
            WebDriverWait(self.driver, 3).until( # Short wait for login prompt
                EC.presence_of_element_located((By.ID, "login_forum"))
            )
            # If above doesn't raise TimeoutException, "login_forum" is present
            logging.info(f"Locked category detected at {section_url_original}, attempting to unlock...")
            password = self.login_config.get("forum_password")
            if not password:
                logging.error(f"No forum password for locked section {section_url_original}. Skipping.")
                return []
            
            password_input_el = self.driver.find_element(By.ID, "password")
            password_input_el.clear()
            password_input_el.send_keys(password)
            
            submit_btn = None
            submit_selectors = [
                (By.NAME, "login"), (By.CSS_SELECTOR, "input[type='submit']"), (By.ID, "load")
            ]
            for by_type, val in submit_selectors:
                try:
                    btn = self.driver.find_element(by_type, val)
                    if btn.is_displayed() and btn.is_enabled():
                        submit_btn = btn
                        break
                except:
                    continue
            
            if not submit_btn:
                logging.error(f"Submit button not found for locked section {section_url_original}. Skipping.")
                return []

            submit_btn.click()
            WebDriverWait(self.driver, 10).until(EC.staleness_of(password_input_el))
            logging.info(f"Forum password submitted for {section_url_original}.")

        except TimeoutException:
            logging.debug(f"'login_forum' prompt not found for {section_url_original}, proceeding.")
        except Exception as e:
            logging.error(f"Error during locked category handling for {section_url_original}: {e}. Skipping.")
            return []

        if normalized_section_url in self.visited_urls:
            logging.info(f"Skipping already mirrored (normalized) section: {normalized_section_url} (original: {section_url_original})")
            return []
       
        logging.info(f"Mirroring section: {section_url_original} (normalized: {normalized_section_url})")
        
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(self.login_config.get("page_load_delay", 2))
            
            html_content = self.driver.page_source
            new_discovered_urls_original_form = self._process_section_page_content(html_content, section_url_original) 
            
            self.visited_urls.add(normalized_section_url)
            self.save_url_to_file(normalized_section_url)
            
            section_num = self.get_section_number(normalized_section_url)
            if section_num:
                self.forum_sections.add(section_num)
            
            return new_discovered_urls_original_form
        except Exception as e:
            logging.error(f"Failed to mirror section {section_url_original} post-unlock: {e}")
            return []

    def is_forum_section_link(self, url): # Added back for completeness
        """Check if URL is a forum section link (can be normalized or original)."""
        parsed = urlparse(url)
        if parsed.path.endswith('viewforum.php'):
            params = parse_qs(parsed.query)
            return 'f' in params
        return False

    def load_cookies(self, cookie_file='cookies.pkl'):
        try:
            with open(cookie_file, 'rb') as f:
                cookies = pickle.load(f)
            self.driver.get(self.base_url)  # Open base URL before adding cookies
            for cookie in cookies:
                # Remove 'sameSite' if present, as it's not accepted by Selenium
                cookie.pop('sameSite', None)
                self.driver.add_cookie(cookie)
            logging.info("Cookies loaded successfully.")
            return True
        except Exception as e:
            logging.error(f"Failed to load cookies: {str(e)}")
            return False

    def mirror_forum(self, max_sections=None):
        try:
            cookies_loaded = False
            if os.path.exists('cookies.pkl'):
                self.driver.get(self.base_url) # Navigate to domain before loading cookies
                time.sleep(1) 
                cookies_loaded = self.load_cookies('cookies.pkl')
            
            if not cookies_loaded:
                if self.login_config and not self.perform_login():
                    logging.error("Failed to login. Aborting mirror process.")
                    self.driver.quit()
                    return

            queue = [self.start_url]  # Stores URLs in their original discovered form
            # queued_normalized_urls tracks normalized versions of URLs in queue or already processed by the loop
            # to prevent adding effectively duplicate URLs to the queue.
            queued_normalized_urls = {self.normalize_url(self.start_url)}
            
            sections_processed_count = 0

            while queue:
                current_url_original = queue.pop(0)
                
                # For type checking, use a normalized version, though our current checks are simple.
                # The mirror_* methods will handle the self.visited_urls check internally with normalized URLs.
                url_normalized_for_type_check = self.normalize_url(current_url_original)

                logging.info(f"Processing URL from queue: {current_url_original} (normalized: {url_normalized_for_type_check})")
                newly_discovered_urls_original_form = []
                
                processed_this_iteration = False
                if self.is_forum_section_link(url_normalized_for_type_check):
                    if max_sections and sections_processed_count >= max_sections:
                        logging.info(f"Max sections ({max_sections}) reached. Skipping further processing of new sections.")
                        # We still process other types of URLs or already queued sections.
                    else:
                        newly_discovered_urls_original_form = self.mirror_section(current_url_original)
                        # Check if the section was actually processed (i.e., its normalized form is now in visited_urls)
                        if self.normalize_url(current_url_original) in self.visited_urls:
                            # Check if this section number was newly added to self.forum_sections
                            # This is tricky as mirror_section adds it.
                            # A simpler way: if mirror_section didn't return empty due to already visited
                            # sections_processed_count is incremented when a section page is successfully mirrored.
                            # The mirror_section adds to self.forum_sections.
                            # We can count based on the size of self.forum_sections, but that's after the fact.
                            # Let's increment if mirror_section implies it processed a new section.
                            # The check `if self.normalize_url(current_url_original) in self.visited_urls:`
                            # after calling mirror_section confirms it was processed (or was already visited and skipped by the call).
                            # To count *newly processed* sections:
                            # initial_section_count = len(self.forum_sections)
                            # ... call mirror_section ...
                            # if len(self.forum_sections) > initial_section_count: sections_processed_count +=1
                            # This is more robust. Let's do it this way.
                            pass # section counting handled by checking self.visited_urls later
                        processed_this_iteration = True

                elif self.is_topic_link(url_normalized_for_type_check):
                    newly_discovered_urls_original_form = self.mirror_topic(current_url_original)
                    processed_this_iteration = True
                else:
                    newly_discovered_urls_original_form = self.mirror_page(current_url_original)
                    processed_this_iteration = True

                # Increment section count if a section URL was processed and added to visited_urls
                # This assumes mirror_section adds to self.visited_urls only upon successful processing
                if self.is_forum_section_link(url_normalized_for_type_check) and \
                   self.normalize_url(current_url_original) in self.visited_urls and \
                   (not max_sections or sections_processed_count < max_sections):
                    # To accurately count sections processed up to max_sections:
                    # We need to know if this specific section *became* visited in this iteration
                    # and wasn't already counted.
                    # The `self.forum_sections` set (which stores section numbers) is a good proxy.
                    # The sections_processed_count should ideally track unique sections processed.
                    # Let's use len(self.forum_sections) directly if max_sections is about unique sections.
                    # The current sections_processed_count is more like "attempts to process section URLs".
                    # For now, let's assume sections_processed_count tracks calls to mirror_section that weren't skipped by max_sections.
                    if processed_this_iteration and not (max_sections and sections_processed_count >= max_sections):
                         # This logic is a bit tangled. Let's simplify:
                         # sections_processed_count will be len(self.forum_sections) at the end.
                         # The max_sections check should be against len(self.forum_sections).
                        if self.is_forum_section_link(url_normalized_for_type_check):
                            current_section_num = self.get_section_number(url_normalized_for_type_check)
                            # Check if this section is newly processed for counting purposes
                            # This is complex because mirror_section adds to self.forum_sections
                            # Let's rely on mirror_section to add to self.forum_sections
                            # and check len(self.forum_sections) for the max_sections limit.
                            pass # Max section check refined below


                for new_url_original in newly_discovered_urls_original_form:
                    new_url_normalized = self.normalize_url(new_url_original)
                    if new_url_normalized not in self.visited_urls and \
                       new_url_normalized not in queued_normalized_urls:
                        
                        # Specific check for adding new sections if max_sections is active
                        if max_sections and self.is_forum_section_link(new_url_normalized) and \
                           len(self.forum_sections) >= max_sections:
                            # If this new URL is a section link, and we've already processed max_sections unique sections,
                            # and this new section is not one of those already processed (get_section_number not in self.forum_sections),
                            # then skip adding it.
                            sec_num_of_new_url = self.get_section_number(new_url_normalized)
                            if sec_num_of_new_url not in self.forum_sections:
                                logging.info(f"Max sections ({max_sections} unique) reached. Not queuing new section: {new_url_original}")
                                continue
                        
                        queue.append(new_url_original)
                        queued_normalized_urls.add(new_url_normalized)
                
                logging.info(f"Queue size: {len(queue)}, Visited (normalized): {len(self.visited_urls)}, Unique Sections: {len(self.forum_sections)}, Unique Topics: {len(self.topics)}")

        except Exception as e:
            logging.error(f"Mirror process failed: {str(e)}", exc_info=True)
        finally:
            self.driver.quit()
            logging.info(f"Mirroring complete. Processed {len(self.forum_sections)} unique sections and {len(self.topics)} unique topics.")
            logging.info(f"Total URLs visited (normalized): {len(self.visited_urls)}")

if __name__ == "__main__":
    # Load login configuration
    with open('login_config.json', 'r') as f:
        login_config = json.load(f)

    base_url = login_config['base_url']
    output_directory = "mirrored_forum"
    
    mirror = ForumMirror(base_url, output_directory, login_config=login_config)
    mirror.mirror_forum(max_sections=None)
