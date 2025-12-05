from unittest.mock import Mock, patch
from app.services.gemini_rag import GeminiRag
from app.genai import errors


class TestGeminiRag:
    """Test GeminiRag resilience and error handling."""

    def test_ask_retries_on_server_error(self):
        """Verify @retry decorator works for ask()."""
        with patch("app.services.gemini_rag.settings") as mock_settings:
            mock_settings.GEMINI_API_KEY = "test-key"
            mock_settings.GEMINI_HTTP_TIMEOUT_S = 60
            mock_settings.GEMINI_RETRY_ATTEMPTS = 3

            rag = GeminiRag(api_key="test-key")

            # Mock client to fail twice, then succeed
            mock_response = Mock(text="Success")
            with patch.object(rag.client.models, "generate_content") as mock_generate:
                mock_generate.side_effect = [
                    errors.ServerError("503 Service Unavailable"),
                    errors.ServerError("503 Service Unavailable"),
                    mock_response,
                ]

                # Should succeed after retries
                result = rag.ask(
                    question="test", store_names=["store1"], metadata_filter=None, model="gemini-2.5-flash"
                )

                assert mock_generate.call_count == 3
                assert result == mock_response

    def test_extract_citations_handles_empty_response(self):
        """Ensure citation extraction doesn't crash on empty data."""
        # Empty candidates
        assert GeminiRag.extract_citations_from_response(Mock(candidates=[])) == []

    def test_extract_citations_handles_missing_metadata(self):
        """Ensure citation extraction handles missing grounding_metadata."""
        mock_resp = Mock(candidates=[Mock(grounding_metadata=None)])
        assert GeminiRag.extract_citations_from_response(mock_resp) == []

    def test_extract_citations_handles_missing_chunks(self):
        """Ensure citation extraction handles missing grounding_chunks."""
        mock_resp = Mock(candidates=[Mock(grounding_metadata=Mock(grounding_chunks=None))])
        assert GeminiRag.extract_citations_from_response(mock_resp) == []

    def test_extract_citations_returns_valid_structure(self):
        """Verify citation extraction with valid response."""
        mock_chunk = Mock(
            retrieved_context=Mock(
                uri="http://example.com", title="Test Doc", text="Snippet text", file_search_store="store1"
            ),
            web=None,
        )
        mock_resp = Mock(candidates=[Mock(grounding_metadata=Mock(grounding_chunks=[mock_chunk]))])

        citations = GeminiRag.extract_citations_from_response(mock_resp)

        assert len(citations) == 1
        assert citations[0]["source_type"] == "retrieved_context"
        assert citations[0]["uri"] == "http://example.com"
        assert citations[0]["title"] == "Test Doc"
        assert citations[0]["snippet"] == "Snippet text"
        assert citations[0]["store"] == "store1"

    def test_extract_citations_logs_warning_on_parsing_error(self, caplog):
        """Verify logging when citation parsing fails."""
        # Malformed response that will trigger AttributeError
        mock_resp = Mock(spec=[])  # No 'candidates' attribute

        with caplog.at_level("WARNING"):
            citations = GeminiRag.extract_citations_from_response(mock_resp)

        assert citations == []
        assert "Failed to extract citations" in caplog.text

    def test_new_stream_ids_returns_unique_ids(self):
        """Verify stream IDs are unique UUIDs."""
        id1, id2 = GeminiRag.new_stream_ids()

        assert isinstance(id1, str)
        assert isinstance(id2, str)
        assert id1 != id2
        assert len(id1) == 36  # UUID format
        assert len(id2) == 36
