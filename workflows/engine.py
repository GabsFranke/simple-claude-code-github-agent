"""YAML-driven workflow engine."""

import logging
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """Loads workflows from YAML and routes events/commands to prompts."""

    def __init__(self, config_path: str | Path = "workflows.yaml"):
        """Initialize workflow engine from YAML config.

        Args:
            config_path: Path to workflows.yaml file
        """
        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Workflow config not found: {config_path}")

        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        self.workflows = config["workflows"]

        # Build lookup tables for fast routing
        self._event_map: dict[str, str] = {}
        self._command_map: dict[str, str] = {}

        for workflow_name, workflow in self.workflows.items():
            triggers = workflow.get("triggers", {})

            # Map events to workflows
            for event in triggers.get("events", []):
                self._event_map[event] = workflow_name
                logger.debug(f"Mapped event '{event}' -> workflow '{workflow_name}'")

            # Map commands to workflows
            for command in triggers.get("commands", []):
                self._command_map[command] = workflow_name
                logger.debug(
                    f"Mapped command '{command}' -> workflow '{workflow_name}'"
                )

        logger.info(
            f"Loaded {len(self.workflows)} workflows: {list(self.workflows.keys())}"
        )

    def get_workflow_for_event(
        self, event_type: str, action: str | None = None
    ) -> str | None:
        """Get workflow name for a GitHub event.

        Args:
            event_type: GitHub event type (e.g., "pull_request")
            action: Event action (e.g., "opened")

        Returns:
            Workflow name or None if no workflow handles this event
        """
        # Try with action first (e.g., "pull_request.opened")
        if action:
            key = f"{event_type}.{action}"
            if key in self._event_map:
                return self._event_map[key]

        # Try without action (e.g., "pull_request")
        if event_type in self._event_map:
            return self._event_map[event_type]

        return None

    def get_workflow_for_command(self, command: str) -> str | None:
        """Get workflow name for a user command.

        Args:
            command: Command string (e.g., "/review")

        Returns:
            Workflow name or None if command not recognized
        """
        return self._command_map.get(command)

    def build_prompt(
        self,
        workflow_name: str,
        repo: str,
        issue_number: int | None = None,
        user_query: str = "",
        **kwargs: Any,
    ) -> str:
        """Build the final prompt for Claude Agent SDK.

        Args:
            workflow_name: Name of workflow to execute
            repo: Repository full name (owner/repo)
            issue_number: Issue or PR number
            user_query: User-provided query/context
            **kwargs: Additional template variables

        Returns:
            Complete prompt string for client.query()
        """
        if workflow_name not in self.workflows:
            raise ValueError(f"Unknown workflow: {workflow_name}")

        workflow = self.workflows[workflow_name]
        prompt_config = workflow["prompt"]

        # Fill template with variables
        template = prompt_config["template"]
        prompt = template.format(
            repo=repo,
            issue_number=issue_number or "",
            user_query=user_query,
            **kwargs,
        )

        # Add system context if defined
        system_context = prompt_config.get("system_context")
        if system_context:
            # Check if it's a file reference (ends with .md)
            if system_context.endswith(".md"):
                context_file = Path(__file__).parent.parent / "prompts" / system_context
                if context_file.exists():
                    system_context = context_file.read_text().strip()
                    logger.debug(f"Loaded system context from {system_context}")
                else:
                    logger.warning(f"System context file not found: {context_file}")
                    system_context = ""

            # Fill system context with variables if it's not empty
            if system_context:
                system_context = system_context.format(
                    repo=repo,
                    issue_number=issue_number or "",
                    **kwargs,
                )

                # Combine: prompt + system_context + user_query
                if user_query:
                    return f"{prompt} {system_context}. {user_query}"
                return f"{prompt} {system_context}"

        return str(prompt)

    def list_workflows(self) -> dict[str, str]:
        """List all available workflows.

        Returns:
            Dict mapping workflow names to descriptions
        """
        return {
            name: workflow.get("description", "No description")
            for name, workflow in self.workflows.items()
        }
