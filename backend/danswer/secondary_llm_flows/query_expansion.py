from collections.abc import Callable
from typing import cast

from danswer.chat.chat_utils import combine_message_chain
from danswer.db.models import ChatMessage
from danswer.llm.factory import get_default_llm
from danswer.llm.interfaces import LLM
from danswer.llm.utils import dict_based_prompt_to_langchain_prompt
from danswer.prompts.chat_prompts import HISTORY_QUERY_REPHRASE
from danswer.prompts.miscellaneous_prompts import LANGUAGE_REPHRASE_PROMPT
from danswer.utils.logger import setup_logger
from danswer.utils.text_processing import count_punctuation
from danswer.utils.threadpool_concurrency import run_functions_tuples_in_parallel

logger = setup_logger()


def llm_multilingual_query_expansion(query: str, language: str) -> str:
    def _get_rephrase_messages() -> list[dict[str, str]]:
        messages = [
            {
                "role": "user",
                "content": LANGUAGE_REPHRASE_PROMPT.format(
                    query=query, target_language=language
                ),
            },
        ]

        return messages

    messages = _get_rephrase_messages()
    filled_llm_prompt = dict_based_prompt_to_langchain_prompt(messages)
    model_output = get_default_llm().invoke(filled_llm_prompt)
    logger.debug(model_output)

    return model_output


def multilingual_query_expansion(
    query: str,
    expansion_languages: str,
    use_threads: bool = True,
) -> list[str]:
    languages = expansion_languages.split(",")
    languages = [language.strip() for language in languages]
    if use_threads:
        functions_with_args: list[tuple[Callable, tuple]] = [
            (llm_multilingual_query_expansion, (query, language))
            for language in languages
        ]

        query_rephrases = run_functions_tuples_in_parallel(functions_with_args)
        return query_rephrases

    else:
        query_rephrases = [
            llm_multilingual_query_expansion(query, language) for language in languages
        ]
        return query_rephrases


def get_contextual_rephrase_messages(
    question: str,
    history_str: str,
) -> list[dict[str, str]]:
    messages = [
        {
            "role": "user",
            "content": HISTORY_QUERY_REPHRASE.format(
                question=question, chat_history=history_str
            ),
        },
    ]

    return messages


def history_based_query_rephrase(
    query_message: ChatMessage,
    history: list[ChatMessage],
    llm: LLM | None = None,
    size_heuristic: int = 200,
    punctuation_heuristic: int = 10,
) -> str:
    user_query = cast(str, query_message.message)

    if not user_query:
        raise ValueError("Can't rephrase/search an empty query")

    # If it's a very large query, assume it's a copy paste which we may want to find exactly
    # or at least very closely, so don't rephrase it
    if len(user_query) >= size_heuristic:
        return user_query

    # If there is an unusually high number of punctuations, it's probably not natural language
    # so don't rephrase it
    if count_punctuation(user_query) >= punctuation_heuristic:
        return user_query

    history_str = combine_message_chain(history)

    prompt_msgs = get_contextual_rephrase_messages(
        question=user_query, history_str=history_str
    )

    if llm is None:
        llm = get_default_llm()

    filled_llm_prompt = dict_based_prompt_to_langchain_prompt(prompt_msgs)
    rephrased_query = llm.invoke(filled_llm_prompt)

    logger.debug(f"Rephrased combined query: {rephrased_query}")

    return rephrased_query


def thread_based_query_rephrase(
    user_query: str,
    history_str: str,
    llm: LLM | None = None,
    size_heuristic: int = 200,
    punctuation_heuristic: int = 10,
) -> str:
    if not history_str:
        return user_query

    if len(user_query) >= size_heuristic:
        return user_query

    if count_punctuation(user_query) >= punctuation_heuristic:
        return user_query

    prompt_msgs = get_contextual_rephrase_messages(
        question=user_query, history_str=history_str
    )

    if llm is None:
        llm = get_default_llm()

    filled_llm_prompt = dict_based_prompt_to_langchain_prompt(prompt_msgs)
    rephrased_query = llm.invoke(filled_llm_prompt)

    logger.debug(f"Rephrased combined query: {rephrased_query}")

    return rephrased_query
