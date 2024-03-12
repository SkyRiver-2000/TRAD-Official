from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores import FAISS
import time
from lxml import etree
from typing import Tuple, List

from envs.env_utils import get_target_obs

def get_top_k_obs(s: dict, top_k: int) -> Tuple[str, str]:
    pos_candidates = s["pos_candidates"]
    pos_ids = [c["backend_node_id"] for c in pos_candidates]
    neg_candidates = s["neg_candidates"]
    neg_candidates = [c for c in neg_candidates if c["rank"] < top_k]
    neg_ids = [c["backend_node_id"] for c in neg_candidates]
    all_candidates = pos_ids + neg_ids
    obs = get_target_obs(etree.fromstring(s["cleaned_html"]), all_candidates)
    if len(s["pos_candidates"]) == 0:
        # Simplify the raw_html if pos_candidates is empty (not in the cleaned html)
        dom_tree = etree.fromstring(s["raw_html"])
        gt_element = dom_tree.xpath(f"//*[@data_pw_testid_buckeye='{s['action_uid']}']")
        element_id = gt_element[0].get("backend_node_id")
        raw_obs = get_target_obs(dom_tree, [element_id])
        # Find the start index of the target element using the element ID
        start_idx = raw_obs.find(f"id={element_id}")
        # Find the start tag for the target element
        start_tag_idx = raw_obs.rfind("<", 0, start_idx)
        end_tag_idx = raw_obs.find(">", start_idx)
        # Extract the tag name
        tag_name = raw_obs[start_tag_idx + 1 : end_tag_idx].split()[0]
        # Initialize count for open and close tags
        open_count = 0
        close_count = 0
        search_idx = start_tag_idx
        while True:
            # Find the next open or close tag of the same type
            next_open_tag = raw_obs.find(f"<{tag_name}", search_idx)
            next_close_tag = raw_obs.find(f"</{tag_name}>", search_idx)
            # No more tags found, break
            if next_open_tag == -1 and next_close_tag == -1:
                break
            # Decide whether the next tag is an open or close tag
            if next_open_tag != -1 and (
                next_open_tag < next_close_tag or next_close_tag == -1
            ):
                open_count += 1
                search_idx = raw_obs.find(">", next_open_tag) + 1
            else:
                close_count += 1
                search_idx = next_close_tag + len(f"</{tag_name}>")
            # If we've closed all open tags, break
            if open_count == close_count:
                break
        # Extract the target element
        target_element = raw_obs[start_tag_idx:search_idx]
        obs = obs.replace("</html>", f"{target_element} </html>")
    else:
        target_element = None

    return obs, target_element


def get_specifiers_from_sample(sample: dict) -> str:
    website = sample["website"]
    domain = sample["domain"]
    subdomain = sample["subdomain"]
    goal = sample["confirmed_task"]
    specifier = (
        f"Website: {website}\nDomain: {domain}\nSubdomain: {subdomain}\nTask: {goal}"
    )

    return specifier

def retrieve_exemplar_name(memory, query: str, top_k) -> List[str]:
    while True:
        try:
            docs_and_similarities = memory.similarity_search_with_score(query, top_k)
            break
        except:
            time.sleep(1)
    retrieved_exemplar_names = []
    retrieved_metadata = []
    scores = []
    for doc, score in docs_and_similarities:
        retrieved_exemplar_names.append(doc.metadata["name"])
        retrieved_metadata.append(doc.page_content)
        scores.append(score)

    return retrieved_exemplar_names, retrieved_metadata, scores

def load_memory(memory_path):
    embedding = OpenAIEmbeddings(model="text-embedding-ada-002")
    memory = FAISS.load_local(memory_path, embedding)
    
    return memory