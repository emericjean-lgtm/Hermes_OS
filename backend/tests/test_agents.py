from __future__ import annotations

import pytest

from backend.agents.hermes_prime import HermesPrimeAgent
from backend.core.router import ModelRouter


@pytest.mark.asyncio
async def test_prime_agent_streams_full_response(fake_ollama_client, models_config):
    router = ModelRouter(models_config)
    agent = HermesPrimeAgent(fake_ollama_client, router, models_config)

    decision, stream = await agent.respond([{"role": "user", "content": "hello"}])

    assert decision.task_type == "conversation"
    tokens = [chunk async for chunk in stream]
    assert "".join(tokens) == "Hello, world!"
    assert fake_ollama_client.last_chat_call["model"] == decision.model


@pytest.mark.asyncio
async def test_prime_agent_reuses_loaded_model(models_config):
    from backend.tests.conftest import FakeOllamaClient

    # Lu dans la configuration, jamais écrit en dur : ce test vérifie qu'un
    # modèle déjà résident est réutilisé, pas quel modèle tient le rôle
    # aujourd'hui. La version précédente attendait « deepseek-r1:14b » et
    # est tombée quand HOS-108 a réaffecté les rôles — un faux rouge, sur du
    # code inchangé.
    attendu = models_config["roles"]["reasoning"]["model"]
    client = FakeOllamaClient(running_models=[attendu])
    router = ModelRouter(models_config)
    agent = HermesPrimeAgent(client, router, models_config)

    decision, _stream = await agent.respond(
        [{"role": "user", "content": "explain this bug"}],
        task_type="reasoning",
    )

    assert decision.model == attendu
    assert "already loaded" in decision.reason
