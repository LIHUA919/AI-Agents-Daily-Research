# -*- coding: utf-8 -*-
import arxiv
import requests
from bs4 import BeautifulSoup
import urllib3

# 屏蔽 SSL 警告
urllib3.disable_warnings()

# 创建 arxiv 客户端
client = arxiv.Client()

# 构建搜索请求
arxiv_search = arxiv.Search(
    query="AI Agents",
    max_results=5,
    sort_by=arxiv.SortCriterion.SubmittedDate
)

# paperswithcode API 获取代码地址
def get_paper_code_url(paper_id):
    base_url = "https://arxiv.paperswithcode.com/api/v0/papers/"
    code_url = base_url + paper_id 
    try:
        code_response = requests.get(code_url, verify=False).json()
        if "official" in code_response and code_response["official"]:
            github_code_url = code_response["official"]["url"]
            return github_code_url
    except:
        return None

# 解析 GitHub stars 数量
def get_stars(github_code_url):
    try:
        code_html = requests.get(github_code_url, verify=False)
        soup = BeautifulSoup(code_html.text, "html.parser")
        a_tags = soup.find_all("a", href=lambda x: x and x.endswith("/stargazers"))
        if a_tags:
            stars = a_tags[0].text.strip().replace(",", "")
            return stars
    except:
        pass
    return "0"

# 遍历查询结果
for result in client.results(arxiv_search):
    paper_id = result.get_short_id()
    paper_title = result.title
    paper_url = result.entry_id
    paper_summary = result.summary.replace("\n", "")
    paper_first_author = result.authors[0]
    publish_time = result.published.date()
    update_time = result.updated.date()

    github_code_url = get_paper_code_url(paper_id)
    stars = get_stars(github_code_url) if github_code_url else "N/A"

    print(f"[{paper_id}] {paper_title}")
    print(f"  📎 URL: {paper_url}")
    print(f"  🧑 Author: {paper_first_author}")
    print(f"  🗓️ Published: {publish_time}, Updated: {update_time}")
    print(f"  🔍 Summary: {paper_summary[:100]}...")
    print(f"  🧑‍💻 Code: {github_code_url or 'Not found'}")
    print(f"  ⭐ Stars: {stars}")
    print("-" * 100)


import datetime
import requests
import json
import arxiv
import os
def get_authors(authors, first_author = False):
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

def get_daily_papers(topic,query="slam", max_results=2):
    """
    @param topic: str
    @param query: str
    @return paper_with_code: dict
    """

    # output 
    content = dict() 
    
    search_engine = arxiv.Search(
        query = query,
        max_results = max_results,
        sort_by = arxiv.SortCriterion.SubmittedDate
    )

    for result in search_engine.results():

        paper_id       = result.get_short_id()
        paper_title    = result.title
        paper_url      = result.entry_id

        paper_abstract = result.summary.replace("\n"," ")
        paper_authors  = get_authors(result.authors)
        paper_first_author = get_authors(result.authors,first_author = True)
        primary_category = result.primary_category

        publish_time = result.published.date()

        print("Time = ", publish_time ,
              " title = ", paper_title,
              " author = ", paper_first_author)

        # eg: 2108.09112v1 -> 2108.09112
        ver_pos = paper_id.find('v')
        if ver_pos == -1:
            paper_key = paper_id
        else:
            paper_key = paper_id[0:ver_pos] 

        content[paper_key] = f"|**{publish_time}**|**{paper_title}**|{paper_first_author} et.al.|[{paper_id}]({paper_url})|\n"
    data = {topic:content}
    
    return data 

def update_json_file(filename,data_all):
    with open(filename,"r") as f:
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

    with open(filename,"w") as f:
        json.dump(json_data,f)
    
def json_to_md(filename):
    """
    @param filename: str
    @return None
    """
    
    DateNow = datetime.date.today()
    DateNow = str(DateNow)
    DateNow = DateNow.replace('-','.')
    
    with open(filename,"r") as f:
        content = f.read()
        if not content:
            data = {}
        else:
            data = json.loads(content)

    md_filename = "README.md"  
      
    # clean README.md if daily already exist else create it
    with open(md_filename,"w+") as f:
        pass

    # write data into README.md
    with open(md_filename,"a+") as f:
  
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
        
            for _,v in day_content.items():
                if v is not None:
                    f.write(v)

            f.write(f"\n")
    print("finished")     

if __name__ == "__main__":

    data_collector = []
    keywords = dict()
    keywords["SLAM"] = "SLAM"
 
    for topic,keyword in keywords.items():
 
        print("Keyword: " + topic)
        data = get_daily_papers(topic, query = keyword, max_results = 10)
        data_collector.append(data)
        print("\n")

    # update README.md file
    json_file = "cv-arxiv-daily.json"
    if ~os.path.exists(json_file):
        with open(json_file,'w')as a:
            print("create " + json_file)
    # update json data
    update_json_file(json_file,data_collector)
    # json data to markdown
    json_to_md(json_file)
