import re

from conftest import FakeModel, block, draft, make_req
from fa_reasoning import reason
from fa_reasoning.config import LLMConfig
from fa_reasoning.prompt import SYSTEM_PROMPT


def test_english_request_does_not_publish_russian_model_text(bass):
    req = {**make_req(bass), "locale": "en"}
    model = FakeModel(draft(blocks=[block("summary", "Русский ответ", [bass['allowed_evidence_ids'][0]])],
                            limitations=["Русское ограничение"], follow_ups=["Русский вопрос?"]))
    answer = reason(req, model=model)
    texts = [b['text'] for b in answer['answer_blocks']] + answer['limitations'] + answer['follow_up_questions']
    assert not any(re.search(r'[\u0400-\u04ff]', text) for text in texts)
    assert any(r['rule'].endswith('language.english_only') for r in answer['audit']['rejections'])
    assert 'ENGLISH' in SYSTEM_PROMPT


def test_offline_answer_is_english_even_for_a_russian_question(bass):
    req = {**make_req(bass), "locale": "en"}
    answer = reason(req, config=LLMConfig(provider='offline', model=None, api_key=None, base_url=None))
    texts = [b['text'] for b in answer['answer_blocks']] + answer['limitations'] + answer['follow_up_questions']
    assert not any(re.search(r'[\u0400-\u04ff]', text) for text in texts)
    assert any('without a generative model' in text for text in answer['limitations'])
