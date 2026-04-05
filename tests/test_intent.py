from brain_agent.agent.intent import detect_intent


def test_question_mark() -> None:
    assert detect_intent("qu'est-ce que j'ai noté sur l'immobilier ?") == "query"
    assert detect_intent("c'est quoi déjà ?") == "query"


def test_interrogative_word() -> None:
    assert detect_intent("comment j'ai structuré mes SPV") == "query"
    assert detect_intent("pourquoi j'ai choisi django") == "query"
    assert detect_intent("résume mes notes padel") == "query"


def test_capture_default() -> None:
    assert detect_intent("note rapide: le levier s'applique aux réseaux") == "capture"
    assert detect_intent("idée: mutualiser le sponsoring padel") == "capture"


def test_override_prefixes() -> None:
    assert detect_intent("?immobilier") == "query"
    assert detect_intent("!pourquoi j'ai choisi django") == "capture"


def test_empty_string() -> None:
    assert detect_intent("") == "capture"
    assert detect_intent("   ") == "capture"
