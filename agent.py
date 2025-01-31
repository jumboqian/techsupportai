import streamlit as st
import time
from openai import AzureOpenAI
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from html2text import HTML2Text
import json
from typing import Optional
# from bing_userguides import search_and_scrape_userguides
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration
BING_SUBSCRIPTION_KEY = os.getenv('BING_SUBSCRIPTION_KEY')
BING_CUSTOM_CONFIG_ID = os.getenv('BING_CUSTOM_CONFIG_ID')


def bing_custom_search(query, subscription_key=BING_SUBSCRIPTION_KEY, custom_config_id=BING_CUSTOM_CONFIG_ID):
    """Perform a Bing custom search and return the results"""
    base_url = "https://api.bing.microsoft.com/v7.0/custom/search"
    headers = {"Ocp-Apim-Subscription-Key": subscription_key}
    print(query)
    params = {
        "q": query,
        "customconfig": custom_config_id,
        "mkt": "en-US"
    }

    try:
        response = requests.get(base_url, headers=headers, params=params)
        response.raise_for_status()

        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error making search request: {e}")
        return None


def convert_html_to_markdown(html_content):
    """Convert HTML to formatted markdown text"""
    h = HTML2Text()
    h.body_width = 0
    h.ignore_links = False
    h.ignore_images = False
    h.ignore_tables = False
    return h.handle(str(html_content))


