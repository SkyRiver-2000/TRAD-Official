import os
import time
import yaml
import openai
from openai.error import InvalidRequestError
import argparse
import alfworld
import alfworld.agents.environment

from utils import load_data
from thought_retrieval import (
    retrieve_demonstration_task_meta,
    retrieve_demonstration_thought
)
from prompts.sys_prompt import sys_message, sys_message_with_mark

openai.api_key = os.environ["OPENAI_API_KEY"]

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", type=str, default="./refined_data")
    parser.add_argument("--emb_dir", type=str, default="./data")
    parser.add_argument("--K", type=int, default=2)
    parser.add_argument("--forward_step", type=int, default=1)
    parser.add_argument("--backward_step", type=int, default=0)
    parser.add_argument("--with_mark", action="store_true")
    parser.add_argument("--with_prev", action="store_true")
    parser.add_argument("--exp_note", type=str, default="default")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    return args

def llm(sys_message, prompt, stop=["\n"]):
    while True:
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4-1106-preview",
                messages=[
                    {"role": "system", "content": sys_message},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=300,
                temperature=0,
                seed=args.seed,
                stop=stop,
            )
            return response["choices"][0]["message"]["content"]
        except InvalidRequestError as e:
            raise e
        except:
            time.sleep(1)

args = parse_args()
with open('base_config.yaml') as reader:
    config = yaml.safe_load(reader)
    
split = "eval_out_of_distribution"

env = getattr(alfworld.agents.environment, config["env"]["type"])(config, train_eval=split)
env = env.init_env(batch_size=1)

sys_mess = sys_message_with_mark if args.with_mark else sys_message

def process_ob(ob, process_init=False):
    if ob.startswith('You arrive at loc '):
        ob = ob[ob.find('. ')+2:]
    elif ob.startswith('You are in the middle ') and process_init:
        ob = "In the middle of the room" + ob[ob.find(', '):]
    return ob

def format_step(step, idx, task):
    if idx == 0:
        template = f"{step['obs']}\nYour task is to: {task}\n> think: {step['thought']}\n> act: {step['act']}\n"
    else:
        template = f"{process_ob(step['obs'])}\n> think: {step['thought']}\n> act: {step['act']}\n"
    return template

def make_prompt_thought(template, demos, prev_prompts, ob, args):
    demo_prompts = []
    for demo in demos:
        traj, step_idx = demo["trajectory"], demo["step_idx"]
        task, traj = traj["task"], traj["traj"]
        demo_section = ""
        for idx in range(len(traj)-1):
            demo_section += format_step(traj[idx], idx, task)
        demo_prompts.append(demo_section)
    
    prev_steps = "\n".join(prev_prompts) + "\n"
    
    result = template.format(*demo_prompts) + prev_steps + f"{ob}\n> think:"
    return result
    

def make_prompt(template, demos, prev_prompts, ob, thought, args):
    demo_prompts = []
    for demo in demos:
        traj, step_idx = demo["trajectory"], demo["step_idx"]
        task, traj = traj["task"], traj["traj"]
        start_idx = max(0, step_idx-args.backward_step)
        end_idx = min(step_idx+1+args.forward_step, len(traj)-1)
        demo_section = ""
        if start_idx > 0:
            init_ob = process_ob(traj[0]['obs'], True)
            demo_section += f"{init_ob}\n" + f"Your task is to: {task}\n"
        for idx in range(start_idx, end_idx):
            demo_section += f"[Step {idx-step_idx}]\n" if args.with_mark else ""
            demo_section += format_step(traj[idx], idx, task)
        demo_section += process_ob(traj[end_idx]["obs"]) + '\n'
        demo_prompts.append(demo_section)
    
    # Insert history piece before current step
    if args.with_prev and len(prev_prompts):
        ahead_step = args.backward_step + args.forward_step
        start_idx = max(0, len(prev_prompts)-ahead_step)
        prev_ = prev_prompts.copy()
        if start_idx > 0:
            meta_info = process_ob(prev_[0], True)
            meta_info = meta_info[:meta_info.find("> think:")]
            prev_[start_idx] = meta_info + prev_[start_idx]
        prev_steps = "\n".join(prev_[start_idx:]) + "\n"
    # No history piece, but specify the task still
    elif len(prev_prompts):
        meta_info = process_ob(prev_prompts[0], True)
        prev_steps = meta_info[:meta_info.find("> think:")]
    # Step 0
    else:
        prev_steps = ""
    
    result = template.format(*demo_prompts) + prev_steps + f"{ob}\n> think: {thought}\n> act:"
    result = (result, f"{ob}\n> think: {thought}\n> act:")
    return result

