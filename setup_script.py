import os
import json
import getpass

# Step 1: Clone the repository
os.system("git clone https://github.com/luiscmartinez/selenium_phpBB_forum_mirror.git")

# Step 2: Navigate into the repository folder
repo_dir = "selenium_phpBB_forum_mirror"
os.chdir(repo_dir)

# Step 3: Edit the `login_config.json` file
config_data = {
    "login_url": "https://vutruhuyenbi.com/forum/ucp.php?mode=login",
    "base_url": "https://vutruhuyenbi.com/forum/",
    "username_selector": "#username",
    "password_selector": "#password",
    "username": "MillionGratitudes",
    "password": "",
    "login_button_selector": "button[type='submit']",
    "success_indicator": {
        "type": "element",
        "selector": "#message",
        "text_contains": "Bạn đã đăng nhập thành công vào hệ thống"
    }
}

# Prompt user for the password
password = getpass.getpass("Enter the password for the account: ")
config_data["password"] = password

# Write to `login_config.json`
with open("login_config.json", "w") as json_file:
    json.dump(config_data, json_file, indent=4, ensure_ascii=False)

print("Updated login_config.json with provided details.")

# Step 4: Install required dependencies
dependencies = [
    "sudo apt install python3-selenium -y",
    "sudo apt install python3-requests -y",
    "sudo apt install python3-bs4 -y"
]

for dependency in dependencies:
    os.system(dependency)

# Step 5: Run the `mirror_site.py` script
os.system("python3 mirror_site.py")

