import logging
import re
import time
import inspect
import tiktoken
import backoff
import openai
from openai.error import (
    APIConnectionError,
    APIError,
    RateLimitError,
    ServiceUnavailableError,
    InvalidRequestError,
)
from typing import List, Dict, Tuple, Union

logger = logging.getLogger("main")


def num_tokens_from_messages(messages, model):
    """Return the number of tokens used by a list of messages.
    Borrowed from https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        print("Warning: model not found. Using cl100k_base encoding.")
        encoding = tiktoken.get_encoding("cl100k_base")
    if model in {
        "gpt-3.5-turbo-0613",
        "gpt-3.5-turbo-16k-0613",
        "gpt-4-0314",
        "gpt-4-32k-0314",
        "gpt-4-0613",
        "gpt-4-32k-0613",
    }:
        tokens_per_message = 3
        tokens_per_name = 1
    elif model == "gpt-3.5-turbo-0301":
        tokens_per_message = (
            4  # every message follows <|start|>{role/name}\n{content}<|end|>\n
        )
        tokens_per_name = -1  # if there's a name, the role is omitted
    else:
        raise NotImplementedError(
            f"""num_tokens_from_messages() is not implemented for model {model}. See https://github.com/openai/openai-python/blob/main/chatml.md for information on how messages are converted to tokens."""
        )
    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens += tokens_per_name
    num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
    return num_tokens


MAX_TOKENS = {
    "gpt-3.5-turbo-0301": 4097,
    "gpt-3.5-turbo-0613": 4097,
    "gpt-3.5-turbo-16k-0613": 16385,
    "gpt-4-0613": 8193,
}


def get_mode(model: str) -> str:
    """Check if the model is a chat model."""

    if model in [
        "gpt-3.5-turbo-0301",
        "gpt-3.5-turbo-0613",
        "gpt-3.5-turbo-16k-0613",
        "gpt-4-0314",
        "gpt-4-32k-0314",
        "gpt-4-0613",
        "gpt-4-32k-0613",
    ]:
        return "chat"
    elif model in [
        "davinci-002",
        "gpt-3.5-turbo-instruct-0914",
    ]:
        return "completion"
    else:
        raise ValueError(f"Unknown model: {model}")

def generate_response(
    messages: List[Dict[str, str]],
    model: str,
    temperature: float,
    stop_tokens: Union[List[str], None] = None,
    seed: int = None
) -> Tuple[str, Dict[str, int]]:
    """Send a request to the OpenAI API."""

    logger.info(
        f"Send a request to the language model from {inspect.stack()[1].function}"
    )
    seed = {"seed": seed} if seed is not None else {}

    while True:
        try:
            if get_mode(model) == "chat":
                response = openai.ChatCompletion.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    stop=stop_tokens if stop_tokens else None,
                    # **seed
                )
                message = response["choices"][0]["message"]["content"]
            else:
                prompt = "\n\n".join(m["content"] for m in messages) + "\n\n"
                response = openai.Completion.create(
                    prompt=prompt,
                    engine=model,
                    temperature=temperature,
                    stop=stop_tokens if stop_tokens else None,
                    **seed
                )
                message = response["choices"][0]["text"]
            break
        except InvalidRequestError as e:
            raise e
        except:
            time.sleep(1)
    info = {
        key: response["usage"][key]
        for key in ["prompt_tokens", "completion_tokens", "total_tokens"]
    }

    return message, info


def extract_from_response(response: str, backtick="```") -> str:
    if backtick == "```":
        # Matches anything between ```<optional label>\n and \n```
        pattern = r"```(?:[a-zA-Z]*)\n?(.*?)\n?```"
    elif backtick == "`":
        pattern = r"`(.*?)`"
    else:
        raise ValueError(f"Unknown backtick: {backtick}")
    match = re.search(
        pattern, response, re.DOTALL
    )  # re.DOTALL makes . match also newlines
    if match:
        extracted_string = match.group(1)
    else:
        extracted_string = response

    return extracted_string
