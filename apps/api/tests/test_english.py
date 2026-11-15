import re

from fa_contracts.english import english_display


def test_saved_system_text_is_translated_without_mutating_source_data():
    original = {
        'scenario': {'name': 'Лунная база'},
        'limitations': ['Отсутствие данных не означает безопасность.'],
        'question': 'Мой вопрос',
        'excerpt': 'Исходная цитата',
        'raw_value': '1,92',
    }
    result = english_display(original)
    assert result['scenario']['name'] == 'Lunar base'
    assert result['limitations'] == ['Missing data do not establish safety.']
    assert result['question'] == original['question']
    assert result['excerpt'] == original['excerpt']
    assert result['raw_value'] == '1,92'
    assert original['scenario']['name'] == 'Лунная база'


def test_config_uses_english_dictionary(server):
    config = server.client().get('/api/v1/config').data
    labels = [item['label'] for values in config['dictionaries'].values() for item in values]
    assert not any(re.search(r'[\u0400-\u04ff]', label) for label in labels)
