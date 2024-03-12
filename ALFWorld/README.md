# TRAD: Evaluation on ALFWorld

This folder contains the code for reproducing our paper's result on ALFWorld environment.

### Experiment Setup

Run the following commands to get expert trajectories and embeddings for retrieval:
```bash
# unzip pre-processed trajectories
unzip traj.zip -d refined_data

# build task meta-data embeddings
python build_init_obs_embedding.py

# build thought embeddings
python build_thought_embedding.py
```

### Start Experiments

Run the following command to re-produce our results:
```bash
# set OPENAI_API_KEY as YOUR_KEY
export OPENAI_API_KEY="YOUR_KEY"

# start experiment
python run_trad.py --forward_step 2 --backward_step 1 --with_mark --with_prev --seed $s --exp_name $n
```
$s: Specify random seed for GPT-4 inference.    
$n: Specify a name for logging.

---

Run the following command to re-produce synapse + ReAct baseline results:
```bash
# set OPENAI_API_KEY as YOUR_KEY
export OPENAI_API_KEY="YOUR_KEY"

# start experiment
python run_synapse.py --with_thought --seed $s
```

$s: Specify random seed for GPT-4 inference.

To re-produce vanilla synapse (without thought) baseline results, remove the `--with_thought` tag.

---

Run the following command to re-produce ReAct baseline results:
```bash
# set OPENAI_API_KEY as YOUR_KEY
export OPENAI_API_KEY="YOUR_KEY"

# start experiment
python run_base.py --seed $s
```

$s: Specify random seed for GPT-4 inference.
