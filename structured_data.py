import os
import json
import re
from bs4 import BeautifulSoup

def process_html_file(file_path):
    """
    Processes an individual HTML file to extract posts and replies.
    :param file_path: Path to the HTML file
    :return: A list of dictionaries with structured data for each post
    """
    data = []
    
    with open(file_path, 'r', encoding='utf-8') as file:
        soup = BeautifulSoup(file, 'html.parser')
        match = re.search(r'topic_(\d+)', file_path)
        if match:
            topic_id = match.group(1)
            print(f"Topic Number: {topic_id}")
        else:
            print("Topic number not found.")

        topic_title = soup.head.title.text if soup.head and soup.head.title else 'No Title'
        print(f"Topic Title: {topic_title}")


        # Example extraction logic for posts and replies
        posts = soup.find_all('article', role='article')  # Adjust based on actual HTML structure
        for post in posts:
            # Find the parent div with class 'clearfix'
            parent_div = post.find_parent('div', class_='clearfix')

            if parent_div and parent_div.has_attr('id'):
                post_id = parent_div['id']  # Get the id attribute of the parent div
                print(f"post ID: {post_id}")
            else:
                print("Parent div with class 'clearfix' or id attribute not found.")

            panelHeading = post.find('div', class_='panel-heading') 
            panelBody = post.find('div', class_='panel-body')
            # Assuming `element` contains the parsed HTML of the div with class "panel-heading"
            post_title = panelHeading.find('h3').find('a').text
            post_author = panelHeading.find('a', class_='username-coloured')  # Try finding in <a> tag first

            # If <a> tag is not found, look for <span> with class "username-coloured"
            if post_author is None:
                post_author = panelHeading.find('span', class_='username-coloured')

            # Extract the text if the tag was found
            post_author = post_author.text.strip() if post_author else "Author not found"

            timestamp = panelHeading.find('span', class_='hidden-xs').text.strip()
            # content = panelBody.find('div', class_='content').text.strip()
            content_div = panelBody.find('div', class_='content')
            content_text = ' '.join(content_div.stripped_strings)
            content_text = re.sub(r"- (Thứ \d|Chủ nhật) Tháng \d{1,2} \d{2}, \d{4} \d{1,2}:\d{2} (am|pm)", "", content_text).strip()
            print(content_text)
            print("POST TITLE: ")
            print(post_title)
            print(timestamp)
            print(post_author)
            data.append({
                'topic_id': topic_id,
                'topic_title': topic_title,
                'post_id': post_id,
                'post_title': post_title,
                'author': post_author,
                'content': content_text,
                'timestamp': timestamp,
            })
    return data

def process_nested_directories(target_directory):
    """
    Iterates through all nested directories to find HTML files and process them.
    :param target_directory: The top-level directory containing HTML files in nested folders
    :return: A list of all extracted posts and replies across all HTML files
    """
    all_data = []

    # Traverse the entire directory structure
    for root, dirs, files in os.walk(target_directory):
        for file in files:
            print("the file inside of files is: ")
            print(file)
            if file.endswith(".html"):  # Only process HTML files
                file_path = os.path.join(root, file)
                print(f"Processing file: {file_path}")
                file_data = process_html_file(file_path)  # Process each found HTML file
                all_data.extend(file_data)  # Add each file's data to the main list

    return all_data

def save_to_json(data, output_file='structured_data.json'):
    """
    Saves extracted data to a JSON file.
    :param data: List of dictionaries containing structured data
    :param output_file: Name of the output JSON file
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"Data saved to {output_file}")

# Main execution
if __name__ == "__main__":
    # Path to your main directory
    target_directory = './mirrored_forum/forum'
    
    # Process directories and save results
    extracted_data = process_nested_directories(target_directory)
    save_to_json(extracted_data)