def scrape_article(url):
    """Scrape content from a Shure knowledge base article"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(url)

        wait = WebDriverWait(driver, 10)
        article = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "content")))

        time.sleep(5)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        article = soup.find('article', class_='content')

        if not article:
            return {"error": "Could not find article content"}

        content = extract_article_content(article)
        return content

    except Exception as e:
        return {"error": f"An error occurred while scraping: {str(e)}"}
    finally:
        driver.quit()


def extract_article_content(article):
    """Extract formatted content from article"""
    title_elem = article.find('span', class_='uiOutputText')
    title = title_elem.text if title_elem else "Title not found"

    rich_text_divs = article.find_all('div', {'class': 'slds-rich-text-editor__output'})

    question = rich_text_divs[0].get_text() if rich_text_divs else "Question not found"
    answer = rich_text_divs[1].get_text() if len(rich_text_divs) > 1 else "Answer not found"

    last_edit = article.find('span', class_='uiOutputDate')
    last_edit = last_edit.text if last_edit else "Date not found"

    return {
        "title": title,
        "question": question,
        "answer": answer,
        "last_edit_date": last_edit
    }


def search_and_get_content(product: str, problem: str) -> str:
    """Search documentation and user guides, returning formatted results"""
    # Construct search query
    query = f"{product} {problem}"
    
    # Search KB articles
    search_results = bing_custom_search(query)

    # try:
    #     guide_content, _ = search_and_scrape_userguides(product, BING_SUBSCRIPTION_KEY)
    #     content = []
    #     if guide_content:
    #         content.append("## From Product Manual\n\n")
    #         content.append(f"{guide_content}\n\n---\n\n")
    # except Exception as e:
    #     print(f"Error fetching user guide content: {e}")
    #     content = []
    

    if not search_results or "webPages" not in search_results:
        return "No results found for the query."

    # Display search results in the sidebar
    with st.sidebar:
        st.header("Technical Support FAQs")
        
        for idx, item in enumerate(search_results["webPages"]["value"][:5]):
            st.subheader(f"FaQ {idx + 1}")
            # Display the page title as a clickable link
            st.markdown(f"[{item['name']}]({item['url']})")
            # Display the snippet
            st.write(item["snippet"])
            st.divider()  # Add a visual separator between results

    content = []
    for idx, item in enumerate(search_results["webPages"]["value"][:2]):
        url = item["url"]
        if "service.shure.com" in url and "/article/" in url:
            article_data = scrape_article(url)
            if "error" not in article_data:
                content.append(f"## {article_data['title']}\n\n")
                content.append(f"**Question:** {article_data['question']}\n\n")
                content.append(f"**Answer:** {article_data['answer']}\n\n")
                content.append(f"*Last updated: {article_data['last_edit_date']}*\n\n")
                content.append(f"[Source]({url})\n\n---\n\n")

    print(f"✅ Scrape Content Complete")


    return "".join(content) if content else "No relevant articles found."


###################### Utility Functions
def poll_run_till_completion(
        client: AzureOpenAI,
        thread_id: str,
        run_id: str,
        available_functions: dict,
        verbose: bool,
        max_steps: int = 40,
        wait: float = 0.25,
) -> None:
    try:
        cnt = 0
        while cnt < max_steps:
            run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
            if verbose:
                print("Poll {}: {}".format(cnt, run.status))
            cnt += 1
            if run.status == "requires_action":
                tool_responses = []
                if (run.required_action.type == "submit_tool_outputs"
                        and run.required_action.submit_tool_outputs.tool_calls is not None):
                    tool_calls = run.required_action.submit_tool_outputs.tool_calls

                    for call in tool_calls:
                        if call.type == "function":
                            if call.function.name not in available_functions:
                                raise Exception("Function requested by the model does not exist")
                            function_to_call = available_functions[call.function.name]
                            tool_response = function_to_call(**json.loads(call.function.arguments))
                            tool_responses.append({"tool_call_id": call.id, "output": tool_response})

                run = client.beta.threads.runs.submit_tool_outputs(
                    thread_id=thread_id, run_id=run.id, tool_outputs=tool_responses
                )

            messages = retrieve_and_print_messages(client=client, thread_id=st.session_state.thread_id,
                                                   verbose=verbose_output)

            assistant_messages_for_run = [
                message for message in messages
                if message.run_id == run.id and message.role == "assistant"
            ]

            for message in reversed(assistant_messages_for_run):
                if message.content and len(message.content) > 0:
                    content = message.content[0].text.value if hasattr(message.content[0].text, 'value') else ''
                    st.session_state.messages.append({"role": "assistant", "content": content})
                    with st.chat_message("assistant"):
                        st.markdown(content)

            if run.status in ["failed", "completed"]:
                break
            time.sleep(wait)

    except Exception as e:
        print(e)


def retrieve_and_print_messages(
        client: AzureOpenAI, thread_id: str, verbose: bool, out_dir: Optional[str] = None
) -> any:
    if client is None and thread_id is None:
        return None
    try:
        messages = client.beta.threads.messages.list(thread_id=thread_id)
        return messages
    except Exception as e:
        print(e)
        return None


# Azure OpenAI Configuration
client = AzureOpenAI(
    azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),
    api_key=os.getenv('AZURE_OPENAI_API_KEY'),
    api_version="2024-03-01-preview"
)

# Available functions for the assistant
available_functions = {"search_documentation": search_and_get_content}
verbose_output = True

# Assistant Configuration
deployment_name = os.getenv('AZURE_OPENAI_DEPLOYMENT')
name = "shure-support-assistant"
instructions = """You are a customer support assistant for Shure's Products. When answering questions:
1. Identify the product and problem from the user's question
2. Use search_documentation with both the product and problem as separate parameters
3. Base your response on the retrieved information from both user guides and support articles
Always provide source URLs at the end. Important: use markdown format for the response"""


tools = [
    {
        "type": "function",
        "function": {
            "name": "search_documentation",
            "description": "Search Shure's documentation and user guides for product information and troubleshooting",
            "parameters": {
                "type": "object",
                "properties": {
                    "product": {
                        "type": "string",
                        "description": "The Shure product name or model",
                    },
                    "problem": {
                        "type": "string",
                        "description": "The specific issue or question about the product",
                    }
                },
                "required": ["product", "problem"],
            },
        },
    }
]

assistant = client.beta.assistants.create(
    name=name,
    description="Shure Customer Support Assistant",
    instructions=instructions,
    tools=tools,
    model=deployment_name
)



# Streamlit App
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
    # Create initial thread when app loads
    thread = client.beta.threads.create()
    st.session_state.thread_id = thread.id

st.set_page_config(page_title="Shure Support Assistant", page_icon=":headphones:")

# Display the Shure logo
st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/5/5d/Shure_Logo_2024.svg/2560px-Shure_Logo_2024.svg.png", width=300)


st.title("Shure Support Assistant")
st.write("Welcome! I'm here to help you with your Shure products. How can I assist you today?")

# New Chat button in sidebar
if st.sidebar.button("New Chat"):
    # Clear messages and create new thread
    st.session_state.messages = []
    thread = client.beta.threads.create()
    st.session_state.thread_id = thread.id
    st.rerun()  # Rerun the app to refresh the chat

# Initialize chat components
if "openai_model" not in st.session_state:
    st.session_state.openai_model = "gpt-4o"
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input and processing
if prompt := st.chat_input("How can I help you with your Shure product today?"):
    # Input Capture and Display
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👩‍🎨"):
        st.markdown(prompt)
    print("✅ User input captured and displayed")

    # Create Message in Thread
    client.beta.threads.messages.create(
        thread_id=st.session_state.thread_id,
        role="user",
        content=prompt
    )
    print(f"✅ Message added to thread {st.session_state.thread_id}")

    # Create and Start Run
    run = client.beta.threads.runs.create(
        thread_id=st.session_state.thread_id,
        assistant_id=assistant.id,
        instructions=instructions
    )
    print(f"✅ Run created with ID: {run.id}")

    # Process Response
    print("⏳ Starting response processing...")
    poll_run_till_completion(
        client=client,
        thread_id=st.session_state.thread_id,
        run_id=run.id,
        available_functions=available_functions,
        verbose=verbose_output
    )
    print("✅ Response processing completed")


