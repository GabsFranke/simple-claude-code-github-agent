"""Request processor that orchestrates Claude SDK execution."""

import asyncio
import json
import logging
import os
import tempfile
from typing import TYPE_CHECKING, Optional

import httpx
from auth import GitHubTokenManager
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
)
from commands import CommandContext, get_command_registry
from langfuse import Langfuse

from subagents import AGENTS

if TYPE_CHECKING:
    from shared import HealthChecker, MultiRateLimiter

logger = logging.getLogger(__name__)


class RequestProcessor:
    """Processes agent requests by orchestrating Claude SDK execution."""

    def __init__(
        self,
        token_manager: GitHubTokenManager,
        http_client: httpx.AsyncClient,
        langfuse_client: Langfuse | None = None,
        shutdown_event: asyncio.Event | None = None,
        rate_limiters: Optional["MultiRateLimiter"] = None,
        health_checker: Optional["HealthChecker"] = None,
    ):
        self.token_manager = token_manager
        self.http_client = http_client
        self.langfuse = langfuse_client
        self.shutdown_event = shutdown_event or asyncio.Event()
        self.rate_limiters = rate_limiters
        self.health_checker = health_checker
        self.temp_files_to_cleanup: list[str] = []

    async def process(
        self,
        repo: str,
        issue_number: int,
        command: str,
        user: str,
        auto_review: bool = False,
        auto_triage: bool = False,
    ) -> str:
        """Process a single agent request."""
        logger.info(f"Processing request for {repo} issue #{issue_number} by {user}")
        logger.info(f"Command: {command}")

        if self.langfuse:
            with self.langfuse.start_as_current_span(
                name="github_agent_request"
            ) as trace:
                trace.update(
                    input={
                        "repo": repo,
                        "issue_number": issue_number,
                        "command": command,
                        "user": user,
                        "auto_review": auto_review,
                        "auto_triage": auto_triage,
                    },
                    metadata={
                        "repo": repo,
                        "issue_number": issue_number,
                        "user": user,
                    },
                )

                try:
                    response = await self._execute(
                        repo, issue_number, command, user, auto_review, auto_triage
                    )

                    trace.update(
                        output={"response": response[:500]},
                        metadata={
                            "status": "success",
                            "response_length": len(response),
                        },
                    )
                    return response

                except Exception as e:
                    logger.error(f"Error processing request: {e}", exc_info=True)
                    trace.update(
                        output={"error": str(e)},
                        metadata={"status": "error"},
                        level="ERROR",
                    )
                    raise
                finally:
                    self.langfuse.flush()
        else:
            return await self._execute(
                repo, issue_number, command, user, auto_review, auto_triage
            )

    async def _execute(
        self,
        repo: str,
        issue_number: int,
        command: str,
        user: str,
        auto_review: bool,
        auto_triage: bool,
    ) -> str:
        """Execute the agent request."""
        # Determine event type
        if auto_review:
            event_type = "auto_review"
        elif auto_triage:
            event_type = "auto_triage"
        else:
            event_type = "manual"

        # Build command context
        context = CommandContext(
            repo=repo,
            issue_number=issue_number,
            command_text=command,
            user=user,
            event_type=event_type,
            raw_data={},
        )

        # Execute command via registry
        registry = get_command_registry()
        result = await registry.execute(context)
        prompt = result.prompt

        # Fetch CLAUDE.md if exists
        claude_md = await self._fetch_claude_md(repo)
        if claude_md:
            prompt = f"{claude_md}\n\n{prompt}"

        # Execute Claude SDK with the prompt
        if self.langfuse:
            model_name = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
            with self.langfuse.start_as_current_observation(
                name="claude_sdk_execution",
                as_type="generation",
                model=model_name,
                model_parameters={"sdk_version": "agent-sdk"},
            ) as generation:
                generation.update(
                    input=prompt,
                    metadata={
                        "repo": repo,
                        "issue_number": issue_number,
                        "user": user,
                        "auto_review": auto_review,
                        "auto_triage": auto_triage,
                        "command": command,
                    },
                )

                try:
                    response = await self._execute_claude_sdk(prompt)
                    generation.update(output=response, level="DEFAULT")
                    return response
                except Exception as e:
                    generation.update(level="ERROR", status_message=str(e))
                    raise
        else:
            return await self._execute_claude_sdk(prompt)

    async def _fetch_claude_md(self, repo: str) -> str:
        """Fetch CLAUDE.md from repository if it exists."""
        from shared.exceptions import GitHubAPIError
        from shared.retry import async_retry

        @async_retry(
            max_attempts=3,
            base_delay=1.0,
            exceptions=(GitHubAPIError, ConnectionError, TimeoutError),
        )
        async def _fetch_with_retry() -> str:
            # Apply rate limiting for GitHub API
            if self.rate_limiters:
                await self.rate_limiters.acquire("github", timeout=30.0)

            token = await self.token_manager.get_token()
            url = f"https://api.github.com/repos/{repo}/contents/CLAUDE.md"
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3.raw",
            }

            response = await self.http_client.get(url, headers=headers, timeout=10.0)

            if response.status_code == 200:
                # httpx response.text is str, but mypy doesn't know that
                return str(response.text)

            if response.status_code == 404:
                return ""

            raise GitHubAPIError(
                f"Failed to fetch CLAUDE.md: {response.status_code}",
                status_code=response.status_code,
            )

        try:
            result: str = await _fetch_with_retry()
            return result
        except (GitHubAPIError, ConnectionError, TimeoutError) as e:
            logger.debug(f"Could not fetch CLAUDE.md: {e}")
            return ""

    def _setup_anthropic_environment(self) -> None:
        """Setup Anthropic API environment variables."""
        anthropic_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv(
            "ANTHROPIC_AUTH_TOKEN"
        )
        if anthropic_key:
            os.environ["ANTHROPIC_API_KEY"] = anthropic_key

        base_url = os.getenv("ANTHROPIC_BASE_URL")
        if base_url:
            os.environ["ANTHROPIC_BASE_URL"] = base_url

    async def _create_mcp_config(self) -> dict:
        """Create MCP server configuration."""
        github_token = await self.token_manager.get_token()
        return {
            "github": {
                "type": "http",
                "url": "https://api.githubcopilot.com/mcp",
                "headers": {"Authorization": f"Bearer {github_token}"},
            }
        }

    def _create_agent_options(
        self, mcp_servers: dict, hooks: dict
    ) -> ClaudeAgentOptions:
        """Create Claude Agent SDK options."""
        return ClaudeAgentOptions(
            allowed_tools=["Task", "mcp__github__*"],
            permission_mode="acceptEdits",
            mcp_servers=mcp_servers,
            agents=AGENTS,
            plugins=[{"type": "local", "path": "/app/plugins/pr-review-toolkit"}],
            hooks=hooks,
            max_turns=50,
        )

    def _process_sdk_message(self, message, response_parts: list[str]) -> bool:
        """
        Process a single SDK message.

        Returns:
            True if processing should stop, False to continue
        """
        if self.shutdown_event.is_set():
            logger.warning("Shutdown requested, stopping SDK execution")
            return True

        if isinstance(message, SystemMessage):
            self._handle_system_message(message)

        elif isinstance(message, AssistantMessage):
            self._handle_assistant_message(message, response_parts)

        elif isinstance(message, ResultMessage):
            self._handle_result_message(message)
            return True

        return False

    def _handle_system_message(self, message: SystemMessage) -> None:
        """Handle system messages from SDK."""
        if message.subtype == "init" and hasattr(message, "data"):
            init_data = message.data
            if "plugins" in init_data:
                plugins = init_data.get("plugins", [])
                logger.info(f"Loaded {len(plugins)} plugins: {plugins}")

    def _handle_assistant_message(
        self, message: AssistantMessage, response_parts: list[str]
    ) -> None:
        """Handle assistant messages from SDK."""
        for block in message.content:
            if isinstance(block, TextBlock):
                response_parts.append(block.text)
                logger.info(f"Received text block: {block.text[:200]}...")
            elif isinstance(block, ToolUseBlock):
                logger.info(f"Tool use: {block.name} (id: {block.id})")

    def _handle_result_message(self, message: ResultMessage) -> None:
        """Handle result messages from SDK."""
        logger.info(
            f"Response complete - {message.num_turns} turns, "
            f"{message.duration_ms}ms"
        )
        if message.total_cost_usd:
            logger.info(f"Cost: ${message.total_cost_usd:.4f}")

    async def _execute_claude_sdk(self, prompt: str) -> str:
        """Execute Claude Agent SDK."""
        from shared.exceptions import SDKInitializationError, SDKTimeoutError

        # Apply rate limiting for Anthropic API
        if self.rate_limiters:
            logger.info("Acquiring Anthropic API rate limit...")
            await self.rate_limiters.acquire("anthropic", timeout=60.0)

        # Setup environment
        self._setup_anthropic_environment()

        # Configure Vertex AI if specified
        credentials_file_path = await self._setup_vertex_ai_credentials()

        try:
            # Get MCP configuration
            mcp_servers = await self._create_mcp_config()

            # Setup Langfuse hooks if configured
            hooks = self._setup_langfuse_hooks()

            # Configure agent options
            options = self._create_agent_options(mcp_servers, hooks)

            logger.info("Executing Claude Agent SDK...")

            response_parts: list[str] = []

            try:
                async with asyncio.timeout(1800):  # 30 minutes
                    async with ClaudeSDKClient(options=options) as client:
                        await client.query(prompt)

                        async for message in client.receive_messages():
                            should_stop = self._process_sdk_message(
                                message, response_parts
                            )
                            if should_stop:
                                break

            except TimeoutError as e:
                raise SDKTimeoutError(
                    "Claude Agent SDK execution timed out after 30 minutes"
                ) from e
            except Exception as e:
                raise SDKInitializationError(
                    f"Failed to execute Claude Agent SDK: {e}"
                ) from e

            response = "\n".join(response_parts)

            if not response or not response.strip():
                raise SDKInitializationError("Claude Agent SDK returned empty response")

            logger.info("Claude Agent SDK completed successfully")
            return response

        finally:
            # Cleanup temporary credentials file
            if credentials_file_path:
                self._cleanup_temp_file(credentials_file_path)

    def _cleanup_temp_file(self, file_path: str) -> None:
        """Cleanup a temporary file."""
        try:
            os.unlink(file_path)
            self.temp_files_to_cleanup.remove(file_path)
            logger.debug(f"Cleaned up temporary file: {file_path}")
        except FileNotFoundError:
            logger.debug(f"Temporary file already removed: {file_path}")
        except ValueError:
            logger.debug(f"Temporary file not in cleanup list: {file_path}")
        except OSError as e:
            logger.warning(f"Failed to cleanup temporary file {file_path}: {e}")

    async def _setup_vertex_ai_credentials(self) -> str | None:
        """Setup Vertex AI credentials if configured."""
        from shared.exceptions import ConfigurationError

        project_id = os.getenv("ANTHROPIC_VERTEX_PROJECT_ID")
        if not project_id:
            return None

        os.environ["ANTHROPIC_VERTEX_PROJECT_ID"] = project_id

        region = os.getenv("ANTHROPIC_VERTEX_REGION")
        if region:
            os.environ["ANTHROPIC_VERTEX_REGION"] = region

        credentials_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        if not credentials_json:
            return None

        try:
            credentials_data = json.loads(credentials_json)

            # Use context manager for proper resource handling
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as credentials_file:
                credentials_file_path = credentials_file.name
                json.dump(credentials_data, credentials_file)

            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_file_path
            self.temp_files_to_cleanup.append(credentials_file_path)
            logger.info("Configured Vertex AI credentials")
            return credentials_file_path

        except json.JSONDecodeError as e:
            logger.error(f"Invalid GOOGLE_APPLICATION_CREDENTIALS_JSON: {e}")
            raise ConfigurationError(
                "GOOGLE_APPLICATION_CREDENTIALS_JSON must be valid JSON"
            ) from e

    def _setup_langfuse_hooks(self) -> dict:
        """Setup Langfuse hooks if configured."""
        langfuse_public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        langfuse_secret_key = os.getenv("LANGFUSE_SECRET_KEY")

        if not (langfuse_public_key and langfuse_secret_key):
            return {}

        async def langfuse_stop_hook_async(input_data, _tool_use_id, _context):
            """Async hook for Langfuse (unused params prefixed with _)."""
            try:
                hook_payload = json.dumps(input_data)

                process = await asyncio.create_subprocess_exec(
                    "python3",
                    "/app/hooks/langfuse_hook.py",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env={
                        "TRACE_TO_LANGFUSE": "true",
                        "LANGFUSE_PUBLIC_KEY": langfuse_public_key,
                        "LANGFUSE_SECRET_KEY": langfuse_secret_key,
                        "LANGFUSE_HOST": os.getenv(
                            "LANGFUSE_HOST", "http://langfuse:3000"
                        ),
                        "LANGFUSE_BASE_URL": os.getenv(
                            "LANGFUSE_HOST", "http://langfuse:3000"
                        ),
                        "CC_LANGFUSE_DEBUG": "true",
                        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                        "HOME": os.environ.get("HOME", "/root"),
                    },
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(input=hook_payload.encode()), timeout=30.0
                    )

                    if process.returncode != 0:
                        logger.warning(f"Langfuse hook failed: {stderr.decode()}")
                    else:
                        logger.debug(
                            f"Langfuse hook completed: {stdout.decode()[:100]}"
                        )

                except TimeoutError:
                    logger.warning("Langfuse hook timed out after 30s")
                    process.kill()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5.0)
                    except TimeoutError:
                        logger.error("Process failed to terminate after kill signal")

            except OSError as e:
                logger.warning(f"Error running Langfuse hook: {e}")
                if "process" in locals() and process.returncode is None:
                    try:
                        process.kill()
                        await asyncio.wait_for(process.wait(), timeout=5.0)
                    except OSError as cleanup_error:
                        logger.error(f"Failed to cleanup process: {cleanup_error}")

            return {}

        return {
            "Stop": [HookMatcher(matcher="*", hooks=[langfuse_stop_hook_async])],
            "SubagentStop": [
                HookMatcher(matcher="*", hooks=[langfuse_stop_hook_async])
            ],
        }

    async def cleanup(self):
        """Cleanup resources."""
        for temp_file in self.temp_files_to_cleanup:
            try:
                os.unlink(temp_file)
                logger.debug(f"Cleaned up temporary file: {temp_file}")
            except OSError as e:
                logger.warning(f"Failed to cleanup {temp_file}: {e}")
        self.temp_files_to_cleanup.clear()
