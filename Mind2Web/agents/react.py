import logging
from lxml import etree
import numpy as np
import json
import os
import random
import torch
from pathlib import Path
from pprint import pprint
from sentence_transformers import SentenceTransformer
from sentence_transformers.util import semantic_search

from envs.env_utils import (
    get_target_obs_and_act,
    get_target_obs,
    calculate_f1,
    parse_act_str,
    construct_act_str,
)
from utils.llm import (
    generate_response,
    num_tokens_from_messages,
    MAX_TOKENS,
    extract_from_response,
)
from memory.build_memory import (
    retrieve_exemplar_name,
    get_specifiers_from_sample,
    get_top_k_obs,
)

logger = logging.getLogger(__name__)

device = torch.device("cuda:0")
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2").to(device)

sys_thought = """
You are a large language model trained to navigate the web. You will be given a task, an observation, and your previous actions. Each time you should output the next action and wait for the next observation. Here is the action space:
1. `CLICK [id]`: Click on an HTML element with its id.
2. `TYPE [id] [value]`: Type a string into the element with the id.
3. `SELECT [id] [value]`: Select a value for an HTML element by its id.
Now you are given some expert demonstrations, follow these examples and conduct reasoning about your situation.
"""

sys_act = """
You are a large language model trained to navigate the web. You will be given a task, an observation, and your previous actions. Each time you should output the next action and wait for the next observation. Here is the action space:
1. `CLICK [id]`: Click on an HTML element with its id.
2. `TYPE [id] [value]`: Type a string into the element with the id.
3. `SELECT [id] [value]`: Select a value for an HTML element by its id.
Now you are given some expert demonstrations, follow these demonstrations and make your decision.
The mark [Step $i] indicates a coarse relative position of expert demonstration steps to your situation. For example, [Step -1] means the last step, [Step 0] means the current step, and [Step 1] means the next step.
Note that you should take all previous actions into reasoning. In your output, the action should be quoted by a pair of '`'.
"""

def process_exemplar_for_thought(trajectory, thoughts, step_idx):
    n_step = len(trajectory) // 2
    step_idx = min(n_step-1, step_idx)
    prev_actions = []
    raw_meta = trajectory[0]['content']
    idx = raw_meta.index('\n')
    task = raw_meta[:idx] + "\n"
    
    for i in range(step_idx):
        prev_actions.append(trajectory[i*2+1]['content'][5:])
    
    message = []
    
    observation = trajectory[step_idx*2]['content']
    if step_idx == 0:
        observation = observation[idx+1:]
    message.append({
        "role": "user",
        "content": task
        + observation
        + "\nprevious actions:\n"
        + '\n'.join(prev_actions)
        + "\nreason: "
        + thoughts[step_idx]
    })
    
    return message

def process_exemplar_for_action(trajectory, thoughts, step_idx):
    n_step = len(trajectory) // 2
    step_idx = min(n_step-1, step_idx)
    prev_actions = []
    raw_meta = trajectory[0]['content']
    idx = raw_meta.index('\n')
    task = raw_meta[:idx] + "\n"
    
    for i in range(step_idx):
        prev_actions.append(trajectory[i*2+1]['content'][5:])
    
    message = []
    
    observation, action = trajectory[step_idx*2]['content'], trajectory[step_idx*2+1]['content']
    if step_idx == 0:
        observation = observation[idx+1:]
    message.append(
        {
            "role": "user",
            "content": task
            + observation
            + "\nprevious actions:\n"
            + '\n'.join(prev_actions)
            + "\nreason: "
            + thoughts[step_idx]
            + "\n"
            + action
        }
    )
    return message

def retrieve_exemplar_random(traj_indices, memory_mapping, target_thoughts):
    chunked_thoughts = target_thoughts.copy()
    retrieved_demos = []
    
    for step_idx, traj_idx in enumerate(traj_indices):
        retrieved_demos.append({
            "doc_id": traj_idx,
            "trajectory": memory_mapping[traj_idx],
            "step_idx": step_idx,
            "thought": chunked_thoughts[traj_idx],
            "similarity": None
        })
    
    return retrieved_demos

