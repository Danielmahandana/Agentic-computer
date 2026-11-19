from computer_agent.agent.labels import format_task_label


def test_format_task_label_adds_task_prefix():
    assert format_task_label("Research vacancies") == "Task: Research vacancies"