def alfworld_run(
    thought_embeddings,
    ob_embeddings,
    expert_demos,
    init_ob=''
):
    print_stuff, actions, prev_prompts, observation = [init_ob], [], [], init_ob
    
    # retrieval for thought generation
    thought_demos = retrieve_demonstration_task_meta(
        init_ob, ob_embeddings, expert_demos, args
    )
    
    for i in range(50):
        # reason
        prompt = make_prompt_thought(
            prompt_template, thought_demos, prev_prompts, observation, args
        )
        
        try:
            thought = llm(sys_message, prompt, stop=['\n>']).strip()
        except:
            print("Thought Production Error...")
            return 0, print_stuff
        
        thought = thought.replace(" in ", " in/on ").replace(" on ", " in/on ")
        
        # thought retrieval
        retrieved_demos = retrieve_demonstration_thought(
            thought, thought_embeddings, expert_demos, args
        )
        
        # decision
        prompt, prompt_cut = make_prompt(
            prompt_template, retrieved_demos, prev_prompts, observation, thought, args
        )
        
        try:
            action = llm(sys_mess, prompt, stop=['\n']).strip()
        except:
            print("Action Production Error...")
            return 0, print_stuff
        
        # hack for GPT wrong output
        action = action.replace(" in ", " in/on ").replace(" on ", " in/on ")
        actions.append(action)
        
        # for alignment
        prev_prompts.append(prompt_cut + ' ' + action)
        
        # fail if repeat often
        if len(actions) >= 3 and (actions[-1] == actions[-2]) and (actions[-2] == actions[-3]):
            return 0, print_stuff
        if len(actions) >= 6 and (actions[-1] == actions[-3]) and (actions[-3] == actions[-5]) \
            and (actions[-2] == actions[-4]) and (actions[-4] == actions[-6]):
            return 0, print_stuff
        
        # transition
        observation, reward, done, info = env.step([action])
        observation, reward, done = process_ob(observation[0]), info['won'][0], done[0]
        
        # log
        print(f'Reason {i+1}: {thought}')
        print(f'Act {i+1}: {action}')
        print(f'Obs {i+1}: {observation}')
        print_stuff.append(f'\nReason {i+1}: {thought}')
        print_stuff.append(f'\nAct {i+1}: {action}')
        print_stuff.append(f'\nObs {i+1}: {observation}')
        
        # done
        if done:
            return reward, print_stuff
    
    return 0, print_stuff

prefixes = {
    'pick_and_place': 'put',
    'look_at_obj': 'examine',
    'pick_clean_then_place': 'clean',
    'pick_heat_then_place': 'heat',
    'pick_cool_then_place': 'cool',
    'pick_two_obj': 'puttwo'
}
cnts = [0] * 6
rs = [0] * 6

mark_tag = "with_mark" if args.with_mark else "no_mark"
prev_tag = "with_prev" if args.with_prev else "no_prev"
exp_name = f"trad_{args.forward_step}f{args.backward_step}b_{mark_tag}_{prev_tag}_{args.exp_note}"
os.makedirs(f"gpt-4-results/{exp_name}", exist_ok=True)
expert_demos, target_thoughts, ob_embeddings, thought_embeddings = load_data(args)

demo_section = '\n'.join(['{'+str(i)+'}' for i in range(args.K)])
prompt_template = f"Here are two examples.\n{demo_section}\nHere is the task.\n"

for idx in range(134):
    ob, info = env.reset()
    ob = '\n'.join(ob[0].split('\n\n')[1:])
    name = '/'.join(info['extra.gamefile'][0].split('/')[-3:-1])
    print(f"{idx}:", name)
    for i, (k, v) in enumerate(prefixes.items()):
        if name.startswith(k):
            r, log_ = alfworld_run(
                thought_embeddings[i],
                ob_embeddings[i],
                expert_demos[i],
                init_ob=ob
            )
            rs[i] += r
            cnts[i] += 1
            break
    with open(f"gpt-4-results/{exp_name}/{idx}.log", "w") as f:
        f.writelines(log_)
        f.write(f"\nSuccess: {r}")
    print(idx, 'r', r, 'rs', rs, 'cnts', cnts, 'sum(rs)/sum(cnts)', sum(rs) / sum(cnts))
    print('------------')
with open(f"gpt-4-results/{exp_name}/result_.log", "w") as f:
    f.write(f"{idx} r {r} rs {rs} cnts {cnts} sum(rs)/sum(cnts) {sum(rs)/sum(cnts)}")