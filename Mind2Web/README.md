# TRAD: Evaluation on Mind2Web

This folder contains the code for reproducing our paper's result on Mind2Web environment.

### Experiment Setup

Run the following commands to get thoughts for retrieval:
```bash
# unzip pre-processed trajectories
unzip thoughts.zip -d memory/thoughts
```

Download the Mind2Web dataset and place it under this directory in the following structure:
```bash
Mind2Web        # present working directory
├── Mind2Web    # dataset storage
│   ├── data
│   │   ├── train
│   │   │   └── train_*.json
│   │   ├── test_task
│   │   │   └── test_task_*.json
│   │   ├── test_website
│   │   │   └── test_website_*.json
│   │   └── test_domain
│   │       └── test_domain_*.json
│   └── ...
├── run_*.py    # experiment scripts
└── ...
```

### Start Experiments
Run the following command to re-produce our results:
```bash
# set OPENAI_API_KEY as YOUR_KEY
export OPENAI_API_KEY="YOUR_KEY"

# start experiment
python run_trad.py --benchmark $b --with_mark --with_prev --forward_step 2 --backward_step 0 --seed $s --exp_note $n
```

$b: One benchmark among `[test_task, test_website, test_domain]`.  
$s: Specify random seed for GPT-3.5-turbo inference.  
$n: Specify a name for logging.

---

Run the following command to re-produce ReAct results:
```bash
# set OPENAI_API_KEY as YOUR_KEY
export OPENAI_API_KEY="YOUR_KEY"

# start experiment
python run_react.py --benchmark $b --seed $s
```

$b: One benchmark among `[test_task, test_website, test_domain]`.  
$s: Specify random seed for GPT-3.5-turbo inference.

By default ReAct uses demonstrations trajectories retrieved by synapse, add `--random` flag to use random ones.