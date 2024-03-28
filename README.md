# TRAD
[![Python 3.8](https://img.shields.io/badge/python-3.8-blue.svg)](https://www.python.org/downloads/release/python-385)
<img alt="License" src="https://img.shields.io/badge/License-MIT-blue">

Official PyTorch implementation of SIGIR 2024 paper [TRAD: Enhancing LLM Agents with Step-Wise Thought Retrieval and Aligned Decision](http://arxiv.org/abs/2403.06221)

### Requirements

Tested on python 3.8 environment:
* openai == 0.27.8
* alfworld == 0.2.2
* lxml == 4.7.1
* langchain == 0.0.285
* pytorch == 2.0.1
* transformers == 4.33.2
* sentence-transformers == 2.2.2

### Getting Started
See [`ALFWorld/`](ALFWorld/) and [`Mind2Web/`](Mind2Web/) folders for details about our experiments on these two environments.

### Citations
Please cite our paper and star this repo if you use TRAD and find it interesting/helpful for your work, we'd appreciate it! Feel free to contact [skyriver@sjtu.edu.cn](mailto:skyriver@sjtu.edu.cn) or open an issue if you have any questions.

```bibtex
@inproceedings{zhou2024trad,
    author={Ruiwen Zhou and Yingxuan Yang and Muning Wen and Ying Wen and Wenhao Wang and Chunling Xi and Guoqiang Xu and Yong Yu and Weinan Zhang},
    title={{TRAD}: Enhancing LLM Agents with Step-Wise Thought Retrieval and Aligned Decision}, 
    booktitle={Proceedings of the 47th International {ACM} {SIGIR} Conference on Research and Development in Information Retrieval ({SIGIR})},
    year={2024},
}
```