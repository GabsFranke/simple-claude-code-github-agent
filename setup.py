"""Setup configuration for simple-claude-code-github-agent."""

from setuptools import find_packages, setup

setup(
    name="simple-claude-code-github-agent",
    version="0.1.0",
    description="AI-powered GitHub agent using Claude Agent SDK",
    author="Franke Gabriel",
    python_requires=">=3.11",
    packages=find_packages(include=["shared", "shared.*"]),
    install_requires=[
        "fastapi>=0.115.0",
        "uvicorn>=0.32.0",
        "redis>=5.0.0",
        "httpx>=0.28.1",
        "pydantic>=2.10.0",
        "pydantic-settings>=2.6.0",
        "langfuse>=2.59.0",
        "PyJWT>=2.10.0",
        "google-cloud-pubsub>=2.26.0",
    ],
    extras_require={  # type: ignore[arg-type]
        "dev": [
            "pytest>=9.0.2",
            "pytest-asyncio>=1.3.0",
            "pytest-cov>=7.0.0",
            "pytest-mock>=3.15.1",
            "black>=26.1.0",
            "isort>=8.0.1",
            "mypy>=1.19.1",
            "ruff>=0.15.4",
        ],
    },
)
