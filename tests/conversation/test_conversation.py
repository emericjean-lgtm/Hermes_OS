"""Conversation & Human Experience Tests for Hermes OS (HOS-064).

Tests conversation session management, intent analysis, context building,
response generation, explainability, approval flow, and voice interfaces.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

import pytest

from backend.conversation.conversation_manager import ConversationManager
from backend.conversation.conversation_models import (
    ConversationContext,
    ConversationSession,
    ConversationStatus,
    IntentResult,
    IntentType,
    Message,
    MessageRole,
)
from backend.conversation.context_builder import ContextBuilder
from backend.conversation.intent_analyzer import IntentAnalyzer
from backend.conversation.response_generator import ResponseGenerator
from backend.conversation.routes import (
    handle_start_session,
    handle_send_message,
    handle_get_history,
    handle_approve,
    handle_cancel,
    handle_get_context,
    handle_list_sessions,
    _get_manager,
)
from backend.explainability.decision_explainer import DecisionExplainer
from backend.explainability.explanation_models import DecisionType, RiskLevel
from backend.explainability.routes import handle_explain, handle_get_explanation, handle_list_explanations
from backend.policy.approval_explainer import ApprovalExplainer
from backend.voice.speech_to_text import SpeechToTextProvider, WhisperProvider, CloudSTTProvider
from backend.voice.text_to_speech import TextToSpeechProvider, PiperProvider, CloudTTSProvider


# ═══════════════════════════════════════════════════════════════
# Models Tests
# ═══════════════════════════════════════════════════════════════

class TestConversationModels:
    def test_message_creation(self):
        msg = Message(role=MessageRole.USER, content="Hello")
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello"
        assert msg.timestamp != ""

    def test_message_with_metadata(self):
        msg = Message(role=MessageRole.HERMES, content="Test", metadata={"key": "val"})
        assert msg.metadata["key"] == "val"

    def test_message_all_roles(self):
        for role in MessageRole:
            msg = Message(role=role, content="test")
            assert msg.role == role

    def test_intent_result_defaults(self):
        intent = IntentResult()
        assert intent.intent == IntentType.UNKNOWN
        assert intent.confidence == 0.0
        assert intent.domain == "general"

    def test_intent_result_with_values(self):
        intent = IntentResult(intent=IntentType.OPTIMIZATION, confidence=0.9, domain="code")
        assert intent.intent == IntentType.OPTIMIZATION
        assert intent.confidence == 0.9

    def test_conversation_context_defaults(self):
        ctx = ConversationContext()
        assert ctx.active_agents == []
        assert ctx.security_level == "normal"

    def test_conversation_session_creation(self):
        session = ConversationSession(session_id="test_1", user_id="user_1")
        assert session.session_id == "test_1"
        assert session.status == ConversationStatus.ACTIVE
        assert session.created_at != ""

    def test_session_status_enum(self):
        for status in ConversationStatus:
            session = ConversationSession(session_id=f"test_{status.value}", status=status)
            assert session.status == status

    def test_message_timestamp_auto(self):
        msg = Message(role=MessageRole.SYSTEM, content="auto")
        assert msg.timestamp != ""

    def test_intent_type_enum_values(self):
        assert IntentType.OPTIMIZATION.value == "optimization"
        assert IntentType.DEBUG.value == "debug"
        assert IntentType.REFACTOR.value == "refactor"

    def test_session_updated_at(self):
        session = ConversationSession(session_id="s1")
        assert session.updated_at == session.created_at


# ═══════════════════════════════════════════════════════════════
# Intent Analyzer Tests
# ═══════════════════════════════════════════════════════════════

class TestIntentAnalyzer:
    def test_analyze_optimization_request(self):
        ia = IntentAnalyzer()
        result = ia.analyze("Optimise les performances de mon application")
        assert result.intent == IntentType.OPTIMIZATION
        assert result.confidence > 0.5

    def test_analyze_debug_request(self):
        ia = IntentAnalyzer()
        result = ia.analyze("J'ai un bug dans le module d'authentification")
        assert result.intent == IntentType.DEBUG

    def test_analyze_refactor_request(self):
        ia = IntentAnalyzer()
        result = ia.analyze("Refactorise la couche de persistence")
        assert result.intent == IntentType.REFACTOR

    def test_analyze_greeting(self):
        ia = IntentAnalyzer()
        result = ia.analyze("Bonjour Hermes")
        assert result.intent == IntentType.GREETING

    def test_analyze_english_greeting(self):
        ia = IntentAnalyzer()
        result = ia.analyze("Hello")
        assert result.intent == IntentType.GREETING

    def test_analyze_approval_yes(self):
        ia = IntentAnalyzer()
        result = ia.analyze("Oui, approuve")
        assert result.intent == IntentType.APPROVAL

    def test_analyze_cancel(self):
        ia = IntentAnalyzer()
        result = ia.analyze("Annule l'opération")
        assert result.intent == IntentType.CANCEL

    def test_analyze_unknown(self):
        ia = IntentAnalyzer()
        result = ia.analyze("zzzzzzyyywww qqqq")
        assert result.intent == IntentType.UNKNOWN

    def test_analyze_question_mark(self):
        ia = IntentAnalyzer()
        result = ia.analyze("Qu'est-ce que Hermes OS ?")
        assert result.intent == IntentType.QUESTION

    def test_analyze_documentation_request(self):
        ia = IntentAnalyzer()
        result = ia.analyze("Documente mon API REST")
        assert result.intent == IntentType.DOCUMENTATION

    def test_analyze_analysis_request(self):
        ia = IntentAnalyzer()
        result = ia.analyze("Analyse la structure du projet")
        assert result.intent == IntentType.ANALYSIS

    def test_analyze_command(self):
        ia = IntentAnalyzer()
        result = ia.analyze("Crée une nouvelle application web")
        assert result.intent == IntentType.COMMAND

    def test_domain_detection(self):
        ia = IntentAnalyzer()
        result = ia.analyze("Analyse le code Python")
        assert result.domain == "software"

    def test_confidence_high_for_greeting(self):
        ia = IntentAnalyzer()
        result = ia.analyze("Salut")
        assert result.confidence > 0.9

    def test_get_history(self):
        ia = IntentAnalyzer()
        ia.analyze("Test 1")
        ia.analyze("Test 2")
        history = ia.get_history()
        assert len(history) == 2

    def test_complexity_estimation(self):
        ia = IntentAnalyzer()
        simple = ia.analyze("Optimise")
        complex_req = ia.analyze("Optimise un large microservices full production avec plusieurs composants")
        assert complex_req.complexity > simple.complexity

    def test_language_detection_by_file(self):
        ia = IntentAnalyzer()
        result = ia.analyze("Analyse mon app.py")
        assert "file" in result.extracted_entities
        assert result.extracted_entities["file"] == "app.py"

    def test_approval_english(self):
        ia = IntentAnalyzer()
        result = ia.analyze("Yes, go ahead")
        assert result.intent == IntentType.APPROVAL

    def test_cancel_stop(self):
        ia = IntentAnalyzer()
        result = ia.analyze("Stop")
        assert result.intent == IntentType.CANCEL


# ═══════════════════════════════════════════════════════════════
# Context Builder Tests
# ═══════════════════════════════════════════════════════════════

class TestContextBuilder:
    def test_build_initial_context(self):
        cb = ContextBuilder()
        ctx = cb.build_initial_context()
        assert isinstance(ctx, ConversationContext)
        assert ctx.active_agents == []

    def test_build_context_with_message(self):
        cb = ContextBuilder()
        ctx = cb.build_context("Analyse mon projet")
        assert ctx is not None
        assert ctx.workspace_status == "ready"

    def test_build_context_with_existing(self):
        cb = ContextBuilder()
        existing = ConversationContext(active_goal_id="goal_1")
        ctx = cb.build_context("Continue", existing)
        assert ctx.active_goal_id == "goal_1"

    def test_get_active_agents_empty(self):
        cb = ContextBuilder()
        agents = cb._get_active_agents()
        assert isinstance(agents, list)

    def test_update_context(self):
        cb = ContextBuilder()
        cb.update_context("session_1", {"key": "value"})
        assert True

    def test_get_recent_events_empty(self):
        cb = ContextBuilder()
        events = cb._get_recent_events(None)
        assert events == []


# ═══════════════════════════════════════════════════════════════
# Response Generator Tests
# ═══════════════════════════════════════════════════════════════

def _offline_generator() -> ResponseGenerator:
    """Un générateur dont l'inférence échoue volontairement.

    ``ResponseGenerator`` interroge désormais un vrai modèle : sans cela, le chat
    répondait « Voici ce que je peux vous dire à ce sujet… » à toute question.
    Les tests ci-dessous portent sur le *repli* — le gabarit servi quand aucun
    modèle n'est joignable — et sur les accusés de réception, qui restent
    volontairement déterministes. Une doublure qui lève garantit ce chemin sans
    dépendre d'Ollama, comme ``tests.support.fake_inference`` ailleurs.
    """
    async def unavailable(**_kwargs):
        raise ConnectionError("aucun modèle en test")

    return ResponseGenerator(chat=unavailable)


class TestResponseGenerator:
    def test_generate_optimization_response(self):
        rg = _offline_generator()
        intent = IntentResult(intent=IntentType.OPTIMIZATION, confidence=0.9)
        ctx = ConversationContext()
        response = rg.generate(intent, ctx, "Optimise mon code")
        assert "optimisation" in response.message.content.lower()
        assert response.requires_approval is False

    def test_generate_debug_response_requires_approval(self):
        rg = ResponseGenerator()
        intent = IntentResult(intent=IntentType.DEBUG, confidence=0.9, complexity=0.8)
        ctx = ConversationContext()
        response = rg.generate(intent, ctx, "Debug mon API")
        assert response.requires_approval is True

    def test_generate_greeting_response(self):
        rg = _offline_generator()
        intent = IntentResult(intent=IntentType.GREETING, confidence=0.95)
        ctx = ConversationContext()
        response = rg.generate(intent, ctx, "Salut")
        assert "Bonjour" in response.message.content
        assert len(response.suggested_actions) > 0

    def test_generate_unknown_response(self):
        rg = _offline_generator()
        intent = IntentResult(intent=IntentType.UNKNOWN)
        ctx = ConversationContext()
        response = rg.generate(intent, ctx, "?")
        assert "pas bien compris" in response.message.content.lower()

    def test_generate_cancel_response(self):
        rg = _offline_generator()
        intent = IntentResult(intent=IntentType.CANCEL)
        ctx = ConversationContext()
        response = rg.generate(intent, ctx, "Annule")
        assert "annulée" in response.message.content.lower()

    def test_suggested_actions_for_analysis(self):
        rg = ResponseGenerator()
        intent = IntentResult(intent=IntentType.ANALYSIS)
        ctx = ConversationContext()
        response = rg.generate(intent, ctx, "Analyse")
        assert len(response.suggested_actions) > 0

    def test_approval_request_for_complex_refactor(self):
        rg = ResponseGenerator()
        intent = IntentResult(intent=IntentType.REFACTOR, complexity=0.7)
        ctx = ConversationContext()
        response = rg.generate(intent, ctx, "Refactorise tout")
        assert response.requires_approval is True
        assert response.approval_request is not None


# ═══════════════════════════════════════════════════════════════
# Conversation Manager Tests
# ═══════════════════════════════════════════════════════════════

class TestConversationManager:
    def test_create_session(self):
        mgr = ConversationManager()
        session = mgr.create_session("user_1")
        assert session.session_id != ""
        assert session.user_id == "user_1"

    def test_get_session(self):
        mgr = ConversationManager()
        session = mgr.create_session("user_1")
        found = mgr.get_session(session.session_id)
        assert found is not None
        assert found.session_id == session.session_id

    def test_get_session_not_found(self):
        mgr = ConversationManager()
        found = mgr.get_session("nonexistent")
        assert found is None

    def test_handle_message_creates_session_auto(self):
        mgr = ConversationManager()
        response = mgr.handle_message("", "Bonjour")
        assert response.session_id != ""

    def test_handle_message_adds_messages(self):
        mgr = ConversationManager()
        session = mgr.create_session("user_1")
        mgr.handle_message(session.session_id, "Analyse mon projet")
        hist = mgr.get_history(session.session_id)
        assert len(hist) >= 1

    def test_handle_message_with_known_session(self):
        mgr = ConversationManager()
        session = mgr.create_session("test_user")
        response = mgr.handle_message(session.session_id, "Optimise mon code")
        assert response.intent is not None
        assert response.intent.intent == IntentType.OPTIMIZATION

    def test_approve_action(self):
        mgr = ConversationManager()
        session = mgr.create_session("user_1")
        response = mgr.approve_action(session.session_id)
        assert "enregistrée" in response.message.content.lower()

    def test_cancel_action(self):
        mgr = ConversationManager()
        session = mgr.create_session("user_1")
        response = mgr.cancel_action(session.session_id)
        assert "annulée" in response.message.content.lower()

    def test_list_sessions(self):
        mgr = ConversationManager()
        mgr.create_session("a")
        mgr.create_session("b")
        sessions = mgr.list_sessions()
        assert len(sessions) >= 2

    def test_get_history_empty(self):
        mgr = ConversationManager()
        hist = mgr.get_history("nonexistent")
        assert hist == []

    def test_set_memory_manager(self):
        mgr = ConversationManager()
        mgr.set_memory_manager(object())
        assert True

    def test_thread_safety(self):
        mgr = ConversationManager()
        errors = []
        def worker(n):
            try:
                session = mgr.create_session(f"thread_{n}")
                mgr.handle_message(session.session_id, f"Message {n}")
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0


# ═══════════════════════════════════════════════════════════════
# API Routes Tests
# ═══════════════════════════════════════════════════════════════

class TestConversationRoutes:
    def test_start_session(self):
        result = handle_start_session("test_user")
        assert result["success"] is True
        assert "session_id" in result

    def test_send_message(self):
        session = handle_start_session("test_user")
        result = handle_send_message(session["session_id"], "Bonjour")
        assert result["success"] is True
        assert "message" in result

    def test_get_history(self):
        session = handle_start_session("test")
        handle_send_message(session["session_id"], "Test 1")
        result = handle_get_history(session["session_id"])
        assert result["success"] is True
        assert result["total"] >= 1

    def test_approve(self):
        session = handle_start_session("test")
        result = handle_approve(session["session_id"])
        assert result["success"] is True
        assert result["status"] == "approved"

    def test_cancel(self):
        session = handle_start_session("test")
        result = handle_cancel(session["session_id"])
        assert result["success"] is True
        assert result["status"] == "cancelled"

    def test_get_context(self):
        session = handle_start_session("test")
        handle_send_message(session["session_id"], "Test")
        result = handle_get_context(session["session_id"])
        assert result["success"] is True
        assert "context" in result

    def test_list_sessions(self):
        handle_start_session("u1")
        handle_start_session("u2")
        result = handle_list_sessions()
        assert result["success"] is True
        assert result["total"] >= 2

    def test_get_session_manager(self):
        mgr = _get_manager()
        assert mgr is not None


# ═══════════════════════════════════════════════════════════════
# Explainability Tests
# ═══════════════════════════════════════════════════════════════

class TestDecisionExplainer:
    def test_explain_agent_selection(self):
        exp = DecisionExplainer()
        result = exp.explain_agent_selection("CoderAgent", "Best match for task", 0.95)
        assert result.decision_type == DecisionType.AGENT_SELECTION
        assert result.confidence == 0.95

    def test_explain_runtime_selection(self):
        exp = DecisionExplainer()
        result = exp.explain_runtime_selection("KTransformers", "GPU available", 0.88)
        assert result.decision_type == DecisionType.RUNTIME_SELECTION

    def test_explain_model_selection(self):
        exp = DecisionExplainer()
        result = exp.explain_model_selection("qwen3-coder", "VRAM 14GB", 0.94)
        assert "qwen3" in result.decision.lower()

    def test_explain_policy_decision(self):
        exp = DecisionExplainer()
        result = exp.explain_policy_decision("allow", "Policy allows", 0.99, "low")
        assert result.decision_type == DecisionType.POLICY_DECISION

    def test_explain_with_alternatives(self):
        exp = DecisionExplainer()
        alts = [
            {"name": "AgentB", "reason": "Lower cost", "score": 0.6, "pros": ["cheaper"]},
            {"name": "AgentC", "reason": "Available", "score": 0.4, "cons": ["slower"]},
        ]
        result = exp.explain_agent_selection("AgentA", "Best", 0.9, alts)
        assert len(result.alternatives) == 2

    def test_get_history(self):
        exp = DecisionExplainer()
        exp.explain_agent_selection("A", "test", 0.9)
        exp.explain_runtime_selection("B", "test", 0.8)
        history = exp.get_history()
        assert len(history) >= 2

    def test_get_explanation_by_id(self):
        exp = DecisionExplainer()
        result = exp.explain_agent_selection("AgentX", "Best", 0.95)
        found = exp.get_explanation(result.decision_id)
        assert found is not None
        assert found.decision == "AgentX"

    def test_get_explanation_not_found(self):
        exp = DecisionExplainer()
        found = exp.get_explanation("nonexistent")
        assert found is None

    def test_format_for_user(self):
        exp = DecisionExplainer()
        result = exp.explain_agent_selection("CoderAgent", "Best match", 0.95)
        formatted = exp.format_for_user(result)
        assert "CoderAgent" in formatted
        assert "95%" in formatted

    def test_format_with_alternatives(self):
        exp = DecisionExplainer()
        alts = [{"name": "AltAgent", "reason": "Fallback", "score": 0.5}]
        result = exp.explain_agent_selection("Primary", "Best", 0.9, alts)
        formatted = exp.format_for_user(result)
        assert "AltAgent" in formatted

    def test_explain_routes(self):
        result = handle_explain("agent_selection", "TestAgent", "Best match", 0.95)
        assert result["success"] is True
        assert "decision_id" in result

    def test_get_explanation_route(self):
        result = handle_explain("runtime_selection", "RT", "Best", 0.9)
        found = handle_get_explanation(result["decision_id"])
        assert found["success"] is True

    def test_list_explanations_route(self):
        handle_explain("agent_selection", "A", "test", 0.9)
        handle_explain("runtime_selection", "B", "test", 0.8)
        result = handle_list_explanations()
        assert result["success"] is True
        assert result["total"] >= 0

    def test_decision_type_enum(self):
        assert DecisionType.MODEL_SELECTION.value == "model_selection"
        assert DecisionType.TOOL_SELECTION.value == "tool_selection"

    def test_risk_level_enum(self):
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_explain_with_risk_high(self):
        exp = DecisionExplainer()
        result = exp.explain_policy_decision("delete", "Risky action", 0.7, "high")
        assert result.risk_level == RiskLevel.HIGH


# ═══════════════════════════════════════════════════════════════
# Approval Explainer Tests
# ═══════════════════════════════════════════════════════════════

class TestApprovalExplainer:
    def test_request_approval(self):
        ae = ApprovalExplainer()
        req = ae.request_approval("delete_workspace", "Supprimer le workspace production", "high")
        assert req.status == "pending"
        assert req.risk_level == RiskLevel.HIGH

    def test_approve_request(self):
        ae = ApprovalExplainer()
        req = ae.request_approval("action", "description", "medium")
        approved = ae.approve(req.request_id)
        assert approved is not None
        assert approved.status == "approved"

    def test_reject_request(self):
        ae = ApprovalExplainer()
        req = ae.request_approval("action", "description", "low")
        rejected = ae.reject(req.request_id)
        assert rejected is not None
        assert rejected.status == "rejected"

    def test_get_pending(self):
        ae = ApprovalExplainer()
        ae.request_approval("a1", "desc1", "medium")
        ae.request_approval("a2", "desc2", "high")
        pending = ae.get_pending()
        assert len(pending) == 2

    def test_get_pending_after_approve(self):
        ae = ApprovalExplainer()
        req = ae.request_approval("a", "desc", "low")
        ae.approve(req.request_id)
        pending = ae.get_pending()
        assert len(pending) == 0

    def test_get_request(self):
        ae = ApprovalExplainer()
        req = ae.request_approval("test", "desc", "low")
        found = ae.get_request(req.request_id)
        assert found is not None

    def test_get_request_not_found(self):
        ae = ApprovalExplainer()
        found = ae.get_request("nonexistent")
        assert found is None

    def test_format_for_user(self):
        ae = ApprovalExplainer()
        req = ae.request_approval("delete_db", "Supprimer la base de données", "critical")
        formatted = ae.format_for_user(req)
        assert "Action" in formatted
        assert "Critique" in formatted.lower() or "CRITICAL" in formatted

    def test_format_with_agents(self):
        ae = ApprovalExplainer()
        req = ae.request_approval("edit_code", "Modifier le code", "medium",
                                  affected_agents=["CoderAgent", "ReviewerAgent"])
        formatted = ae.format_for_user(req)
        assert "CoderAgent" in formatted


# ═══════════════════════════════════════════════════════════════
# Voice Interface Tests
# ═══════════════════════════════════════════════════════════════

class TestVoiceInterfaces:
    def test_whisper_provider_interface(self):
        provider = WhisperProvider()
        name = provider.get_name()
        assert name == "whisper"

    def test_whisper_availability_check(self):
        provider = WhisperProvider()
        available = provider.is_available()
        assert isinstance(available, bool)

    def test_cloud_stt_provider(self):
        provider = CloudSTTProvider()
        assert provider.is_available() is False

    def test_cloud_stt_with_key(self):
        provider = CloudSTTProvider(api_key="test_key")
        assert provider.is_available() is True

    def test_piper_provider_interface(self):
        provider = PiperProvider()
        name = provider.get_name()
        assert name == "piper"

    def test_cloud_tts_provider(self):
        provider = CloudTTSProvider()
        assert provider.is_available() is False

    def test_cloud_tts_with_key(self):
        provider = CloudTTSProvider(api_key="test_key", provider="azure")
        assert provider.is_available() is True
        assert "azure" in provider.get_name()

    def test_speech_to_text_abstract(self):
        assert issubclass(WhisperProvider, SpeechToTextProvider)

    def test_text_to_speech_abstract(self):
        assert issubclass(PiperProvider, TextToSpeechProvider)

    def test_stt_languages(self):
        provider = WhisperProvider()
        langs = provider.get_languages()
        assert "fr" in langs
        assert "en" in langs

    def test_tts_voices(self):
        provider = PiperProvider()
        voices = provider.get_voices()
        assert "default" in voices


# ═══════════════════════════════════════════════════════════════
# Thread Safety Tests
# ═══════════════════════════════════════════════════════════════

class TestThreadSafetyConversation:
    def test_concurrent_sessions(self):
        mgr = ConversationManager()
        errors = []
        def create_and_message(n):
            try:
                session = mgr.create_session(f"user_{n}")
                mgr.handle_message(session.session_id, f"Message {n} from user")
                mgr.get_history(session.session_id)
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=create_and_message, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0
        sessions = mgr.list_sessions()
        assert len(sessions) >= 15

    def test_concurrent_intent_analysis(self):
        ia = IntentAnalyzer()
        errors = []
        def analyze(n):
            try:
                ia.analyze(f"Optimise le module {n} pour les performances")
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=analyze, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0

    def test_concurrent_explanations(self):
        exp = DecisionExplainer()
        errors = []
        def explain(n):
            try:
                exp.explain_agent_selection(f"Agent_{n}", f"Task {n}", 0.9)
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=explain, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0
        history = exp.get_history()
        assert len(history) >= 15

    def test_concurrent_approvals(self):
        ae = ApprovalExplainer()
        errors = []
        def request_and_approve(n):
            try:
                req = ae.request_approval(f"action_{n}", f"desc_{n}", "medium")
                if n % 2 == 0:
                    ae.approve(req.request_id)
                else:
                    ae.reject(req.request_id)
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=request_and_approve, args=(i,)) for i in range(15)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0
