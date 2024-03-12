import os
import json
import torch
import numpy as np
from tqdm import tqdm

# Load pre-processed data
def load_data(args):
    demonstrations = {i: [] for i in range(6)}
    target_thoughts = {i: [] for i in range(6)}
    thought_embeddings = {}
    ob_embeddings = {}
    traj_files = os.listdir(args.data_dir)
    print("Loading trajectory files...")
    for filename in tqdm(traj_files):
        task_type = int(filename[0])
        with open(os.path.join(args.data_dir, filename), "r") as f:
            traj = json.load(f)
        thoughts = []
        for step in traj["traj"][:-1]:
            thoughts.append(step["thought"])
        demonstrations[task_type].append(traj)
        target_thoughts[task_type].append(thoughts)
    print("Loading pre-computed thought embeddings...")
    for task_type in range(6):
        th_emb_path = os.path.join(args.emb_dir, f"{task_type}_thought_embedding.npy")
        ob_emb_path = os.path.join(args.emb_dir, f"{task_type}_init_obs_embedding.npy")
        thought_embeddings[task_type] = torch.from_numpy(np.load(th_emb_path)).to('cuda:0')
        ob_embeddings[task_type] = torch.from_numpy(np.load(ob_emb_path)).to('cuda:0')
    return demonstrations, target_thoughts, ob_embeddings, thought_embeddings