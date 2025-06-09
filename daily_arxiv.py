# -*- coding: utf-8 -*-
import arxiv
import requests
from bs4 import BeautifulSoup
import urllib3
import time
import random # 引入 random 用于 jitter
import datetime
import json
import os

# 屏蔽 SSL 警告 (虽然方便调试，但在生产环境中应尽量避免，除非你明确知道风险并接受)
urllib3.disable_warnings()

# --- 通用重试装饰器 ---
def retry_on_connection_error(max_retries=5, initial_delay=5):
    """
    一个装饰器，用于在 ConnectionError 发生时重试函数。
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            attempt = 0
            while attempt < max_retries:
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.ConnectionError as e:
                    attempt += 1
                    print(f"ConnectionError occurred in {func.__name__}: {e}. Attempt {attempt}/{max_retries}.")
                    if attempt < max_retries:
                        # 指数退避加抖动 (exponential backoff with jitter)
                        wait_time = initial_delay * (2 ** (attempt - 1)) + (random.random() * 2)
                        print(f"Retrying {func.__name__} in {wait_time:.2f} seconds...")
                        time.sleep(wait_time)
                    else:
                        print(f"Max retries reached for {func.__name__}. Giving up.")
                        raise # 重新抛出异常，让调用者知道最终失败了
                except Exception as e:
                    # 捕获其他非 ConnectionError 的异常并直接抛出
                    print(f"An unexpected error occurred in {func.__name__}: {e}")
                    raise
        return wrapper
    return decorator

# 创建 arxiv 客户端
# 增加延迟，对服务器更友好，并降低被重置的风险
client = arxiv.Client(delay_seconds=3.0)

# paperswithcode API 获取代码地址
@retry_on_connection_error(max_retries=3, initial_delay=2) # 对此函数也应用重试
def get_paper_code_url(paper_id):
    base_url = "https://arxiv.paperswithcode.com/api/v0/papers/"
    code_url = base_url + paper_id
    try:
        # verify=False 应该只用于调试，生产环境建议设置为 True 并处理 SSL 证书问题
        code_response = requests.get(code_url, verify=False, timeout=10).json() # 增加超时
        if "official" in code_response and code_response["official"]:
            github_code_url = code_response["official"]["url"]
            return github_code_url
    except requests.exceptions.Timeout:
        print(f"Timeout when fetching code for {paper_id}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Request error for code for {paper_id}: {e}")
        return None
    except json.JSONDecodeError:
        print(f"JSON decode error for code for {paper_id}. Response was not valid JSON.")
        return None
    except Exception as e: # 捕获其他潜在错误
        print(f"An unexpected error occurred in get_paper_code_url for {paper_id}: {e}")
    return None

# 解析 GitHub stars 数量
@retry_on_connection_error(max_retries=3, initial_delay=2) # 对此函数也应用重试
def get_stars(github_code_url):
    try:
        # verify=False 应该只用于调试，生产环境建议设置为 True
        code_html = requests.get(github_code_url, verify=False, timeout=10) # 增加超时
        code_html.raise_for_status() # 检查HTTP请求是否成功
        soup = BeautifulSoup(code_html.text, "html.parser")
        a_tags = soup.find_all("a", href=lambda x: x and x.endswith("/stargazers"))
        if a_tags:
            stars = a_tags[0].text.strip().replace(",", "")
            return stars
    except requests.exceptions.Timeout:
        print(f"Timeout when fetching stars for {github_code_url}")
    except requests.exceptions.RequestException as e: # 更广泛地捕获requests库的异常
        print(f"Request error for stars for {github_code_url}: {e}")
    except Exception as e: # 捕获其他潜在错误
        print(f"An unexpected error occurred in get_stars for {github_code_url}: {e}")
    return "0"


# --- 你的辅助函数保持不变 ---
def get_authors(authors, first_author=False):
    output = str()
    if first_author == False:
        output = ", ".join(str(author) for author in authors)
    else:
        output = authors[0]
    return output

def sort_papers(papers):
    output = dict()
    keys = list(papers.keys())
    keys.sort(reverse=True)
    for key in keys:
        output[key] = papers[key]
    return output

@retry_on_connection_error(max_retries=5, initial_delay=5) # 对获取每日论文的函数也应用重试
def get_daily_papers(topic, query="slam", max_results=2):
    """
    @param topic: str
    @param query: str
    @return paper_with_code: dict
    """

    content = dict()

    # 使用全局的 client 对象，或者在这里重新创建，但要确保有 delay_seconds
    search_engine = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate
    )

    for result in client.results(search_engine): # 直接使用全局 client 对象
        paper_id = result.get_short_id()
        paper_title = result.title
        paper_url = result.entry_id

        paper_abstract = result.summary.replace("\n", " ")
        paper_authors = get_authors(result.authors)
        paper_first_author = get_authors(result.authors, first_author=True)
        primary_category = result.primary_category

        publish_time = result.published.date()

        print("Time = ", publish_time,
              " title = ", paper_title,
              " author = ", paper_first_author)

        # eg: 2108.09112v1 -> 2108.09112
        ver_pos = paper_id.find('v')
        if ver_pos == -1:
            paper_key = paper_id
        else:
            paper_key = paper_id[0:ver_pos]

        content[paper_key] = f"|**{publish_time}**|**{paper_title}**|{paper_first_author} et.al.|[{paper_id}]({paper_url})|\n"
    data = {topic: content}

    return data

def update_json_file(filename, data_all):
    with open(filename, "r") as f:
        content = f.read()
        if not content:
            m = {}
        else:
            m = json.loads(content)

    json_data = m.copy()

    # update papers in each keywords
    for data in data_all:
        for keyword in data.keys():
            papers = data[keyword]

            if keyword in json_data.keys():
                json_data[keyword].update(papers)
            else:
                json_data[keyword] = papers

    with open(filename, "w") as f:
        json.dump(json_data, f, indent=4, ensure_ascii=False) # 增加indent和ensure_ascii=False，使json更易读

def json_to_md(filename):
    """
    @param filename: str
    @return None
    """

    DateNow = datetime.date.today()
    DateNow = str(DateNow)
    DateNow = DateNow.replace('-', '.')

    with open(filename, "r") as f:
        content = f.read()
        if not content:
            data = {}
        else:
            data = json.loads(content)

    md_filename = "README.md"

    # clean README.md if daily already exist else create it
    # 注意：这里是清空 README.md，如果你想追加内容，需要修改逻辑
    with open(md_filename, "w+") as f:
        pass

    # write data into README.md
    with open(md_filename, "a+", encoding='utf-8') as f: # 确保以utf-8编码写入
        f.write("## Updated on " + DateNow + "\n\n")

        for keyword in data.keys():
            day_content = data[keyword]
            if not day_content:
                continue
            # the head of each part
            f.write(f"## {keyword}\n\n")
            f.write("|Publish Date|Title|Authors|PDF|\n" + "|---|---|---|---|\n")
            # sort papers by date
            day_content = sort_papers(day_content)

            for _, v in day_content.items():
                if v is not None:
                    f.write(v)

            f.write(f"\n")
    print("finished writing to README.md")

if __name__ == "__main__":
    data_collector = []
    keywords = dict()
    # 你的原代码中只有一个 keywords["SLAM"] = "SLAM"
    # 如果你想搜索 "AI Agents"，你需要把它也加入到 keywords 字典中
    # 比如：
    keywords["AI Agents"] = "AI Agents"
    keywords["SLAM"] = "SLAM" # 如果你还想保留 SLAM

    # 检查 cv-arxiv-daily.json 文件是否存在，不存在则创建
    json_file = "cv-arxiv-daily.json"
    if not os.path.exists(json_file): # ~os.path.exists 是错误的写法，应该是 not os.path.exists
        with open(json_file,'w', encoding='utf-8') as f: # 确保以utf-8编码创建
            f.write("{}") # 初始化为空JSON对象
        print("Created " + json_file)

    try:
        for topic, keyword in keywords.items():
            print(f"Collecting papers for Keyword: {topic} (query: {keyword})")
            # 调用带重试逻辑的 get_daily_papers
            data = get_daily_papers(topic, query=keyword, max_results=10)
            data_collector.append(data)
            print("\n")

        # 更新 json data
        update_json_file(json_file, data_collector)
        print("JSON file updated successfully.")

        # json data to markdown
        json_to_md(json_file)

        print("Script finished successfully.")
    except Exception as main_e:
        print(f"An error occurred during the main script execution: {main_e}")
        exit(1) # 如果主流程失败，则以错误代码退出
