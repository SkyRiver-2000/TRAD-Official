import os
import sys
import json
import time
import yaml
import openai
from openai.error import InvalidRequestError
import argparse
import alfworld
import alfworld.agents.environment
from prompts.sys_prompt import sys_message
from prompts.alfworld_3prompts import react_prompt_inference as d

openai.api_key = os.environ["OPENAI_API_KEY"]

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0)
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
                stop=stop,
            )
            return response["choices"][0]["message"]["content"]
        except InvalidRequestError as e:
            raise e
        except:
            time.sleep(1)

with open('base_config.yaml') as reader:
    config = yaml.safe_load(reader)
    
split = "eval_out_of_distribution"

env = getattr(alfworld.agents.environment, config["env"]["type"])(config, train_eval=split)
env = env.init_env(batch_size=1)

def process_ob(ob):
    if ob.startswith('You arrive at loc '):
        ob = ob[ob.find('. ')+2:]    
    return ob
    
def alfworld_run(prompt, to_print=True, ob=''):
    print_stuff = []
    init_prompt = prompt + ob + '\n> think: '
    prompt, actions, observations = '', [], []
    if to_print:
        print_stuff.append(ob)
        sys.stdout.flush()
    for i in range(1, 50):
        # reason
        try:
            reason = llm(init_prompt + prompt, stop=['\n>']).strip()
        except:
            return 0, print_stuff
        
        # decision
        prompt += f' {reason}\n> act: '
        try:
            action = llm(init_prompt + prompt, stop=['\n']).strip()
        except:
            return 0, print_stuff
        
        # hack for GPT wrong output
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
        
        prompt += f' {action}\n{observation}\n> think: '
        
        # log
        if to_print:
            print(f'Reason {i}: {reason}')
            print(f'Act {i}: {action}')
            print(f'Obs {i}: {observation}')
            print_stuff.append(f'\nReason {i}: {reason}')
            print_stuff.append(f'\nAct {i}: {action}')
            print_stuff.append(f'\nObs {i}: {observation}')
            sys.stdout.flush()
        
        # done
        if done:
            return reward, print_stuff
    
    return 0, print_stuff

args = parse_args()
prefixes = {
    'pick_and_place': 'put',
    'pick_clean_then_place': 'clean',
    'pick_heat_then_place': 'heat',
    'pick_cool_then_place': 'cool',
    'look_at_obj': 'examine',
    'pick_two_obj': 'puttwo'
}
cnts = [0] * 6
rs = [0] * 6

start_idx = 0
end_idx = 134

exp_name = f"react_fixed_test_{args.seed}"
os.makedirs(f"gpt-4-results/{exp_name}", exist_ok=True)

for idx in range(start_idx):
    ob, info = env.reset()

for idx in range(start_idx, end_idx): # 134
    ob, info = env.reset()
    ob = '\n'.join(ob[0].split('\n\n')[1:])
    name = '/'.join(info['extra.gamefile'][0].split('/')[-3:-1])
    print(f"{idx}:", name)
    for i, (k, v) in enumerate(prefixes.items()):
        if name.startswith(k):
            prompt = 'Here are two examples.\n' + d[f'react_{v}_1'] + '\n' + d[f'react_{v}_0'] + '\nHere is the task.\n'
            # print(k, v)
            r, log_ = alfworld_run(prompt, to_print=True, ob=ob)
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