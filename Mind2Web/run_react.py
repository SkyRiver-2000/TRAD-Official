import pickle
import logging
import argparse
import os
import json
import openai
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm, trange

from memory.build_memory import load_memory
from envs.env_utils import load_json
from agents.react import eval_traj_sample

logger = logging.getLogger("synapse")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(handler)

openai.api_key = os.environ["OPENAI_API_KEY"]
test_end_idx = {
    "test_task": 252,
    "test_website": 177,
    "test_domain": 912
}

def create_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", type=str, default="./Mind2Web/data")
    # 252, 177, 912
    parser.add_argument(
        "--benchmark", type=str, choices=["test_task", "test_website", "test_domain"]
    )
    parser.add_argument("--top_k_elements", type=int, default=5)
    parser.add_argument("--retrieve_top_k", type=int, default=3)
    parser.add_argument("--model", type=str, default="gpt-3.5-turbo-0613")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--random", action="store_true", default=False)
    parser.add_argument("--no_memory", action="store_true", default=False)
    parser.add_argument("--no_trajectory", action="store_true", default=False)
    parser.add_argument("--chunk_size", type=int, default=5)
    parser.add_argument("--exp_note", type=str, default="")
    parser.add_argument("--seed", type=int, default=0)

    return parser

def load_memory_and_thoughts(args):
    memory = load_memory(args.memory_path)
    with open(os.path.join(args.memory_path, f"exemplars.json"), "r") as f:
        memory_mapping = json.load(f)
    
    args.thought_path = os.path.join(args.memory_path, "thoughts")
    thoughts = []
    for i in trange(len(memory_mapping)):
        with open(os.path.join(args.thought_path, f"{i}.json"), 'r') as f:
            thoughts.append(json.load(f))
    
    return memory, memory_mapping, thoughts

def main():
    parser = create_parser()
    args = parser.parse_args()
    current_path = os.getcwd()
    args.memory_path = os.path.join(current_path, "memory/")
    args.log_dir = os.path.join(current_path, "results/")

    # Evaluate test set
    assert args.benchmark in ["test_task", "test_website", "test_domain"]
    samples = load_json(args.data_dir, args.benchmark)
    start_idx = 0
    end_idx = test_end_idx[args.benchmark]
    samples = samples[start_idx:end_idx]
    n = len(samples)

    # add prediction scores and ranks to candidates
    with open(os.path.join(args.data_dir, "scores_all_data.pkl"), "rb") as f:
        candidate_results = pickle.load(f)
    candidate_scores = candidate_results["scores"]
    candidate_ranks = candidate_results["ranks"]
    for sample in samples:
        for s, act_repr in zip(sample["actions"], sample["action_reprs"]):
            sample_id = f"{sample['annotation_id']}_{s['action_uid']}"
            for candidates in [s["pos_candidates"], s["neg_candidates"]]:
                for candidate in candidates:
                    candidate_id = candidate["backend_node_id"]
                    candidate["score"] = candidate_scores[sample_id][candidate_id]
                    candidate["rank"] = candidate_ranks[sample_id][candidate_id]
    
    memory, memory_mapping, thoughts = load_memory_and_thoughts(args)
    
    with tqdm(total=n) as t:
        for i in range(0, n, args.chunk_size):
            chunk = samples[i : min(i + args.chunk_size, n)]
            with ThreadPoolExecutor() as executor:
                iterator = executor.map(
                    lambda p: eval_traj_sample(p[0], args, p[1], memory, memory_mapping, thoughts),
                    zip(range(i + start_idx, i + start_idx + len(chunk)), chunk),
                )
                for _ in iterator:
                    pass
            t.update(len(chunk))

if __name__ == "__main__":
    main()
