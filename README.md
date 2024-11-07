# phpBB Forum Mirrorer

phpBB Forum Mirrorer is a Python tool that downloads and locally mirrors entire online forums, including forum sections, topics, and pages. This tool uses Selenium to interact with pages that may require login and dynamically load content, making it versatile for mirroring interactive forums.

## Features

- **Full Forum Mirroring**: Mirrors all sections, topics, and paginated pages.
- **Local Cache Checking**: Avoids redundant requests by checking locally saved files before downloading.
- **Login Support**: Supports logging in to forums with credentials to access restricted content.
- **Asset Downloading**: Saves images and CSS for offline viewing.
- **Normalization of URLs**: Ensures each unique URL is processed only once, avoiding duplicate downloads.

## Requirements

- Python 3.7 or later
- Google Chrome
- ChromeDriver
- The following Python packages:
  - `selenium`
  - `requests`
  - `beautifulsoup4`

## Installation

1. **Clone the repository**:
    ```bash
    git clone https://github.com/luiscmartinez/selenium_phpBB_forum_mirror.git
    cd selenium_phpBB_forum_mirror
    ```

2. **Install required Python packages**:
    ```bash
    pip install -r requirements.txt
    ```


## Configuration

### Login Configuration

If the forum requires login, create a `login_config.json` file in the project directory. Configure it with the necessary selectors and credentials:

```json
{
    "login_url": "https://exampleforum.com/login",
    "base_url": "https://exampleforum.com/forum/",
    "username_selector": "#username",
    "password_selector": "#password",
    "login_button_selector": "#loginButton",
    "username": "your_username",
    "password": "your_password"
}
```

Directory Structure
By default, mirrored content will be saved in the mirrored_forum directory, structured by sections and topics, making it easy to navigate offline.

## Usage
Run the script with the following command:

bash
`python3 mirror_site.py`

## Code Overview

### `ForumMirror` Class

- **`mirror_forum`**: Entry point for mirroring the forum, manages the queue of URLs.
- **`mirror_section`**: Mirrors a forum section and retrieves all topics within it.
- **`mirror_topic`**: Mirrors an entire topic, including paginated pages.
- **`mirror_page`**: Mirrors a general page if it doesn't match a section or topic pattern.
- **`download_assets`**: Downloads images and CSS linked on each page for offline access.
- **`normalize_url`**: Ensures URLs are consistent to avoid duplicate requests.

## Logs

- Logging output is saved in `forum_mirror.log`. The log provides detailed information on mirroring progress, including any errors encountered during requests.

## Known Issues

- **Rate Limiting**: Some forums may limit access if requests are too frequent. Adjust the `time.sleep()` intervals if this becomes an issue.
- **CSS and JavaScript Assets**: Currently only CSS files are downloaded, which may affect some JavaScript-heavy pages.
- **Login Check**: A generic `check_login_success` method is provided; further customization may be needed for forums with unique login success indicators.
