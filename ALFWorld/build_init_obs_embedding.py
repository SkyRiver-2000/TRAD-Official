import os
import json
import torch
import numpy as np
from tqdm import tqdm, trange
from sentence_transformers import SentenceTransformer

device = torch.device("cuda:0")
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2").to(device)
os.makedirs("data/", exist_ok=True)

traj_files = os.listdir("refined_data")
obs = {
    0: [],
    1: [],
    2: [],
    3: [],
    4: [],
    5: [],
}
for filename in tqdm(traj_files):
    idx = int(filename[0])
    json_path = os.path.join("refined_data", filename)
    with open(json_path, "r") as f:
        traj_dict = json.load(f)
    task, traj = traj_dict["task"], traj_dict["traj"]
    init_ob = traj[0]["obs"] + '\nYour task is to: ' + task
    obs[idx].append(init_ob)

for i in trange(6):
    emb = model.encode(
        obs[i], batch_size=512, convert_to_numpy=True, normalize_embeddings=True)
    np.save(f"data/{i}_init_obs_embedding.npy", emb)