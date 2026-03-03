"""Parse agent commands from GitHub comments."""

# Registered command prefixes (command names and aliases)
# These should match the commands registered in the command registry
REGISTERED_COMMANDS = {
    "review-pr",
    "pr-review",
    "review",
    "triage",
    "triage-issue",
}


def parse_command(comment_body: str) -> str:
    """Extract agent command from comment body.

    Supports two patterns:
    1. /agent <query> - Generic query/request (always accepted)
    2. /<command> - Specific registered command (e.g., /pr-review, /triage, /review)

    Args:
        comment_body: The comment text to parse

    Returns:
        The command text, or empty string if not found
    """
    if not comment_body:
        return ""

    lines = comment_body.strip().split("\n")
    for line in lines:
        line = line.strip()

        # Pattern 1: /agent <query> - pass the query as-is to generic command
        if line.startswith("/agent "):
            return line[7:].strip()  # Strip "/agent " (with space)

        # Pattern 2: /<command> - check if it's a registered command
        if line.startswith("/"):
            # Extract the command name (first word after /)
            command_part = line[1:].strip()
            command_name = command_part.split()[0] if command_part else ""

            # Check if this is a registered command
            if command_name in REGISTERED_COMMANDS:
                return command_part

    return ""
