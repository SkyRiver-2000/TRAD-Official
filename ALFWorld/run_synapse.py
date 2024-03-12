import os
import time
import yaml
import openai
from openai.error import InvalidRequestError
import argparse
import alfworld
import alfworld.agents.environment
from copy import deepcopy

from utils import load_data
from thought_retrieval import retrieve_demonstration_task_meta
from prompts.sys_prompt import sys_message

openai.api_key = os.environ["OPENAI_API_KEY"]

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", type=str, default="./refined_data")
    parser.add_argument("--emb_dir", type=str, default="./data")
    parser.add_argument("--K", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--with_thought", action="store_true")
    args = parser.parse_args()
    return args

def llm(prompt, stop=["\n"]):
    while True:
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4-1106-preview",
                messages=[
                    {"role": "system", "content": sys_message},
                    {"role": "user", "content": prompt},
                ],
                top_p=1,
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

def process_ob(ob):
    if ob.startswith('You arrive at loc '):
        ob = ob[ob.find('. ')+2:]    
    return ob

def format_step(step, idx, task):
    if args.with_thought:
        if idx == 0:
            template = f"{process_ob(step['obs'])}\nYour task is to: {task}\n> think: {step['thought']}\n> act: {step['act']}\n"
        else:
            template = f"{process_ob(step['obs'])}\n> think: {step['thought']}\n> act: {step['act']}\n"
        return template
    if idx == 0:
        template = f"{process_ob(step['obs'])}\nYour task is to: {task}\n> act: {step['act']}\n"
    else:
        template = f"{process_ob(step['obs'])}\n> act: {step['act']}\n"
    return template

def make_prompt(template, demos, with_act=False):
    demo_prompts = []
    for demo in demos:
        demo_section, traj = "", demo["trajectory"]
        task, traj = traj["task"], traj["traj"]
        for i, step in enumerate(traj[:-1]):
            demo_section += format_step(step, i, task)
        step = traj[-1]
        if with_act: # For action
            if args.with_thought:
                demo_section += f"{process_ob(step['obs'])}\n> think: {step['thought']}\n> act: {step['act']}\n"
            else:
                demo_section += f"{process_ob(step['obs'])}\n> act: {step['act']}\n"
        else: # For thought
            demo_section += f"{process_ob(step['obs'])}\n"
        demo_prompts.append(demo_section)
    return template.format(*demo_prompts)

def alfworld_run(
    init_ob_embeddings,
    expert_demos,
    init_ob=''
):
    print_stuff, actions, observations = [], [], []
    if args.with_thought:
        template = deepcopy(prompt_template) + init_ob + '\n> think:'
    else:
        template = deepcopy(prompt_template) + init_ob + '\n> act:'
    thought_demos = retrieve_demonstration_task_meta(
        init_ob, init_ob_embeddings, expert_demos, args
    )
    prompt = make_prompt(template, thought_demos, with_act=False)
    print_stuff.append(init_ob)
    for i in range(50):
        # reason
        if args.with_thought:
            try:
                thought = llm(prompt, stop=['\n>']).strip()
            except:
                return 0, print_stuff
        
            prompt += f' {thought}\n> act:'
        
        # decision
        try:
            action = llm(prompt, stop=['\n']).strip()
        except:
            return 0, print_stuff
        
        # hack for GPT-3.5-turbo wrong output
        action = action.replace(" in ", " in/on ").replace(" on ", " in/on ")
        actions.append(action)
        
        # fail if repeating recent actions
        if len(actions) >= 3 and (actions[-1] == actions[-2]) and (actions[-2] == actions[-3]):
            return 0, print_stuff
        if len(actions) >= 6 and (actions[-1] == actions[-3]) and (actions[-3] == actions[-5]) \
            and (actions[-2] == actions[-4]) and (actions[-4] == actions[-6]):
            return 0, print_stuff
        if len(observations) >= 3 and all([x.startswith("Nothing") for x in observations[-3:]]):
            return 0, print_stuff
        
        # transition
        observation, reward, done, info = env.step([action])
        observation, reward, done = process_ob(observation[0]), info['won'][0], done[0]
        observations.append(observation)
        
        if args.with_thought:
            prompt += f' {action}\n{observation}\n> think:'
        else:
            prompt += f' {action}\n{observation}\n> act:'
        
        # log
        if args.with_thought:
            print(f'Reason {i+1}: {thought}')
        print(f'Act {i+1}: {action}')
        print(f'Obs {i+1}: {observation}')
        if args.with_thought:
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

start_idx = 0
end_idx = 134

thought_tag = "with_thought" if args.with_thought else "no_thought"
exp_name = f"synapse_{thought_tag}_test_{args.seed}"
os.makedirs(f"gpt-4-results/{exp_name}", exist_ok=True)
expert_demos, target_thoughts, init_ob_embeddings, thought_embeddings = load_data(args)

demo_section = '\n'.join(['{'+str(i)+'}' for i in range(args.K)])
prompt_template = f"Here are two examples.\n{demo_section}\nHere is the task.\n"

for idx in range(start_idx):
    ob, info = env.reset()

for idx in range(start_idx, end_idx): # 134
    ob, info = env.reset()
    ob = '\n'.join(ob[0].split('\n\n')[1:])
    name = '/'.join(info['extra.gamefile'][0].split('/')[-3:-1])
    print(f"{idx}:", name)
    for i, (k, v) in enumerate(prefixes.items()):
        if name.startswith(k):
            r, log_ = alfworld_run(
                init_ob_embeddings[i],
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