def eval_traj_sample(task_id, args, sample, memory, memory_mapping, thoughts):
    element_acc = []
    action_f1 = []
    step_success = []
    success = []
    token_stats = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    conversation = []
    episode_length = len(sample["action_reprs"])

    specifier = get_specifiers_from_sample(sample)
    print("====================")
    print(specifier)
    
    if args.random:
        retrieved_exemplar_names = np.random.permutation(len(thoughts))[:args.retrieve_top_k]
    else: 
        retrieved_exemplar_names, _, _ = retrieve_exemplar_name(
            memory, specifier, args.retrieve_top_k
        )
    exemplars = [memory_mapping[name] for name in retrieved_exemplar_names]

    sys_message_thought = [
        {
            "role": "system",
            "content": sys_thought.strip('\n'),
        }
    ]
    sys_message_action = [
        {
            "role": "system",
            "content": sys_act.strip('\n'),
        }
    ]
    prev_actions = []
    prev_obs = []
    prev_thoughts = []
    na_message = f"I have to {sample['confirmed_task']}.\nHowever, there is no relevant element in the observation, and thus no action should be taken."
    for s, act_repr in zip(sample["actions"], sample["action_reprs"]):
        # target_obs, target_act = get_target_obs_and_act(s)
        _, target_act = get_target_obs_and_act(s)
        target_obs, _ = get_top_k_obs(s, args.top_k_elements)

        # stop if the ground truth element is not in the top-k candidates
        pos_candidates = s["pos_candidates"]
        pos_candidates = [c for c in pos_candidates if c["rank"] < args.top_k_elements]
        pos_ids = [c["backend_node_id"] for c in pos_candidates]
        if len(pos_ids) == 0:
            print("====================")
            print("Pos element not recalled...")
            prev_obs.append(target_obs)
            prev_actions.append("`" + target_act + "` (" + act_repr + ")")
            prev_thoughts.append(na_message)
            element_acc.append(0)
            action_f1.append(0)
            step_success.append(0)
            continue

        # get obs by pruning the tree with top-k candidates
        neg_candidates = s["neg_candidates"]
        neg_candidates = [c for c in neg_candidates if c["rank"] < args.top_k_elements]
        neg_ids = [c["backend_node_id"] for c in neg_candidates]
        all_candidates = pos_ids + neg_ids
        obs = get_target_obs(etree.fromstring(s["cleaned_html"]), all_candidates)

        # Generate thought with OpenAI api
        query = []
        if obs.startswith("Task:"):
            obs = obs[obs.index('\n')+1:]
        query.append(
            {
                "role": "user",
                "content": f"Task: {sample['confirmed_task']}\n"
                + "obs: `"
                + obs
                + "`\n"
                + "previous actions:\n"
                + '\n'.join(prev_actions)
                + "\nreason: ",
            }
        )

        model = args.model
        total_num_tokens = num_tokens_from_messages(sys_message_thought + query, model)
        if total_num_tokens > MAX_TOKENS[model]:
            model = "gpt-3.5-turbo-16k-0613"
            logger.info(f"Using {model} due to context limit")
            total_num_tokens = num_tokens_from_messages(sys_message_thought + query, model)
            if total_num_tokens > MAX_TOKENS[model]:
                logger.info(
                    f"Too many tokens in acting ({total_num_tokens} / {MAX_TOKENS[model]}), skipping..."
                )
                element_acc.append(0)
                action_f1.append(0)
                step_success.append(0)
                conversation.append(
                    {
                        "input": sys_message_thought + query,
                        "output": f"FAILED DUE TO THE CONTEXT LIMIT: {total_num_tokens}",
                    }
                )
                continue

        demo_message = []
        for e_id, e in enumerate(exemplars):
            e = process_exemplar_for_thought(e, thoughts[retrieved_exemplar_names[e_id]], e_id)
            total_num_tokens = num_tokens_from_messages(
                sys_message_thought + demo_message + e + query, model
            )
            if total_num_tokens > MAX_TOKENS[model]:
                if model == "gpt-3.5-turbo-16k-0613":
                    logger.info(
                        f"Using {e_id} / {len(exemplars)} exemplars due to context limit"
                    )
                    break
                else:
                    model = "gpt-3.5-turbo-16k-0613"
                    logger.info(f"Using {model} due to context limit")
                    total_num_tokens = num_tokens_from_messages(
                        sys_message_thought + demo_message + e + query, model
                    )
                    if total_num_tokens > MAX_TOKENS[model]:
                        logger.info(
                            f"Using {e_id} / {len(exemplars)} exemplars due to context limit"
                        )
                        break
                    else:
                        demo_message.extend(e)
            else:
                demo_message.extend(e)

        message = sys_message_thought + demo_message + query
        thought, info = generate_response(
            messages=message,
            model=model,
            temperature=args.temperature,
            stop_tokens=["Task:", "obs:", "act:"],
            seed=args.seed
        )
        prev_thoughts.append(thought)
        query[0]["content"] += (thought + "\nact: ")
        
        # NOTE: use thought for retrieval and do another inference for action
        retrieved_demos = retrieve_exemplar_random(
            retrieved_exemplar_names, memory_mapping, thoughts
        )
        
        demo_message = []
        for e_id, e in enumerate(retrieved_demos):
            e = process_exemplar_for_action(e["trajectory"], e["thought"], e_id)
            total_num_tokens = num_tokens_from_messages(
                sys_message_action + demo_message + e + query, model
            )
            if total_num_tokens > MAX_TOKENS[model]:
                if model == "gpt-3.5-turbo-16k-0613":
                    logger.info(
                        f"Using {e_id} / {len(exemplars)} exemplars due to context limit"
                    )
                    break
                else:
                    model = "gpt-3.5-turbo-16k-0613"
                    logger.info(f"Using {model} due to context limit")
                    total_num_tokens = num_tokens_from_messages(
                        sys_message_action + demo_message + e + query, model
                    )
                    if total_num_tokens > MAX_TOKENS[model]:
                        logger.info(
                            f"Using {e_id} / {len(exemplars)} exemplars due to context limit"
                        )
                        break
                    else:
                        demo_message.extend(e)
            else:
                demo_message.extend(e)
        
        message = sys_message_action + demo_message + query
        # print("\n".join([mess["content"] for mess in message]))
        # exit(-1)
        
        try:
            response, info = generate_response(
                messages=message,
                model=model,
                temperature=args.temperature,
                stop_tokens=["Task:", "obs:"],
                seed=args.seed
            )
        except:
            print("====================")
            print("OpenAI Request Error...")
            prev_obs.append(target_obs)
            prev_actions.append("`" + target_act + "` (" + act_repr + ")")
            element_acc.append(0)
            action_f1.append(0)
            step_success.append(0)
            continue
        prev_obs.append(target_obs)
        prev_actions.append("`" + target_act + "` (" + act_repr + ")")
        
        conversation.append({"input": message, "output": response, "token_stats": info})
        for k, v in info.items():
            token_stats[k] += v
        pred_act = extract_from_response(response, "`")
        print("====================")
        print("Pred Act:", pred_act)
        print("Target Act:", "`" + target_act + "` (" + act_repr + ")")
        pred_op, pred_id, pred_val = parse_act_str(pred_act)
        target_op, _, target_val = parse_act_str(target_act)

        # calculate metrics
        if pred_id in pos_ids:
            element_acc.append(1)
        else:
            element_acc.append(0)
        action_f1.append(
            calculate_f1(
                construct_act_str(pred_op, pred_val),
                construct_act_str(target_op, target_val),
            )
        )
        conversation.append({"pred_act": pred_act, "target_act": target_act})
        if pred_act == target_act:
            step_success.append(1)
        else:
            step_success.append(0)

    # check the last episode_length of step_success, if all 1, then success = 1
    if np.sum(step_success[-episode_length:]) == episode_length:
        success.append(1)
    else:
        success.append(0)

    conversation.append(
        {
            "element_acc": element_acc,
            "action_f1": action_f1,
            "step_success": step_success,
            "success": success,
        }
    )
    exp_name = f"{args.benchmark}_react_{args.top_k_elements}_{args.retrieve_top_k}"
    options = f"{f'_no_mem' if args.no_memory else ''}" + \
        f"{f'_no_traj' if args.no_trajectory else ''}" + \
        f"{f'_random' if args.random else ''}" + \
        f"_{args.exp_note}"
    log_dir = Path(
        f"{args.log_dir}/{args.model}/{exp_name}{options}"
    )
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(os.path.join(log_dir, f"{task_id}.json"), "w") as f:
        json.dump(conversation, f, indent=2)
        
    return conversation[-1]