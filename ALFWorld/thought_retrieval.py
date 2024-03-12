import torch
import numpy as np

from sentence_transformers import SentenceTransformer

# Pre-load the embedding model
device = torch.device("cuda:0")
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2").to(device)

# Prompt in retrieval for thought
def process_ob(ob):
    if ob.startswith("In the middle of the room"):
        ob = "You are in the middle of the room."
    return ob

# Trajectory-level random retrieval
def retrieve_demonstration_random(expert_demos, args):
    order = np.random.permutation(len(expert_demos))
    retrieved_demos = []
    
    retrieved_demos, len_trajs = [], []
    for idx in order[:args.K]:
        step_idx = len(expert_demos[idx]["traj"]) - 1
        retrieved_demos.append({
            "doc_id": idx,
            "trajectory": expert_demos[idx],
            "step_idx": step_idx,
            "similarity": None
        })
        len_trajs.append(step_idx)
    
    order = np.argsort(len_trajs)
    retrieved_demos = [retrieved_demos[i] for i in order]
    
    return retrieved_demos

# Trajectory-level retrieval with initial observation + task (Synapse)
@torch.no_grad()
def retrieve_demonstration_task_meta(init_obs, target_emb, expert_demos, args):
    # Embed task metadata into dense vectors, compute similarity, and rank
    query_emb = model.encode([init_obs], convert_to_tensor=True, normalize_embeddings=True)
    similarity = torch.matmul(query_emb, target_emb.T).view(-1).cpu().numpy()
    order = np.argsort(-similarity)
    
    retrieved_demos, len_trajs = [], []
    for idx in order[:args.K]:
        step_idx = len(expert_demos[idx]["traj"]) - 1
        retrieved_demos.append({
            "doc_id": idx,
            "trajectory": expert_demos[idx],
            "step_idx": step_idx,
            "similarity": similarity
        })
        len_trajs.append(step_idx)
    
    # Re-rank the retrieved demostrations by its step_idx or length
    order = np.argsort(len_trajs)
    retrieved_demos = [retrieved_demos[i] for i in order]
    
    return retrieved_demos

# Step-level retrieval with thought
@torch.no_grad()
def retrieve_demonstration_thought(thought, target_emb, expert_demos, args):
    # Embed thought into dense vectors, compute similarity, and rank
    query_emb = model.encode([thought], convert_to_tensor=True, normalize_embeddings=True)
    similarity = torch.matmul(query_emb, target_emb.T).view(-1).cpu().numpy()
    order = np.argsort(-similarity)
    
    # Index for concatnated embedding
    raw_traj_idx = np.repeat(np.arange(len(expert_demos)), [len(d["traj"])-1 for d in expert_demos])
    raw_step_idx = np.concatenate([np.arange(len(d["traj"])-1) for d in expert_demos], axis=0)
    
    # Collect trajectory-independent demonstrations
    traj_collection, retrieved_demos, step_indices = set(), [], []
    for idx in order:
        traj_idx, step_idx = raw_traj_idx[idx], raw_step_idx[idx]
        if traj_idx in traj_collection:
            continue
        traj_collection.add(traj_idx)
        retrieved_demos.append({
            "doc_id": traj_idx,
            "trajectory": expert_demos[traj_idx],
            "step_idx": step_idx,
            "similarity": similarity
        })
        step_indices.append(step_idx)
        if len(traj_collection) >= args.K:
            break
    
    # Re-rank the retrieved demostrations by its step_idx or length
    order = np.argsort(step_indices)
    retrieved_demos = [retrieved_demos[i] for i in order]
    return retrieved_demos